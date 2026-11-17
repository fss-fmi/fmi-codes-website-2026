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
    def log_message(self, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        payload = json.dumps({"got": body, "cookie": self.headers.get("Cookie")}).encode()
        self.send_response(201)
        self.send_header("Set-Cookie", "token=new-token; HttpOnly; Path=/; Secure")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(503)
        self.send_header("Content-Length", "9")
        self.end_headers()
        self.wfile.write(b"<html/>\n\n")


@pytest.fixture()
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join()


def test_client_sends_the_token_by_hand_and_reads_the_new_one(server):
    results = rush.Results()
    reply = rush.Client(server, 5, results).call(
        "register", "POST", "/x", token="old", body={"a": 1}, expect=(201,)
    )
    assert reply.status == 201
    assert reply.body == {"got": {"a": 1}, "cookie": "token=old"}
    assert reply.token == "new-token"
    assert [(s.name, s.status, s.expected) for s in results.samples] == [("register", 201, True)]


def test_client_records_an_error_status_with_a_non_json_body(server):
    results = rush.Results()
    reply = rush.Client(server, 5, results).call("config", "GET", "/api/config")
    assert (reply.status, reply.body, reply.token) == (503, None, None)
    assert results.samples[0].expected is False


def test_client_records_no_answer_as_status_zero():
    results = rush.Results()
    reply = rush.Client("http://127.0.0.1:1", 2, results).call("me", "GET", "/api/auth/me")
    assert reply.status == 0
    assert results.samples[0].error
