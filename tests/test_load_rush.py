"""The registration rush script's pass/fail verdict and HTTP client (tests/load/)."""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "registration_rush", Path(__file__).parent / "load" / "registration_rush.py"
)
rush = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rush)

LIMITS = rush.Limits(register_p95=3.0, register_p99=10.0)


def results_with(*samples, lags=(0.01,), problems=()):
    results = rush.Results()
    results.samples.extend(samples)
    results.start_lags.extend(lags)
    results.problems.extend(problems)
    return results


def ok(name="register", status=201, seconds=0.5):
    return rush.Sample(name, status, seconds, expected=True)


def test_clean_run_passes():
    assert rush.verdict(results_with(ok(), ok("me", 200), ok("me_anonymous", 401)), LIMITS) == []


@pytest.mark.parametrize(
    ("sample", "label"),
    [
        (rush.Sample("join_team", 502, 0.1, expected=False), "5xx responses"),
        (rush.Sample("login", 429, 0.1, expected=False), "429 responses"),
        (rush.Sample("me", 0, 75.0, expected=False, error="TimeoutError"), "no answer"),
        (rush.Sample("join_team", 400, 0.1, expected=False), "unexpected"),
    ],
)
def test_each_bad_status_fails_the_run(sample, label):
    failures = rush.verdict(results_with(ok(), sample), LIMITS)
    assert len(failures) == 1
    assert label in failures[0] and sample.name in failures[0]


def test_an_expected_4xx_does_not_fail_the_run():
    member_read = rush.Sample("mentor_preferences", 403, 0.1, expected=True)
    assert rush.verdict(results_with(ok(), member_read), LIMITS) == []


def test_a_5xx_fails_the_run_even_when_listed_as_expected():
    assert rush.verdict(results_with(ok(), rush.Sample("me", 503, 0.1, True)), LIMITS)


def test_slow_registrations_fail_on_p95_and_p99():
    fast = [ok(seconds=0.5) for _ in range(90)]
    slow = [ok(seconds=20.0) for _ in range(10)]
    failures = rush.verdict(results_with(*fast, *slow), LIMITS)
    assert any(f.startswith("register p95") for f in failures)
    assert any(f.startswith("register p99") for f in failures)


def test_a_failed_registration_counts_towards_its_percentiles():
    timed_out = rush.Sample("register", 0, 75.0, expected=False, error="TimeoutError")
    failures = rush.verdict(results_with(timed_out), LIMITS)
    assert any(f.startswith("register p95") for f in failures)


def test_no_registration_fails_the_run():
    assert rush.verdict(results_with(ok("me", 200)), LIMITS) == ["no registration was sent"]


def test_a_late_start_fails_the_run_as_understated():
    failures = rush.verdict(results_with(ok(), lags=(0.0, 1.5)), LIMITS)
    assert len(failures) == 1 and "fell behind" in failures[0]


def test_scenario_problems_fail_the_run():
    assert rush.verdict(results_with(ok(), problems=["user 4 crashed"]), LIMITS) == [
        "user 4 crashed"
    ]


def test_percentile_is_exact_and_handles_one_sample():
    values = [float(v) for v in range(1, 101)]
    assert rush.percentile(values, 95) == pytest.approx(95.05)
    assert rush.percentile([2.5], 99) == 2.5


@pytest.mark.parametrize(
    ("headers", "token"),
    [
        (["token=abc.def; HttpOnly; Path=/; SameSite=Lax; Secure; Max-Age=259200"], "abc.def"),
        (["other=1; Path=/", "token=xyz; Path=/"], "xyz"),
        (["token=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax"], None),
        ([], None),
    ],
)
def test_token_from_set_cookie(headers, token):
    assert rush.token_from(headers) == token


class _Handler(BaseHTTPRequestHandler):
    """HTTP/1.1 with keep-alive; the path picks how the answer goes wrong."""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _answer(self, status, payload, extra_headers=()):
        self.send_response(status)
        for name, value in extra_headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.server.hits.append((id(self.connection), self.path))
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        payload = json.dumps({"got": body, "cookie": self.headers.get("Cookie")}).encode()
        self._answer(
            201,
            payload,
            [
                ("Set-Cookie", "token=new-token; HttpOnly; Path=/; Secure"),
                ("Content-Type", "application/json"),
            ],
        )

    def do_GET(self):
        self.server.hits.append((id(self.connection), self.path))
        if self.path == "/503":
            self._answer(503, b"<html/>\n\n")
        elif self.path == "/ok":
            self._answer(200, b"{}", [("Content-Type", "application/json")])
        elif self.path == "/ok-then-drop":
            # Closes without a Connection: close header, as nginx does at keepalive_timeout.
            self._answer(200, b"{}")
            self.close_connection = True
        elif self.path == "/cut":
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"{")
            self.close_connection = True
        elif self.path == "/hangup":
            self.close_connection = True


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.hits = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    thread.join()


def _url(httpd):
    return f"http://127.0.0.1:{httpd.server_port}"


