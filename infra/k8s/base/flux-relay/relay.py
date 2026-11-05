"""Flux Relay: replies "recovered" in the Slack thread of a Flux error.

Flux's own Slack Providers post errors through incoming webhooks, which can't
reply or react. Two generic Providers send the same errors here, at /cluster
or /staging, the split those Providers use. The relay finds the error's post
in that channel, keeps the open incident in a ConfigMap and watches the
object's Ready condition. Once the object is ready again it replies in the
first post's thread and adds a reaction to every post of the incident.

Recovery is read from the object, not from Flux's info events: a HelmRelease
that comes back in sync without a Helm action emits none. The relay only acts
on errors its own cluster reported and claims the matching post closest in
time to each one. A Flux post doesn't say which cluster sent it, so when two
clusters share a channel and the same object fails with the same message on
both within seconds, they can still swap posts.

Stdlib only: it runs from a ConfigMap on a stock python image.
"""

import http.server
import json
import logging
import os
import queue
import re
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

logger = logging.getLogger("flux-relay")

SLACK_API = "https://slack.com/api/"
KUBE_API = "https://kubernetes.default.svc"
SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
ROUTES = ("cluster", "staging")
REPLY_EVENT_TYPE = "flux_relay_recovery"
REACTION = "white_check_mark"
MAX_BODY = 1 << 20

KINDS = {
    "Kustomization": ("kustomize.toolkit.fluxcd.io/v1", "kustomizations"),
    "HelmRelease": ("helm.toolkit.fluxcd.io/v2", "helmreleases"),
    "GitRepository": ("source.toolkit.fluxcd.io/v1", "gitrepositories"),
    "HelmRepository": ("source.toolkit.fluxcd.io/v1", "helmrepositories"),
    "HelmChart": ("source.toolkit.fluxcd.io/v1", "helmcharts"),
    "ImageRepository": ("image.toolkit.fluxcd.io/v1", "imagerepositories"),
    "ImagePolicy": ("image.toolkit.fluxcd.io/v1", "imagepolicies"),
    "ImageUpdateAutomation": ("image.toolkit.fluxcd.io/v1", "imageupdateautomations"),
}

# Flux posts to Slack and to the relay in parallel, so the post may show up a little after
# the event; notification-controller retries a failing webhook for about a minute more.
FIND_WINDOW = 180
# How much earlier than the event's (whole-second) timestamp its post may be stamped, for clock
# skew between the node and Slack.
POST_EARLY = 30
# An error that never made the object unready (a Helm drift, a failed prune) has no
# transition to wait for. Flux reposts a lasting error every ~5 minutes, so this long
# without a new post while Ready means it stopped.
QUIET_AFTER = 900
# Slack may cut a very long attachment and the relay keeps only MAX_MESSAGE characters of an
# event, so texts this long that agree up to the shorter one count as the same.
MATCH_PREFIX = 2000
MAX_MESSAGE = 4000
# Bounds on what the state ConfigMap (1 MiB) holds and on one tick's Slack calls.
MAX_PENDING = 100
MAX_POSTS = 200
REACTIONS_PER_TICK = 20
TICK = 15
# A tick that waits out Slack rate limits is still alive; only one stuck this long is not.
MAX_TICK = 600
MAX_HISTORY_PAGES = 5
MAX_RETRIES = 3
# Slack returns a URL in a post as <target> or <target|label>, while the Flux event has the
# plain text. The classes exclude < and >, so no scan runs past the next bracket: linear time.
SLACK_LINK = re.compile(r"<([^<>|]*)(?:\|([^<>]*))?>")
# Errors that retrying won't fix: the incident's channel is gone or closed to the bot.
CHANNEL_GONE = {"channel_not_found", "is_archived", "not_in_channel"}
# The post itself was deleted.
POST_GONE = {"thread_not_found", "message_not_found"}


class SlackError(Exception):
    def __init__(self, message: str, code: str = ""):
        super().__init__(message)
        self.code = code


class KubeError(Exception):
    pass


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def unescape(text: str) -> str:
    return text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def author_name(kind: str, name: str, namespace: str) -> str:
    """The author line Flux's Slack notifier puts on every post."""
    return f"{kind.lower()}/{name}.{namespace}"


def parse_time(value) -> float | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def slack_date(epoch: float) -> str:
    """A timestamp each reader sees in their own time zone."""
    iso = datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"<!date^{int(epoch)}^{{date_short_pretty}} {{time}}|{iso}>"


