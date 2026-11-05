"""Tests for the Flux Relay (infra/k8s/base/flux-relay/relay.py) and its Flux wiring."""

import io
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "infra" / "k8s" / "base" / "flux-relay"))

import relay  # noqa: E402

T0 = 1_800_000_000.0
CLUSTER = "C0CLUSTER"
STAGING = "C0STAGING"


def iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def flux_event(
    kind="Kustomization",
    name="fmi-codes-staging",
    message="health check failed",
    at=T0,
    severity="error",
):
    return {
        "involvedObject": {"kind": kind, "namespace": "flux-system", "name": name},
        "severity": severity,
        "timestamp": iso(at),
        "message": message,
        "reason": "ReconciliationFailed",
        "reportingController": "kustomize-controller",
    }


def flux_post(
    ts: float,
    kind="Kustomization",
    name="fmi-codes-staging",
    text="health check failed",
    stored=None,
):
    """A message as Flux's Slack notifier posts it, as conversations.history returns it.

    `stored` is the attachment text exactly as Slack returns it, when it isn't just `text`
    escaped (Slack's link markup)."""
    author = f"{kind.lower()}/{name}.flux-system"
    return {
        "ts": f"{ts:.6f}",
        "attachments": [
            {
                "author_name": author,
                "text": relay.escape(text) if stored is None else stored,
                "fallback": f"{author}: {text.splitlines()[0]}",
                "color": "danger",
            }
        ],
    }


def flux_object(
    status="True", ltt=T0 + 60, message="Applied revision: main@sha1:abc", generation=1, observed=1
):
    return {
        "metadata": {"generation": generation},
        "status": {
            "observedGeneration": observed,
            "conditions": [
                {
                    "type": "Ready",
                    "status": status,
                    "lastTransitionTime": iso(ltt),
                    "message": message,
                }
            ],
        },
    }


class FakeSlack:
    def __init__(self):
        self.channels = {CLUSTER: [], STAGING: []}
        self.threads = {}
        self.reactions = set()
        self.posts = []
        self.react_calls = 0
        self.fail = False
        # method -> Slack error code it answers with
        self.errors = {}

    def add(self, channel, message):
        self.channels[channel].append(message)

    def delete(self, channel, ts):
        self.channels[channel] = [m for m in self.channels[channel] if m["ts"] != ts]

    def _check(self, method):
        if self.fail:
            raise relay.SlackError(f"{method}: internal_error", "internal_error")
        if method in self.errors:
            raise relay.SlackError(f"{method}: {self.errors[method]}", self.errors[method])

    def history(self, channel, oldest):
        self._check("history")
        return sorted(
            (m for m in self.channels[channel] if float(m["ts"]) >= oldest),
            key=lambda m: -float(m["ts"]),
        )

    def replies(self, channel, ts):
        self._check("replies")
        parent = next((m for m in self.channels[channel] if m["ts"] == ts), None)
        if parent is None:
            raise relay.SlackError("conversations.replies: thread_not_found", "thread_not_found")
        return [parent] + self.threads.get((channel, ts), [])

    def post(self, channel, text, thread_ts, metadata):
        self._check("post")
        reply = {"ts": f"{T0 + 10_000 + len(self.posts):.6f}", "text": text, "metadata": metadata}
        self.threads.setdefault((channel, thread_ts), []).append(reply)
        self.posts.append((channel, thread_ts, text))
        return reply["ts"]

    def react(self, channel, ts, name):
        self._check("react")
        self.react_calls += 1
        self.reactions.add((channel, ts, name))


class FakeKube:
    def __init__(self):
        self.objects = {}
        self.configmap = {"state.json": "{}"}
        self.fail = False

    def get_object(self, kind, namespace, name):
        if self.fail:
            raise relay.KubeError("GET: HTTP 500")
        return self.objects.get((kind, namespace, name))

    def get_configmap(self, namespace, name):
        return None if self.configmap is None else {"data": dict(self.configmap)}

    def patch_configmap(self, namespace, name, data):
        self.configmap.update(data)

    def state(self):
        return json.loads(self.configmap["state.json"])


