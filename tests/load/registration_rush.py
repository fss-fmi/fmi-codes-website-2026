"""Registration rush load test (#222): 500 people register and form teams in the first minute.

Users arrive on a fixed schedule however slow the backend gets (an open model), load the
registration page's API calls, register, then every third creates a team and the rest join
one by code. Some log out and back in. Everyone then stays on the team page the way the
SPA does: `/api/config` every 30 s (ConfigContext) and a few full reloads.

Standard library only, so it runs on a stock python image. How to run it on staging:
docs/testing.md, "Load test". Exit code 0 when every pass criterion holds, 1 when one
fails, 2 when the run could not start.
"""

import argparse
import http.client
import json
import queue
import random
import secrets
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from http.cookies import CookieError, SimpleCookie

EMAIL_DOMAIN = "loadtest.invalid"
CAPTAIN_EVERY = 3
# A thread that starts later than this after its scheduled arrival means the generator,
# not the backend, set the pace, and every latency it measured is understated.
MAX_START_LAG_SECONDS = 1.0


@dataclass(frozen=True)
class Sample:
    name: str
    status: int  # 0 when no HTTP answer came back (timeout, refused, reset)
    seconds: float
    expected: bool
    error: str = ""


@dataclass
class Limits:
    register_p95: float
    register_p99: float
    max_start_lag: float = MAX_START_LAG_SECONDS


@dataclass
class Results:
    samples: list[Sample] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    start_lags: list[float] = field(default_factory=list)
    registered_at: list[float] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def add(self, sample: Sample) -> None:
        with self.lock:
            self.samples.append(sample)

    def problem(self, text: str) -> None:
        with self.lock:
            self.problems.append(text)


@dataclass(frozen=True)
class Response:
    status: int
    body: dict | None
    token: str | None


def token_from(set_cookie_headers: list[str]) -> str | None:
    for header in set_cookie_headers:
        cookie = SimpleCookie()
        try:
            cookie.load(header)
        except CookieError:
            continue
        if "token" in cookie and cookie["token"].value:
            return cookie["token"].value
    return None