def plain_text(text: str) -> str:
    """Text as a reader sees it: entities unescaped, link markup reduced to label or target.

    Applied to both sides, so an event message whose own < and > Slack read as markup still
    matches its post.
    """
    return SLACK_LINK.sub(
        lambda m: m.group(1) if m.group(2) is None else m.group(2), unescape(text)
    )


def same_text(posted: str, text: str) -> bool:
    if posted == text:
        return True
    n = min(len(posted), len(text))
    return n >= MATCH_PREFIX and posted[:n] == text[:n]


def post_matches(message: dict, author: str, text: str) -> bool:
    text = plain_text(text)
    for attachment in message.get("attachments") or []:
        if attachment.get("author_name") == author and same_text(
            plain_text(attachment.get("text") or ""), text
        ):
            return True
    return False


def ready_condition(obj: dict) -> tuple[str, float | None, str]:
    """("ready" | "not_ready" | "unknown", lastTransitionTime, message) of the Ready condition.

    "unknown" covers a reconcile in progress and a spec the controller hasn't caught up with.
    """
    status = obj.get("status") or {}
    generation = (obj.get("metadata") or {}).get("generation")
    observed = status.get("observedGeneration")
    for condition in status.get("conditions") or []:
        if condition.get("type") != "Ready":
            continue
        ltt = parse_time(condition.get("lastTransitionTime"))
        message = condition.get("message") or ""
        if condition.get("status") == "False":
            return "not_ready", ltt, message
        if condition.get("status") == "True" and (
            generation is None or observed is None or observed >= generation
        ):
            return "ready", ltt, message
        return "unknown", ltt, message
    return "unknown", None, ""


def parse_event(route: str, event) -> dict | None:
    """The fields the relay keeps from a Flux event, or None for anything it ignores."""
    if route not in ROUTES or not isinstance(event, dict) or event.get("severity") != "error":
        return None
    obj = event.get("involvedObject") or {}
    kind, name, namespace = obj.get("kind"), obj.get("name"), obj.get("namespace")
    message = event.get("message")
    if kind not in KINDS or not all(isinstance(v, str) and v for v in (name, namespace, message)):
        return None
    return {
        "route": route,
        "kind": kind,
        "name": name,
        "namespace": namespace,
        "message": message[:MAX_MESSAGE],
        "time": parse_time(event.get("timestamp")),
    }


def _form_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict):
        return json.dumps(value)
    return str(value)


def _retry_after(value) -> int:
    try:
        return max(1, min(int(value), 30))
    except (TypeError, ValueError):
        return 1