def test_client_sends_the_token_by_hand_and_reads_the_new_one(server):
    results = rush.Results()
    reply = rush.Client(_url(server), 5, results).call(
        "register", "POST", "/x", token="old", body={"a": 1}, expect=(201,)
    )
    assert reply.status == 201
    assert reply.body == {"got": {"a": 1}, "cookie": "token=old"}
    assert reply.token == "new-token"
    assert [(s.name, s.status, s.expected) for s in results.samples] == [("register", 201, True)]


def test_client_records_an_error_status_with_a_non_json_body(server):
    results = rush.Results()
    reply = rush.Client(_url(server), 5, results).call("config", "GET", "/503")
    assert (reply.status, reply.body, reply.token) == (503, None, None)
    assert results.samples[0].expected is False


def test_client_keeps_one_connection_per_thread(server):
    client = rush.Client(_url(server), 5, rush.Results())
    for _ in range(3):
        assert client.call("config", "GET", "/ok").status == 200
    other = threading.Thread(target=client.call, args=("config", "GET", "/ok"))
    other.start()
    other.join()
    connections = [conn for conn, _ in server.hits]
    assert len(set(connections[:3])) == 1
    assert connections[3] != connections[0]


def test_client_resends_once_on_an_idle_connection_the_server_closed(server):
    results = rush.Results()
    client = rush.Client(_url(server), 5, results)
    client.call("config", "GET", "/ok-then-drop")
    reply = client.call("config", "GET", "/ok")
    assert reply.status == 200
    assert [(s.status, s.expected, s.error) for s in results.samples] == [
        (200, True, ""),
        (200, True, ""),
    ]
    assert [path for _, path in server.hits] == ["/ok-then-drop", "/ok"]


def test_client_never_resends_on_a_fresh_connection(server):
    results = rush.Results()
    reply = rush.Client(_url(server), 5, results).call("register", "GET", "/hangup")
    assert reply.status == 0
    assert results.samples[0].error and results.samples[0].expected is False
    assert [path for _, path in server.hits] == ["/hangup"]


def test_a_body_cut_off_after_its_status_line_is_no_answer(server):
    results = rush.Results()
    reply = rush.Client(_url(server), 5, results).call("register", "GET", "/cut")
    assert reply.status == 0
    assert "IncompleteRead" in results.samples[0].error
    assert any("no answer" in f for f in rush.verdict(results, LIMITS))


def test_client_records_no_answer_as_status_zero():
    results = rush.Results()
    reply = rush.Client("http://127.0.0.1:1", 2, results).call("me", "GET", "/api/auth/me")
    assert reply.status == 0
    assert results.samples[0].error


# ── The user's flow, against a scripted client ──────────────────────────────


class _ScriptedClient:
    def __init__(self, replies):
        self.replies = replies
        self.calls = []

    def call(self, name, method, path, **kwargs):
        self.calls.append(name)
        return self.replies.get(name, rush.Response(200, {}, None))


def _user(replies, index=1):
    results = rush.Results()
    client = _ScriptedClient(replies)
    scenario = rush.Scenario(
        client=client,
        results=results,
        run_id="abc123",
        password="p" * 16,
        university_id=1,
        specialty_id=1,
        team_size=3,
        relogin_share=0.0,
        linger_seconds=0.0,
        config_poll_seconds=30.0,
        team_reloads=0,
        seat_wait_seconds=0.1,
        seed=1,
    )
    return rush.User(scenario, index), client, results


def test_a_registration_without_a_token_is_a_problem():
    user, _, results = _user({"register": rush.Response(201, {"user_id": 5}, None)})
    assert user.register() is False
    assert results.problems == ["user 1 registered but got no token or no body"]


def test_a_refused_registration_is_left_to_its_sample():
    user, _, results = _user({"register": rush.Response(409, {}, None)})
    assert user.register() is False
    assert results.problems == []


def test_a_login_without_a_token_is_a_problem():
    user, _, results = _user({"login": rush.Response(200, {}, None)})
    user.token = "t"
    assert user.relogin() is False
    assert results.problems == ["user 1 logged in but got no token"]


def test_a_failed_join_stays_on_the_form():
    user, client, _ = _user({"join_team": rush.Response(400, {}, None)})
    user.s.seats.put("CODE1234")
    user.join_team()
    assert client.calls == ["join_team"]


def test_a_team_without_a_join_code_is_a_problem_and_offers_no_seats():
    user, client, results = _user({"create_team": rush.Response(201, {"team": {}}, None)}, 0)
    user.create_team()
    assert client.calls == ["create_team"]
    assert results.problems == ["user 0 created a team but got no join code"]
    assert user.s.seats.empty()


@pytest.mark.parametrize(
    "bad",
    [
        ["--team-size=7"],
        ["--team-size=1"],
        ["--config-poll-seconds=0"],
        ["--relogin-share=1.5"],
        ["--seat-wait-seconds=0"],
        ["--max-start-lag=0"],
        ["--linger-seconds=-1"],
    ],
)
def test_bad_options_are_refused(bad):
    with pytest.raises(SystemExit) as exc:
        rush.parse_args(["--base-url=http://x", *bad])
    assert exc.value.code == 2


def test_a_base_url_that_is_not_http_is_refused():
    with pytest.raises(SystemExit):
        rush.parse_args(["--base-url=ingress:80"])