class Clock:
    def __init__(self, now=T0):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def env():
    slack, kube, clock = FakeSlack(), FakeKube(), Clock()
    secrets = {"bot_token": "xoxb-1", "cluster_channel": CLUSTER, "staging_channel": STAGING}

    def make():
        return relay.Relay(
            kube,
            "flux-system",
            "flux-relay-state",
            lambda: dict(secrets),
            lambda token: slack,
            clock,
        )

    return slack, kube, clock, secrets, make


KEY = ("Kustomization", "flux-system", "fmi-codes-staging")


def test_transient_failure_gets_one_reply_and_a_reaction(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    assert r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    assert slack.posts == []
    assert "Kustomization/flux-system/fmi-codes-staging" in kube.state()["incidents"]

    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    clock.now = T0 + 75
    r.tick()
    assert len(slack.posts) == 1
    channel, thread_ts, text = slack.posts[0]
    assert (channel, thread_ts) == (STAGING, f"{T0 + 1:.6f}")
    assert text.startswith("✅ Recovered <!date^")
    assert "Applied revision: main@sha1:abc" in text
    assert slack.reactions == {(STAGING, f"{T0 + 1:.6f}", "white_check_mark")}
    assert kube.state() == {"incidents": {}, "pending": [], "closing": []}

    clock.now = T0 + 90
    r.tick()
    assert len(slack.posts) == 1


def test_object_already_ready_when_first_checked_closes_at_once(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 50)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 60
    r.tick()
    assert len(slack.posts) == 1


def test_repeated_errors_share_one_thread_and_every_post_gets_a_reaction(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    for at in (T0, T0 + 300, T0 + 600):
        r.enqueue("staging", flux_event(at=at))
        slack.add(STAGING, flux_post(at + 1))
        clock.now = at + 5
        r.tick()
    incident = kube.state()["incidents"]["Kustomization/flux-system/fmi-codes-staging"]
    assert [p["ts"] for p in incident["posts"]] == [f"{T0 + d:.6f}" for d in (1, 301, 601)]

    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 700)
    clock.now = T0 + 720
    r.tick()
    assert len(slack.posts) == 1
    assert slack.posts[0][1] == f"{T0 + 1:.6f}"
    assert "3 error posts in this incident" in slack.posts[0][2]
    assert {ts for _, ts, _ in slack.reactions} == {f"{T0 + d:.6f}" for d in (1, 301, 601)}


@pytest.mark.parametrize("same_tick", [True, False])
def test_identical_events_claim_different_posts(env, same_tick):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event(at=T0))
    slack.add(STAGING, flux_post(T0 + 1))
    if not same_tick:
        clock.now = T0 + 5
        r.tick()
    r.enqueue("staging", flux_event(at=T0 + 30))
    slack.add(STAGING, flux_post(T0 + 31))
    clock.now = T0 + 35
    r.tick()
    posts = kube.state()["incidents"]["Kustomization/flux-system/fmi-codes-staging"]["posts"]
    assert sorted(p["ts"] for p in posts) == [f"{T0 + 1:.6f}", f"{T0 + 31:.6f}"]


def test_a_claimed_post_is_never_claimed_twice(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event(at=T0))
    r.enqueue("staging", flux_event(at=T0 + 2))
    slack.add(STAGING, flux_post(T0 + 1))
    slack.add(STAGING, flux_post(T0 + 40))
    clock.now = T0 + 45
    r.tick()
    posts = kube.state()["incidents"]["Kustomization/flux-system/fmi-codes-staging"]["posts"]
    assert sorted(p["ts"] for p in posts) == [f"{T0 + 1:.6f}", f"{T0 + 40:.6f}"]