class Slack:
    def __init__(self, token: str, opener=urllib.request.urlopen, sleep=time.sleep):
        self._token = token
        self._open = opener
        self._sleep = sleep

    def call(self, method: str, **params) -> dict:
        body = urllib.parse.urlencode(
            {k: _form_value(v) for k, v in params.items() if v is not None}
        ).encode("utf-8")
        for attempt in range(MAX_RETRIES + 1):
            req = urllib.request.Request(
                SLACK_API + method,
                data=body,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                method="POST",
            )
            try:
                with self._open(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < MAX_RETRIES:
                    self._sleep(_retry_after(e.headers.get("Retry-After")))
                    continue
                raise SlackError(f"{method}: HTTP {e.code}") from None
            except (urllib.error.URLError, TimeoutError) as e:
                raise SlackError(f"{method}: {getattr(e, 'reason', e)}") from None
            if not data.get("ok"):
                error = data.get("error", "unknown_error")
                raise SlackError(f"{method}: {error}", error)
            return data
        raise SlackError(f"{method}: still rate limited after {MAX_RETRIES} retries")

    def _pages(self, method: str, **params):
        cursor = None
        for _ in range(MAX_HISTORY_PAGES):
            data = self.call(method, limit=200, include_all_metadata=True, cursor=cursor, **params)
            yield from data.get("messages", [])
            cursor = (data.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                return

    def history(self, channel: str, oldest: float) -> list:
        return list(self._pages("conversations.history", channel=channel, oldest=f"{oldest:.6f}"))

    def replies(self, channel: str, ts: str) -> list:
        return list(self._pages("conversations.replies", channel=channel, ts=ts))

    def post(self, channel: str, text: str, thread_ts: str, metadata: dict) -> str:
        data = self.call(
            "chat.postMessage",
            channel=channel,
            text=text,
            thread_ts=thread_ts,
            metadata=metadata,
            unfurl_links=False,
            unfurl_media=False,
        )
        return data["ts"]

    def react(self, channel: str, ts: str, name: str) -> None:
        try:
            self.call("reactions.add", channel=channel, timestamp=ts, name=name)
        except SlackError as e:
            if e.code != "already_reacted" and e.code not in POST_GONE:
                raise


class Kube:
    def __init__(self, base=KUBE_API, sa_dir=SA_DIR, opener=None):
        self._base = base
        self._sa_dir = sa_dir
        if opener is None:
            ctx = ssl.create_default_context(cafile=os.path.join(sa_dir, "ca.crt"))
            handler = urllib.request.HTTPSHandler(context=ctx)
            opener = urllib.request.build_opener(handler).open
        self._open = opener

    def _request(self, method: str, path: str, body=None, content_type="application/json"):
        # Projected service account tokens rotate, so read it per request.
        with open(os.path.join(self._sa_dir, "token"), encoding="utf-8") as f:
            token = f.read().strip()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = content_type
        req = urllib.request.Request(self._base + path, data=data, headers=headers, method=method)
        try:
            with self._open(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise KubeError(f"{method} {path}: HTTP {e.code}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise KubeError(f"{method} {path}: {getattr(e, 'reason', e)}") from None

    def get_object(self, kind: str, namespace: str, name: str) -> dict | None:
        api, plural = KINDS[kind]
        return self._request("GET", f"/apis/{api}/namespaces/{namespace}/{plural}/{name}")

    def get_configmap(self, namespace: str, name: str) -> dict | None:
        return self._request("GET", f"/api/v1/namespaces/{namespace}/configmaps/{name}")

    def patch_configmap(self, namespace: str, name: str, data: dict) -> None:
        result = self._request(
            "PATCH",
            f"/api/v1/namespaces/{namespace}/configmaps/{name}",
            {"data": data},
            "application/merge-patch+json",
        )
        if result is None:
            raise KubeError(f"configmap {namespace}/{name} not found")


def read_secrets(secret_dir: str) -> dict:
    values = {}
    for key in ("bot_token", "cluster_channel", "staging_channel"):
        try:
            with open(os.path.join(secret_dir, key), encoding="utf-8") as f:
                values[key] = f.read().strip()
        except OSError:
            values[key] = ""
    return values


class Relay:
    """State: pending events waiting for their post, open incidents by object and closing
    incidents (already replied to) whose posts still need a reaction."""

    def __init__(
        self, kube, namespace: str, state_name: str, secrets, slack_factory=Slack, clock=time.time
    ):
        self.kube = kube
        self.namespace = namespace
        self.state_name = state_name
        self.secrets = secrets
        self.slack_factory = slack_factory
        self.clock = clock
        self.inbox = queue.Queue()
        self.incidents = {}
        self.pending = []
        self.closing = []
        self.loaded = False
        self.dirty = False
        self.last_tick = clock()
        self.tick_started = None
        self._token = None
        self._slack = None
        self._warned = set()

    def enqueue(self, route: str, event) -> bool:
        parsed = parse_event(route, event)
        if parsed is None:
            return False
        parsed["received"] = self.clock()
        if parsed["time"] is None:
            parsed["time"] = parsed["received"]
        self.inbox.put(parsed)
        return True

    def _warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            logger.warning(message)

    def load(self) -> None:
        cm = self.kube.get_configmap(self.namespace, self.state_name)
        if cm is None:
            raise KubeError(f"configmap {self.namespace}/{self.state_name} not found")
        raw = (cm.get("data") or {}).get("state.json") or "{}"
        try:
            state = json.loads(raw)
        except ValueError:
            logger.error("State ConfigMap holds invalid JSON; starting empty")
            state = {}
        self.incidents = state.get("incidents") or {}
        self.closing = state.get("closing") or []
        self.pending = (state.get("pending") or []) + self.pending
        self.loaded = True

    def save(self) -> None:
        state = {"incidents": self.incidents, "pending": self.pending, "closing": self.closing}
        self.kube.patch_configmap(
            self.namespace, self.state_name, {"state.json": json.dumps(state, sort_keys=True)}
        )
        self.dirty = False

    def tick(self) -> None:
        self.tick_started = self.clock()
        try:
            self._tick()
        finally:
            self.tick_started = None
            self.last_tick = self.clock()

    def _tick(self) -> None:
        while True:
            try:
                self.pending.append(self.inbox.get_nowait())
                self.dirty = True
            except queue.Empty:
                break
        if len(self.pending) > MAX_PENDING:
            logger.warning("Dropping %d waiting events", len(self.pending) - MAX_PENDING)
            self.pending = self.pending[-MAX_PENDING:]
        try:
            if not self.loaded:
                self.load()
        except KubeError as e:
            self._warn_once("load", f"Cannot load the relay state yet, retrying every {TICK}s: {e}")
            return

        secrets = self.secrets()
        if not secrets["bot_token"]:
            self._warn_once(
                "token", "No Slack bot token in the flux-relay-slack Secret; idle until one is set"
            )
            self._expire_pending()
            self._save_if_dirty()
            return
        if secrets["bot_token"] != self._token:
            self._token = secrets["bot_token"]
            self._slack = self.slack_factory(self._token)
        channels = {"cluster": secrets["cluster_channel"], "staging": secrets["staging_channel"]}

        self._match_pending(channels)
        self._check_incidents()
        self._react_closing()
        self._save_if_dirty()

    def _save_if_dirty(self) -> None:
        if not self.dirty:
            return
        try:
            self.save()
        except KubeError as e:
            logger.error("Cannot save the relay state: %s", e)

    def _expire_pending(self) -> None:
        now = self.clock()
        keep = [e for e in self.pending if now - e["received"] < FIND_WINDOW]
        if len(keep) != len(self.pending):
            self.pending = keep
            self.dirty = True

    def _claimed(self) -> set:
        posts = [p for inc in self.incidents.values() for p in inc["posts"]]
        posts += [p for c in self.closing for p in c["posts"]]
        return {(p["channel"], p["ts"]) for p in posts}

    def _match_pending(self, channels: dict) -> None:
        if not self.pending:
            return
        now = self.clock()
        by_channel = {}
        keep = []
        for event in self.pending:
            channel = channels.get(event["route"])
            if not channel:
                self._warn_once(
                    f"channel:{event['route']}",
                    f"No {event['route']}_channel in the flux-relay-slack Secret; "
                    f"{event['route']} errors get no recovery reply",
                )
                continue
            by_channel.setdefault(channel, []).append(event)

        claimed = self._claimed()
        for channel, events in by_channel.items():
            try:
                history = self._slack.history(channel, min(e["time"] for e in events) - POST_EARLY)
            except SlackError as e:
                # not_in_channel and the like don't fix themselves, so the find window still applies.
                logger.error("Cannot read channel %s: %s", channel, e)
                keep.extend(ev for ev in events if now - ev["received"] < FIND_WINDOW)
                continue
            for event in sorted(events, key=lambda e: e["time"]):
                author = author_name(event["kind"], event["name"], event["namespace"])
                candidates = [
                    m
                    for m in history
                    if (channel, m.get("ts")) not in claimed
                    and float(m.get("ts", 0)) >= event["time"] - POST_EARLY
                    and post_matches(m, author, event["message"])
                ]
                if candidates:
                    # The closest in time: a repeat of the same error, or another cluster's
                    # identical post, is further away than this event's own post.
                    ts = min(candidates, key=lambda m: abs(float(m["ts"]) - event["time"]))["ts"]
                    claimed.add((channel, ts))
                    self._add_post(event, channel, ts)
                elif now - event["received"] < FIND_WINDOW:
                    keep.append(event)
                else:
                    logger.info("No Slack post found for %s; it gets no recovery reply", author)
        if keep != self.pending:
            self.dirty = True
        self.pending = keep

    def _add_post(self, event: dict, channel: str, ts: str) -> None:
        key = f"{event['kind']}/{event['namespace']}/{event['name']}"
        incident = self.incidents.get(key)
        if incident is None:
            incident = self.incidents[key] = {
                "kind": event["kind"],
                "namespace": event["namespace"],
                "name": event["name"],
                "posts": [],
                "unlisted": 0,
                "start": event["time"],
                "last": event["time"],
                "seen_not_ready": False,
            }
            logger.info("Tracking %s from its error post %s", key, ts)
        if len(incident["posts"]) < MAX_POSTS:
            incident["posts"].append({"channel": channel, "ts": ts})
        else:
            incident["unlisted"] = incident.get("unlisted", 0) + 1
        incident["last"] = max(incident["last"], event["time"])
        self.dirty = True

    def _check_incidents(self) -> None:
        now = self.clock()
        for key, incident in list(self.incidents.items()):
            try:
                obj = self.kube.get_object(
                    incident["kind"], incident["namespace"], incident["name"]
                )
            except KubeError as e:
                logger.error("Cannot read %s: %s", key, e)
                continue
            if obj is None:
                text = (
                    f"🗑️ `{incident['kind'].lower()}/{incident['name']}` was deleted "
                    f"{slack_date(now)}, so nothing is left to recover."
                )
                self._close(key, incident, text)
                continue
            state, ltt, message = ready_condition(obj)
            if state == "not_ready":
                if not incident["seen_not_ready"]:
                    incident["seen_not_ready"] = True
                    self.dirty = True
                continue
            if state != "ready":
                continue
            if (
                incident["seen_not_ready"]
                or (ltt is not None and ltt > incident["start"])
                or now - incident["last"] >= QUIET_AFTER
            ):
                text = f"✅ Recovered {slack_date(now)}"
                if message:
                    text += f" · {escape(message)}"
                count = len(incident["posts"]) + incident.get("unlisted", 0)
                if count > 1:
                    text += f" · {count} error posts in this incident"
                self._close(key, incident, text)

    def _close(self, key: str, incident: dict, text: str) -> None:
        """Reply under the first post, then hand the posts to _react_closing."""
        parent = incident["posts"][0]
        try:
            try:
                replies = self._slack.replies(parent["channel"], parent["ts"])
            except SlackError as e:
                if e.code not in POST_GONE:
                    raise
                logger.info("The first post of %s was deleted; no reply, only reactions", key)
            else:
                if not any(
                    (m.get("metadata") or {}).get("event_type") == REPLY_EVENT_TYPE for m in replies
                ):
                    self._slack.post(
                        parent["channel"],
                        text,
                        parent["ts"],
                        {"event_type": REPLY_EVENT_TYPE, "event_payload": {"object": key}},
                    )
        except SlackError as e:
            if e.code in CHANNEL_GONE:
                logger.warning("Giving up on %s: %s", key, e)
                del self.incidents[key]
                self.dirty = True
            else:
                logger.error("Cannot reply for %s yet: %s", key, e)
            return
        logger.info("Replied for %s", key)
        self.closing.append({"key": key, "posts": incident["posts"]})
        del self.incidents[key]
        self.dirty = True

    def _react_closing(self) -> None:
        """React to at most REACTIONS_PER_TICK posts, remembering which are done, so a long
        incident under Slack's rate limit finishes over a few ticks instead of starting over."""
        budget = REACTIONS_PER_TICK
        for entry in list(self.closing):
            try:
                for post in entry["posts"]:
                    if post.get("done"):
                        continue
                    if budget == 0:
                        return
                    self._slack.react(post["channel"], post["ts"], REACTION)
                    post["done"] = True
                    budget -= 1
                    self.dirty = True
            except SlackError as e:
                if e.code in CHANNEL_GONE:
                    logger.warning("Giving up on the reactions for %s: %s", entry["key"], e)
                    self.closing.remove(entry)
                    self.dirty = True
                    continue
                logger.error("Cannot react for %s yet: %s", entry["key"], e)
                return
            logger.info("Closed %s", entry["key"])
            self.closing.remove(entry)
            self.dirty = True

    def healthy(self) -> bool:
        started = self.tick_started
        if started is not None:
            return self.clock() - started < MAX_TICK
        return self.clock() - self.last_tick < 5 * TICK + 60


def make_handler(relay: Relay):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                self._reply(200 if relay.healthy() else 503)
            else:
                self._reply(404)

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if not 0 < length <= MAX_BODY:
                self.close_connection = True
                self._reply(413 if length > MAX_BODY else 400)
                return
            # Read the body before answering, even for a bad path, so the client isn't cut off
            # mid-send.
            body = self.rfile.read(length)
            route = self.path.strip("/")
            if route not in ROUTES:
                self._reply(404)
                return
            try:
                event = json.loads(body)
            except ValueError:
                self._reply(400)
                return
            relay.enqueue(route, event)
            self._reply(202)

        def _reply(self, code: int):
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    return Handler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    with open(os.path.join(SA_DIR, "namespace"), encoding="utf-8") as f:
        namespace = f.read().strip()
    secret_dir = os.environ.get("SECRET_DIR", "/etc/flux-relay/slack")
    relay = Relay(
        Kube(),
        namespace,
        os.environ.get("STATE_CONFIGMAP", "flux-relay-state"),
        lambda: read_secrets(secret_dir),
    )
    server = http.server.ThreadingHTTPServer(
        ("", int(os.environ.get("PORT", "8000"))), make_handler(relay)
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Listening on %s", server.server_address)
    while True:
        try:
            relay.tick()
        except Exception:
            logger.exception("Tick failed")
        time.sleep(TICK)


if __name__ == "__main__":
    main()