class Client:
    """One HTTP request per call, a new connection each time.

    The token cookie is `Secure` on staging (`FLASK_ENV=production`) and the Job talks plain
    HTTP, so a cookie jar would never send it back: it is read from `Set-Cookie` and sent by
    hand.
    """

    def __init__(self, base_url: str, timeout: float, results: Results | None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.results = results

    def call(
        self,
        name: str,
        method: str,
        path: str,
        *,
        token: str | None = None,
        body: dict | None = None,
        expect: tuple[int, ...] = (200,),
    ) -> Response:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(self.base_url + path, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if token:
            request.add_header("Cookie", f"token={token}")

        status, raw, cookies, error = 0, b"", [], ""
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as reply:
                status = reply.status
                cookies = reply.headers.get_all("Set-Cookie") or []
                raw = reply.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            try:
                raw = exc.read()
            except (OSError, http.client.HTTPException):
                raw = b""
        except (OSError, http.client.HTTPException) as exc:
            error = f"{type(exc).__name__}: {exc}"
        seconds = time.perf_counter() - started

        if self.results is not None:
            self.results.add(Sample(name, status, seconds, status in expect, error))
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        return Response(status, parsed if isinstance(parsed, dict) else None, token_from(cookies))


@dataclass
class Scenario:
    client: Client
    results: Results
    run_id: str
    password: str
    university_id: int
    specialty_id: int
    team_size: int
    relogin_share: float
    linger_seconds: float
    config_poll_seconds: float
    team_reloads: int
    seat_wait_seconds: float
    seed: int
    seats: queue.Queue = field(default_factory=queue.Queue)


class User:
    def __init__(self, scenario: Scenario, index: int):
        self.s = scenario
        self.c = scenario.client
        self.index = index
        self.rng = random.Random(f"{scenario.seed}-{index}")
        self.email = f"{scenario.run_id}-{index:04d}@{EMAIL_DOMAIN}"
        self.token: str | None = None
        self.user_id: int | None = None

    @property
    def is_captain(self) -> bool:
        return self.index % CAPTAIN_EVERY == 0

    def run(self, scheduled_at: float) -> None:
        with self.s.results.lock:
            self.s.results.start_lags.append(time.monotonic() - scheduled_at)
        try:
            self._run()
        except Exception as exc:  # a bug in the script must fail the run, not vanish
            self.s.results.problem(f"user {self.index} crashed: {type(exc).__name__}: {exc}")

    def _run(self) -> None:
        self.open_page()
        self.c.call("universities", "GET", "/api/universities")
        self.c.call("specialties", "GET", "/api/specialties")
        if not self.register():
            return
        self.team_page()

        if self.is_captain:
            self.create_team()
        else:
            self.join_team()

        if self.rng.random() < self.s.relogin_share and not self.relogin():
            return
        self.linger()

    def open_page(self) -> None:
        """What every full page load sends before the page's own queries."""
        if self.token:
            self.c.call("me", "GET", "/api/auth/me", token=self.token)
        else:
            self.c.call("me_anonymous", "GET", "/api/auth/me", expect=(401,))
        self.c.call("config", "GET", "/api/config", token=self.token)

    def register(self) -> bool:
        reply = self.c.call(
            "register",
            "POST",
            "/api/auth/register",
            body={
                "first_name": "Load",
                "last_name": "Tester",
                "email": self.email,
                "password": self.s.password,
                "phone_number": "0888000000",
                "faculty_number": f"LT{self.s.run_id}{self.index:04d}",
                "course": "Bachelor 1st Year",
                "university_id": self.s.university_id,
                "specialty_id": self.s.specialty_id,
            },
            expect=(201,),
        )
        if reply.status != 201 or not reply.token or not reply.body:
            return False
        self.token = reply.token
        self.user_id = reply.body.get("user_id")
        with self.s.results.lock:
            self.s.results.registered_at.append(time.monotonic())
        return True

    def team_page(self) -> None:
        """The /team route's queries (TeamPage.tsx), in the order the page sends them."""
        me = self.c.call("me", "GET", "/api/auth/me", token=self.token)
        team_id = ((me.body or {}).get("user") or {}).get("team_id")
        if not team_id:
            self.c.call("my_applications", "GET", "/api/teams/my-applications", token=self.token)
            return
        team = (
            self.c.call("team", "GET", f"/api/teams/{team_id}", token=self.token).body or {}
        ).get("team") or {}
        captain = team.get("captain_id") == self.user_id
        if captain:
            self.c.call("join_requests", "GET", f"/api/teams/{team_id}/requests", token=self.token)
        if team.get("status") == "active":
            # The page asks for every member, though only the captain may read them.
            self.c.call(
                "mentor_preferences",
                "GET",
                f"/api/teams/{team_id}/mentor-preferences",
                token=self.token,
                expect=(200,) if captain else (403,),
            )
            self.c.call("matching_status", "GET", "/api/matching-status", token=self.token)

    def create_team(self) -> None:
        reply = self.c.call(
            "create_team",
            "POST",
            "/api/teams",
            token=self.token,
            body={"team_name": f"Load {self.s.run_id} {self.index:04d}"},
            expect=(201,),
        )
        code = ((reply.body or {}).get("team") or {}).get("join_code")
        if reply.status == 201 and code:
            for _ in range(self.s.team_size - 1):
                self.s.seats.put(code)
        self.after_team_change()

    def join_team(self) -> None:
        try:
            code = self.s.seats.get(timeout=self.s.seat_wait_seconds)
        except queue.Empty:
            self.s.results.problem(
                f"user {self.index} found no open seat in {self.s.seat_wait_seconds:.0f} s"
            )
            return
        self.c.call(
            "join_team", "POST", "/api/teams/join", token=self.token, body={"join_code": code}
        )
        self.after_team_change()

    def after_team_change(self) -> None:
        # CreateTeamPage and JoinTeamPage refresh the user, then navigate to /team.
        self.c.call("me", "GET", "/api/auth/me", token=self.token)
        self.team_page()

    def relogin(self) -> bool:
        self.c.call("logout", "POST", "/api/auth/logout", token=self.token)
        self.token = None
        reply = self.c.call(
            "login",
            "POST",
            "/api/auth/login",
            body={"email": self.email, "password": self.s.password, "role": "participant"},
        )
        if reply.status != 200 or not reply.token:
            return False
        self.token = reply.token
        self.team_page()
        return True

    def linger(self) -> None:
        now = time.monotonic()
        end = now + self.s.linger_seconds
        reloads = sorted(
            now + self.rng.uniform(0, self.s.linger_seconds) for _ in range(self.s.team_reloads)
        )
        next_poll = now + self.s.config_poll_seconds
        while True:
            next_reload = reloads[0] if reloads else float("inf")
            at = min(next_poll, next_reload)
            if at >= end:
                return
            time.sleep(max(0.0, at - time.monotonic()))
            if at == next_reload:
                reloads.pop(0)
                self.open_page()
                self.team_page()
                next_poll = time.monotonic() + self.s.config_poll_seconds
            else:
                self.c.call("config", "GET", "/api/config", token=self.token)
                next_poll += self.s.config_poll_seconds


def percentile(values: list[float], pct: int) -> float:
    """Exact percentile over every sample, interpolated between neighbours."""
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[pct - 1]


def verdict(results: Results, limits: Limits) -> list[str]:
    """Every failed pass criterion as one line; empty means the run passed."""
    failures = []
    samples = results.samples
    server_errors = [s for s in samples if s.status >= 500]
    throttled = [s for s in samples if s.status == 429]
    no_answer = [s for s in samples if s.status == 0]
    unexpected = [s for s in samples if not s.expected and 0 < s.status < 500 and s.status != 429]
    for label, bad in (
        ("5xx responses", server_errors),
        ("429 responses", throttled),
        ("requests with no answer", no_answer),
        ("unexpected 4xx/2xx statuses", unexpected),
    ):
        if bad:
            where = Counter(f"{s.name} {s.status or s.error}" for s in bad).most_common(5)
            failures.append(f"{len(bad)} {label}: " + ", ".join(f"{k} x{n}" for k, n in where))

    register = [s.seconds for s in samples if s.name == "register"]
    if not register:
        failures.append("no registration was sent")
    else:
        p95, p99 = percentile(register, 95), percentile(register, 99)
        if p95 >= limits.register_p95:
            failures.append(f"register p95 {p95:.2f} s, limit {limits.register_p95:.2f} s")
        if p99 >= limits.register_p99:
            failures.append(f"register p99 {p99:.2f} s, limit {limits.register_p99:.2f} s")

    if results.start_lags and max(results.start_lags) > limits.max_start_lag:
        failures.append(
            f"the load generator started a user {max(results.start_lags):.2f} s late "
            f"(limit {limits.max_start_lag:.2f} s): it fell behind, so latencies are understated"
        )
    failures.extend(results.problems[:20])
    if len(results.problems) > 20:
        failures.append(f"... and {len(results.problems) - 20} more problems")
    return failures


def report(results: Results, started: float, arrival_seconds: float) -> None:
    by_name: dict[str, list[Sample]] = {}
    for sample in results.samples:
        by_name.setdefault(sample.name, []).append(sample)

    print(f"{'endpoint':<20}{'count':>7}{'p50':>9}{'p95':>9}{'p99':>9}{'max':>9}  statuses")
    for name in sorted(by_name):
        group = by_name[name]
        times = [s.seconds for s in group]
        statuses = Counter(s.status for s in group)
        print(
            f"{name:<20}{len(group):>7}"
            f"{percentile(times, 50):>9.3f}{percentile(times, 95):>9.3f}"
            f"{percentile(times, 99):>9.3f}{max(times):>9.3f}  "
            + " ".join(f"{code}x{n}" for code, n in sorted(statuses.items()))
        )
    print(f"requests: {len(results.samples)}")
    if results.start_lags:
        print(f"max start lag: {max(results.start_lags):.3f} s")
    if results.registered_at:
        drained = max(results.registered_at) - started
        print(
            f"registrations: {len(results.registered_at)}, the last one done "
            f"{drained:.1f} s after arrivals began (they took {arrival_seconds:.0f} s)"
        )


class PreflightError(Exception):
    pass


def preflight(client: Client) -> tuple[int, int]:
    """Refuse to start on a staging the run would not measure or would leave dirty."""
    config = client.call("preflight", "GET", "/api/config")
    if config.status != 200 or config.body is None:
        raise PreflightError(f"/api/config answered {config.status}")
    if not config.body.get("REGISTRATION_OPEN"):
        raise PreflightError("registration_open is off; switch it on in Mission Control")
    if config.body.get("REQUIRE_EMAIL_VERIFICATION"):
        raise PreflightError("REQUIRE_EMAIL_VERIFICATION is on, so captains can't create teams")

    registered = client.call("preflight", "GET", "/api/teams/registered")
    if registered.status != 200 or registered.body is None:
        raise PreflightError(f"/api/teams/registered answered {registered.status}")
    if registered.body.get("teams"):
        raise PreflightError(
            "teams are already registered; run cleanup.sql (the list is cached for ~30 s)"
        )

    ids = []
    for path, key in (("/api/universities", "universities"), ("/api/specialties", "specialties")):
        rows = (client.call("preflight", "GET", path).body or {}).get(key) or []
        if not rows:
            raise PreflightError(f"{path} returned no seed {key}")
        ids.append(rows[0]["id"])
    return ids[0], ids[1]


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--base-url",
        required=True,
        help="e.g. http://ingress-nginx-staging-controller.ingress-nginx-staging.svc.cluster.local",
    )
    p.add_argument("--users", type=int, default=500)
    p.add_argument(
        "--arrival-seconds", type=float, default=60.0, help="arrivals spread over this window"
    )
    p.add_argument(
        "--team-size", type=int, default=6, help="seats a captain hands out, captain included"
    )
    p.add_argument(
        "--relogin-share", type=float, default=0.1, help="share of users who log out and back in"
    )
    p.add_argument(
        "--linger-seconds", type=float, default=120.0, help="time on the team page afterwards"
    )
    p.add_argument(
        "--config-poll-seconds", type=float, default=30.0, help="ConfigContext refetchInterval"
    )
    p.add_argument(
        "--team-reloads", type=int, default=2, help="full reloads of the team page while lingering"
    )
    p.add_argument(
        "--seat-wait-seconds", type=float, default=120.0, help="how long a joiner waits for a code"
    )
    p.add_argument(
        "--timeout", type=float, default=75.0, help="per request; above the ingress's 60 s"
    )
    p.add_argument("--register-p95", type=float, default=3.0)
    p.add_argument("--register-p99", type=float, default=10.0)
    p.add_argument("--seed", type=int, default=None, help="repeat a run's arrival schedule")
    args = p.parse_args(argv)
    if args.users < 1 or args.team_size < 2 or args.arrival_seconds < 0:
        p.error(
            "--users must be at least 1, --team-size at least 2, --arrival-seconds not negative"
        )
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seed = args.seed if args.seed is not None else secrets.randbits(32)
    run_id = secrets.token_hex(3)
    try:
        university_id, specialty_id = preflight(Client(args.base_url, args.timeout, None))
    except PreflightError as exc:
        print(f"preflight: {exc}", file=sys.stderr)
        return 2

    results = Results()
    scenario = Scenario(
        client=Client(args.base_url, args.timeout, results),
        results=results,
        run_id=run_id,
        password=secrets.token_urlsafe(18),
        university_id=university_id,
        specialty_id=specialty_id,
        team_size=args.team_size,
        relogin_share=args.relogin_share,
        linger_seconds=args.linger_seconds,
        config_poll_seconds=args.config_poll_seconds,
        team_reloads=args.team_reloads,
        seat_wait_seconds=args.seat_wait_seconds,
        seed=seed,
    )
    print(
        f"run {run_id}, seed {seed}: {args.users} users over {args.arrival_seconds:.0f} s",
        flush=True,
    )

    rng = random.Random(seed)
    offsets = sorted(rng.uniform(0, args.arrival_seconds) for _ in range(args.users))
    threading.stack_size(512 * 1024)
    started = time.monotonic() + 1.0
    threads = []
    for index, offset in enumerate(offsets):
        at = started + offset
        time.sleep(max(0.0, at - time.monotonic()))
        thread = threading.Thread(target=User(scenario, index).run, args=(at,), daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()

    report(results, started, args.arrival_seconds)
    failures = verdict(results, Limits(args.register_p95, args.register_p99))
    for line in failures:
        print(f"FAIL: {line}")
    print("RESULT: " + ("FAIL" if failures else "PASS"), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