def test_post_from_before_the_event_is_not_claimed_in_a_shared_scan(env):
    slack, kube, clock, _, make = env
    r = make()
    hr = ("HelmRelease", "flux-system", "kps")
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    kube.objects[hr] = flux_object(status="False", ltt=T0)
    r.enqueue("cluster", flux_event(at=T0))
    r.enqueue(
        "cluster", flux_event(kind="HelmRelease", name="kps", message="upgrade failed", at=T0 + 600)
    )
    slack.add(CLUSTER, flux_post(T0 + 1))
    slack.add(CLUSTER, flux_post(T0 + 100, kind="HelmRelease", name="kps", text="upgrade failed"))
    clock.now = T0 + 605
    r.tick()
    assert set(kube.state()["incidents"]) == {"Kustomization/flux-system/fmi-codes-staging"}


def test_restart_mid_incident_still_replies(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()

    restarted = make()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 400)
    clock.now = T0 + 420
    restarted.tick()
    assert len(slack.posts) == 1
    assert slack.posts[0][1] == f"{T0 + 1:.6f}"


def test_event_waiting_for_its_post_survives_a_restart(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    clock.now = T0 + 2
    r.tick()
    assert len(kube.state()["pending"]) == 1

    restarted = make()
    slack.add(STAGING, flux_post(T0 + 20))
    clock.now = T0 + 30
    restarted.tick()
    assert kube.state()["pending"] == []
    assert "Kustomization/flux-system/fmi-codes-staging" in kube.state()["incidents"]


def test_deleted_object_closes_with_its_own_reply(env):
    slack, kube, clock, _, make = env
    r = make()
    r.enqueue("staging", flux_event(name="alert-test"))
    slack.add(STAGING, flux_post(T0 + 1, name="alert-test"))
    clock.now = T0 + 5
    r.tick()
    assert len(slack.posts) == 1
    assert slack.posts[0][2].startswith("🗑️ `kustomization/alert-test` was deleted")
    assert len(slack.reactions) == 1
    assert kube.state()["incidents"] == {}


def test_error_that_never_reached_slack_gets_no_traffic(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    for now in (T0 + 15, T0 + 100, T0 + relay.FIND_WINDOW + 1):
        clock.now = now
        r.tick()
    assert kube.state() == {"incidents": {}, "pending": [], "closing": []}
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 400)
    clock.now = T0 + 500
    r.tick()
    assert slack.posts == [] and slack.reactions == set()


@pytest.mark.parametrize(
    "event",
    [
        flux_event(severity="info", message="Reconciliation finished in 1s, next run in 5m0s"),
        flux_event(kind="Bucket"),
        {
            "involvedObject": {"kind": "Kustomization", "namespace": "flux-system"},
            "severity": "error",
            "message": "x",
        },
        {"severity": "error"},
        "not an object",
    ],
)
def test_ignored_events(env, event):
    _, _, _, _, make = env
    assert make().enqueue("staging", event) is False


def test_unknown_route_is_ignored(env):
    _, _, _, _, make = env
    assert make().enqueue("prod", flux_event()) is False


def test_without_a_token_nothing_reaches_slack_until_one_is_set(env):
    slack, kube, clock, secrets, make = env
    secrets["bot_token"] = ""
    r = make()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    assert slack.posts == []
    assert len(kube.state()["pending"]) == 1

    secrets["bot_token"] = "xoxb-1"
    clock.now = T0 + 70
    r.tick()
    assert len(slack.posts) == 1


def test_each_route_reads_its_own_channel(env):
    slack, kube, clock, _, make = env
    r = make()
    hr = ("HelmRelease", "flux-system", "kps")
    kube.objects[hr] = flux_object(status="False", ltt=T0)
    r.enqueue("cluster", flux_event(kind="HelmRelease", name="kps", message="upgrade failed"))
    slack.add(STAGING, flux_post(T0 + 1, kind="HelmRelease", name="kps", text="upgrade failed"))
    clock.now = T0 + 5
    r.tick()
    assert kube.state()["incidents"] == {}

    slack.add(CLUSTER, flux_post(T0 + 6, kind="HelmRelease", name="kps", text="upgrade failed"))
    clock.now = T0 + 20
    r.tick()
    posts = kube.state()["incidents"]["HelmRelease/flux-system/kps"]["posts"]
    assert posts == [{"channel": CLUSTER, "ts": f"{T0 + 6:.6f}"}]


def test_missing_channel_id_drops_that_routes_events(env):
    slack, kube, clock, secrets, make = env
    secrets["staging_channel"] = ""
    r = make()
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    assert kube.state() == {"incidents": {}, "pending": [], "closing": []}


def test_another_clusters_post_is_never_claimed(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    slack.add(STAGING, flux_post(T0 - 600))
    slack.add(STAGING, flux_post(T0 + 1, text="a different failure"))
    r.enqueue("staging", flux_event())
    clock.now = T0 + 5
    r.tick()
    assert kube.state()["incidents"] == {}


def test_existing_reply_is_not_posted_twice(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    slack.threads[(STAGING, f"{T0 + 1:.6f}")] = [
        {"ts": "1.0", "metadata": {"event_type": relay.REPLY_EVENT_TYPE, "event_payload": {}}}
    ]
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    clock.now = T0 + 75
    r.tick()
    assert slack.posts == []
    assert len(slack.reactions) == 1
    assert kube.state()["incidents"] == {}


def test_slack_failure_on_close_retries_next_tick(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    slack.fail = True
    clock.now = T0 + 75
    r.tick()
    assert kube.state()["incidents"]
    slack.fail = False
    clock.now = T0 + 90
    r.tick()
    assert len(slack.posts) == 1
    assert kube.state()["incidents"] == {}


def test_unreadable_channel_retries_until_the_find_window_ends(env):
    slack, kube, clock, _, make = env
    r = make()
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    slack.fail = True
    clock.now = T0 + 5
    r.tick()
    assert len(kube.state()["pending"]) == 1
    clock.now = T0 + relay.FIND_WINDOW + 1
    r.tick()
    assert kube.state()["pending"] == []
    slack.fail = False
    r.tick()
    assert kube.state()["incidents"] == {}


def test_without_a_token_waiting_events_still_expire(env):
    slack, kube, clock, secrets, make = env
    secrets["bot_token"] = ""
    r = make()
    r.enqueue("staging", flux_event())
    clock.now = T0 + 5
    r.tick()
    assert len(kube.state()["pending"]) == 1
    clock.now = T0 + relay.FIND_WINDOW + 1
    r.tick()
    assert kube.state()["pending"] == []

    secrets["bot_token"] = "xoxb-1"
    slack.add(STAGING, flux_post(T0 + 1))
    r.tick()
    assert slack.posts == [] and kube.state()["incidents"] == {}


def test_waiting_events_are_capped(env):
    _, kube, clock, secrets, make = env
    secrets["bot_token"] = ""
    r = make()
    for i in range(relay.MAX_PENDING + 25):
        r.enqueue("staging", flux_event(message=f"failure {i}"))
    clock.now = T0 + 5
    r.tick()
    pending = kube.state()["pending"]
    assert len(pending) == relay.MAX_PENDING
    assert pending[-1]["message"] == f"failure {relay.MAX_PENDING + 24}"


def test_closest_post_wins_over_another_clusters_identical_one(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    slack.add(STAGING, flux_post(T0 - 5))
    slack.add(STAGING, flux_post(T0 + 1))
    r.enqueue("staging", flux_event(at=T0))
    clock.now = T0 + 5
    r.tick()
    posts = kube.state()["incidents"]["Kustomization/flux-system/fmi-codes-staging"]["posts"]
    assert [p["ts"] for p in posts] == [f"{T0 + 1:.6f}"]


@pytest.mark.parametrize("code", sorted(relay.CHANNEL_GONE))
def test_channel_gone_gives_the_incident_up(env, code):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    slack.errors["replies"] = code
    clock.now = T0 + 75
    r.tick()
    assert kube.state() == {"incidents": {}, "pending": [], "closing": []}
    clock.now = T0 + 90
    r.tick()
    assert slack.posts == []


def test_channel_gone_while_reacting_gives_the_reactions_up(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60)
    slack.errors["react"] = "is_archived"
    clock.now = T0 + 75
    r.tick()
    assert len(slack.posts) == 1
    assert kube.state()["closing"] == []


def test_deleted_first_post_still_gets_the_others_reacted(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    for at in (T0, T0 + 300):
        r.enqueue("staging", flux_event(at=at))
        slack.add(STAGING, flux_post(at + 1))
        clock.now = at + 5
        r.tick()
    slack.delete(STAGING, f"{T0 + 1:.6f}")
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 400)
    clock.now = T0 + 420
    r.tick()
    assert slack.posts == []
    assert (STAGING, f"{T0 + 301:.6f}", "white_check_mark") in slack.reactions
    assert kube.state()["incidents"] == {} and kube.state()["closing"] == []


def test_reactions_spread_over_ticks_and_keep_their_progress(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    n = relay.REACTIONS_PER_TICK * 2 + 5
    for i in range(n):
        at = T0 + i * 300
        r.enqueue("staging", flux_event(at=at))
        slack.add(STAGING, flux_post(at + 1))
        clock.now = at + 5
        r.tick()
    kube.objects[KEY] = flux_object(status="True", ltt=clock.now + 10)
    clock.now += 20
    r.tick()
    assert len(slack.posts) == 1 and slack.react_calls == relay.REACTIONS_PER_TICK
    assert f"{n} error posts in this incident" in slack.posts[0][2]

    slack.errors["react"] = "ratelimited"
    clock.now += 15
    r.tick()
    del slack.errors["react"]
    restarted = make()
    for _ in range(2):
        clock.now += 15
        restarted.tick()
    assert slack.react_calls == n
    assert len(slack.reactions) == n and len(slack.posts) == 1
    assert kube.state()["closing"] == []


def test_posts_beyond_the_cap_are_counted_not_listed(env, monkeypatch):
    slack, kube, clock, _, make = env
    monkeypatch.setattr(relay, "MAX_POSTS", 2)
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    for i in range(3):
        at = T0 + i * 300
        r.enqueue("staging", flux_event(at=at))
        slack.add(STAGING, flux_post(at + 1))
        clock.now = at + 5
        r.tick()
    incident = kube.state()["incidents"]["Kustomization/flux-system/fmi-codes-staging"]
    assert len(incident["posts"]) == 2 and incident["unlisted"] == 1
    kube.objects[KEY] = flux_object(status="True", ltt=clock.now + 10)
    clock.now += 20
    r.tick()
    assert "3 error posts in this incident" in slack.posts[0][2]


def test_health_follows_the_loop_not_one_slow_tick(env):
    _, _, clock, _, make = env
    r = make()
    r.tick()
    assert r.healthy()
    r.tick_started = clock.now
    clock.now += 5 * relay.TICK + 120
    assert r.healthy()
    clock.now = r.tick_started + relay.MAX_TICK
    assert not r.healthy()
    r.tick_started = None
    r.last_tick = clock.now
    clock.now += 5 * relay.TICK + 60
    assert not r.healthy()


def test_kube_failure_keeps_the_incident(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    kube.fail = True
    clock.now = T0 + 20
    r.tick()
    assert kube.state()["incidents"]
    assert slack.posts == []


def test_error_that_never_made_the_object_unready_closes_after_a_quiet_period(env):
    slack, kube, clock, _, make = env
    r = make()
    hr = ("HelmRelease", "flux-system", "kps")
    kube.objects[hr] = flux_object(status="True", ltt=T0 - 3600, message="Helm upgrade succeeded")
    r.enqueue("cluster", flux_event(kind="HelmRelease", name="kps", message="drift detected"))
    slack.add(CLUSTER, flux_post(T0 + 1, kind="HelmRelease", name="kps", text="drift detected"))
    clock.now = T0 + 5
    r.tick()
    clock.now = T0 + relay.QUIET_AFTER - 1
    r.tick()
    assert slack.posts == []
    clock.now = T0 + relay.QUIET_AFTER
    r.tick()
    assert len(slack.posts) == 1


def test_ready_for_an_older_generation_is_not_recovered(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="False", ltt=T0)
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 5
    r.tick()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60, generation=2, observed=1)
    clock.now = T0 + 75
    r.tick()
    assert slack.posts == []


def test_state_configmap_not_there_yet(env):
    slack, kube, clock, _, make = env
    kube.configmap = None
    r = make()
    r.enqueue("staging", flux_event())
    clock.now = T0 + 5
    r.tick()
    assert r.loaded is False and len(r.pending) == 1
    kube.configmap = {"state.json": "{}"}
    clock.now = T0 + 20
    r.tick()
    assert r.loaded is True


def test_corrupt_state_starts_empty(env):
    _, kube, clock, _, make = env
    kube.configmap = {"state.json": "{not json"}
    r = make()
    r.tick()
    assert r.loaded and r.incidents == {}


@pytest.mark.parametrize(
    "text",
    [
        "Deployment/fmi-codes-staging/backend & <frontend> not ready",
        "kustomize build failed: accumulating resources\nline two\nline three",
    ],
)
def test_post_matches_escaped_and_multiline_text(text):
    assert relay.post_matches(
        flux_post(T0, text=text), "kustomization/fmi-codes-staging.flux-system", text
    )


def test_same_first_line_is_not_enough():
    post = flux_post(T0, text="dry-run failed:\nConfigMap/a invalid")
    assert not relay.post_matches(
        post, "kustomization/fmi-codes-staging.flux-system", "dry-run failed:\nSecret/b invalid"
    )


def test_long_text_matches_when_either_side_was_cut():
    full = "x" * (relay.MAX_MESSAGE + 500)
    author = "kustomization/fmi-codes-staging.flux-system"
    assert relay.post_matches(flux_post(T0, text=full), author, full[: relay.MAX_MESSAGE])
    assert relay.post_matches(flux_post(T0, text=full[: relay.MATCH_PREFIX]), author, full)
    assert not relay.post_matches(flux_post(T0, text=full[: relay.MATCH_PREFIX - 1]), author, full)


def test_event_message_is_kept_short():
    long_message = "y" * (relay.MAX_MESSAGE * 3)
    assert len(relay.parse_event("staging", flux_event(message=long_message))["message"]) == (
        relay.MAX_MESSAGE
    )


def test_post_does_not_match_another_object():
    post = flux_post(T0, name="fmi-codes")
    assert not relay.post_matches(
        post, "kustomization/fmi-codes-staging.flux-system", "health check failed"
    )


GIT_KEY = ("GitRepository", "flux-system", "alert-test")
GIT_AUTHOR = "gitrepository/alert-test.flux-system"
LIVE_MESSAGE = (
    "failed to checkout and determine revision: unable to clone "
    "'ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git': "
    'couldn\'t find remote ref "refs/heads/does-not-exist"'
)
# Flux's post of LIVE_MESSAGE as conversations.history returned it in the staging live test.
LIVE_STORED = (
    "failed to checkout and determine revision: unable to clone "
    "'<ssh://git@github.com/fss-fmi/fmi-codes-website-2026.git>': "
    'couldn\'t find remote ref "refs/heads/does-not-exist"'
)


@pytest.mark.parametrize(
    "message, stored",
    [
        (LIVE_MESSAGE, LIVE_STORED),
        (
            "GET https://index.docker.io/v2/fssfmi/x/tags/list: UNAUTHORIZED",
            "GET <https://index.docker.io/v2/fssfmi/x/tags/list>: UNAUTHORIZED",
        ),
        ("cannot reach example.com", "cannot reach <http://example.com|example.com>"),
        ("mail ops@example.com", "mail <mailto:ops@example.com|ops@example.com>"),
        ("Deployment/backend <frontend> not ready", "Deployment/backend <frontend> not ready"),
    ],
    ids=["live-git-clone", "docker-url", "auto-link-label", "mailto", "unescaped-brackets"],
)
def test_post_matches_through_slack_link_markup(message, stored):
    post = flux_post(T0, kind="GitRepository", name="alert-test", stored=stored)
    assert relay.post_matches(post, GIT_AUTHOR, message)


def test_link_markup_does_not_hide_a_different_url():
    other = LIVE_STORED.replace("fss-fmi/", "someone-else/")
    post = flux_post(T0, kind="GitRepository", name="alert-test", stored=other)
    assert not relay.post_matches(post, GIT_AUTHOR, LIVE_MESSAGE)


def test_error_with_a_url_is_tracked_and_replied_to(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[GIT_KEY] = flux_object(status="False", ltt=T0)
    event = flux_event(kind="GitRepository", name="alert-test", message=LIVE_MESSAGE)
    assert r.enqueue("cluster", event)
    slack.add(
        CLUSTER, flux_post(T0 + 2, kind="GitRepository", name="alert-test", stored=LIVE_STORED)
    )
    clock.now = T0 + 5
    r.tick()
    assert "GitRepository/flux-system/alert-test" in kube.state()["incidents"]

    kube.objects[GIT_KEY] = flux_object(status="True", ltt=T0 + 60)
    clock.now = T0 + 75
    r.tick()
    assert [(channel, ts) for channel, ts, _ in slack.posts] == [(CLUSTER, f"{T0 + 2:.6f}")]
    assert slack.reactions == {(CLUSTER, f"{T0 + 2:.6f}", "white_check_mark")}


@pytest.mark.parametrize(
    "unit, count", [("<", 200_000), ("<a|", 100_000), ("<a", 100_000), ("a", 200_000)]
)
def test_plain_text_stays_linear_on_hostile_brackets(unit, count):
    text = unit * count if unit != "a" else "<" + unit * count
    started = time.perf_counter()
    relay.plain_text(text)
    assert time.perf_counter() - started < 2


def test_ready_condition_states():
    assert relay.ready_condition(flux_object(status="False"))[0] == "not_ready"
    assert relay.ready_condition(flux_object(status="Unknown"))[0] == "unknown"
    assert relay.ready_condition({"status": {}})[0] == "unknown"
    state, ltt, message = relay.ready_condition(flux_object(ltt=T0))
    assert (state, ltt, message) == ("ready", T0, "Applied revision: main@sha1:abc")


def test_reply_escapes_the_ready_message(env):
    slack, kube, clock, _, make = env
    r = make()
    kube.objects[KEY] = flux_object(status="True", ltt=T0 + 60, message="ok <@U123> & done")
    r.enqueue("staging", flux_event())
    slack.add(STAGING, flux_post(T0 + 1))
    clock.now = T0 + 70
    r.tick()
    assert "ok &lt;@U123&gt; &amp; done" in slack.posts[0][2]


def test_slack_react_ignores_already_reacted():
    def opener(req, timeout):
        return io.BytesIO(json.dumps({"ok": False, "error": "already_reacted"}).encode())

    relay.Slack("xoxb-1", opener=opener).react(CLUSTER, "1.0", "white_check_mark")


def test_slack_call_retries_rate_limits():
    calls = []

    def opener(req, timeout):
        calls.append(req)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "slow down", {"Retry-After": "2"}, None)
        return io.BytesIO(json.dumps({"ok": True, "ts": "5.0"}).encode())

    waits = []
    ts = relay.Slack("xoxb-1", opener=opener, sleep=waits.append).post(
        CLUSTER, "hi", "1.0", {"a": 1}
    )
    assert ts == "5.0" and waits == [2]
    body = calls[-1].data.decode()
    assert "metadata=%7B%22a%22%3A+1%7D" in body and "unfurl_links=false" in body


def test_kube_reads_objects_and_maps_404_to_none(tmp_path):
    (tmp_path / "token").write_text("sa-token\n")
    seen = []

    def opener(req, timeout):
        seen.append(req)
        if req.full_url.endswith("/missing"):
            raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)
        return io.BytesIO(b'{"kind": "ImageUpdateAutomation"}')

    kube = relay.Kube(base="https://api", sa_dir=str(tmp_path), opener=opener)
    assert kube.get_object("ImageUpdateAutomation", "flux-system", "fmi-codes") == {
        "kind": "ImageUpdateAutomation"
    }
    assert seen[0].full_url == (
        "https://api/apis/image.toolkit.fluxcd.io/v1/namespaces/flux-system/imageupdateautomations/fmi-codes"
    )
    assert seen[0].headers["Authorization"] == "Bearer sa-token"
    assert kube.get_object("Kustomization", "flux-system", "missing") is None


def test_read_secrets_missing_files_are_empty(tmp_path):
    (tmp_path / "bot_token").write_text("xoxb-x\n")
    assert relay.read_secrets(str(tmp_path)) == {
        "bot_token": "xoxb-x",
        "cluster_channel": "",
        "staging_channel": "",
    }


def test_http_endpoint(env):
    _, _, _, _, make = env
    r = make()
    server = relay.http.server.ThreadingHTTPServer(("127.0.0.1", 0), relay.make_handler(r))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def send(path, body=None):
        data = body if body is None or isinstance(body, bytes) else json.dumps(body).encode()
        req = urllib.request.Request(base + path, data=data, method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            return e.code

    try:
        assert send("/healthz") == 200
        assert send("/staging", flux_event()) == 202
        assert send("/cluster", flux_event(severity="info")) == 202
        assert send("/prod", flux_event()) == 404
        assert send("/other") == 404
        assert send("/staging", b"{not json") == 400
    finally:
        server.shutdown()
    assert r.inbox.qsize() == 1


# The Flux wiring: each relay Alert must see exactly the errors its Slack Alert posts.

NOTIFICATIONS = ROOT / "infra" / "k8s" / "flux" / "notifications.yaml"


def _documents(kind: str) -> dict:
    docs = {}
    for doc in NOTIFICATIONS.read_text(encoding="utf-8").split("\n---\n"):
        if re.search(rf"^kind: {kind}$", doc, re.M):
            name = re.search(r"^  name: (\S+)$", doc, re.M).group(1)
            docs[name] = doc
    return docs


def _alert_spec(doc: str) -> str:
    spec = doc.split("\nspec:\n", 1)[1]
    spec = re.sub(r"^  providerRef:\n    name: \S+\n", "", spec, flags=re.M)
    return "\n".join(line for line in spec.splitlines() if not line.lstrip().startswith("#"))


@pytest.mark.parametrize(
    "slack_alert, relay_alert", [("slack", "flux-relay"), ("slack-staging", "flux-relay-staging")]
)
def test_relay_alerts_mirror_the_slack_alerts(slack_alert, relay_alert):
    alerts = _documents("Alert")
    assert _alert_spec(alerts[relay_alert]) == _alert_spec(alerts[slack_alert])
    assert f"providerRef:\n    name: {relay_alert}\n" in alerts[relay_alert]


@pytest.mark.parametrize(
    "provider, route", [("flux-relay", "cluster"), ("flux-relay-staging", "staging")]
)
def test_relay_providers_point_at_the_relay_service(provider, route):
    doc = _documents("Provider")[provider]
    assert "type: generic" in doc
    service = (ROOT / "infra" / "k8s" / "base" / "flux-relay" / "service.yaml").read_text(
        encoding="utf-8"
    )
    port = re.search(r"^    - name: http\n      port: (\d+)$", service, re.M).group(1)
    assert f"address: http://flux-relay.flux-system.svc.cluster.local:{port}/{route}" in doc
    assert route in relay.ROUTES


def test_only_the_slack_and_relay_alerts_exist():
    assert set(_documents("Alert")) == {
        "slack",
        "slack-staging",
        "flux-relay",
        "flux-relay-staging",
    }
