# ADR-014: Rate limits key on the account and the user, not only the network

**Status**: accepted.

## Context

Every limit keyed on the client address (#207). That is wrong for this event in two ways. During the hackathon every participant sits on the university network behind one address, and registration is first come, first served, so the whole venue shared one bucket: the 11th registration in a minute (10/min) or the 16th login (15/min) from anyone there got 429, and every device shared the 200/min default. The same happens to students who register from a lab when registration opens. Raising the address limits alone would also raise how much an attacker gets from one address, because each login attempt costs a bcrypt hash.

A per-device key was considered: a device ID cookie or header, or a browser fingerprint. A session token was considered too, either the login JWT itself or an anonymous session stored in Redis for every visitor. The client decides whether to send any of these back, so an attacker drops it and gets a fresh bucket on every request, and limiting how many it can mint brings back the per-address bucket. Fingerprints also collide on identical university laptops. A per-JWT key is multiplied by logging in again. Storing login sessions in Redis would reverse [ADR-002](002-jwt-httponly-cookie-layered-revocation.md) and make Redis mandatory ([ADR-003](003-redis-optional-fail-open.md)), a new single point of failure during the opening minute.

## Decision

Each limit keys on what it protects (`backend/app/utils/rate_limits.py`):

- **The account a request names**, for login (15 attempts per minute) and password reset requests (5 per hour). The key is an HMAC of role and email with `SECRET_KEY`, so Redis never holds an email and a list of known addresses can't be hashed to find one. A reset without a valid role (which the route rejects with a 400 and sends nothing) counts against the address, never against someone's account.
- **Login attempts count when they arrive, and a successful login clears them.** Counting after the response (`deduct_when`) only tests the limit before the view, so parallel wrong passwords would all pass before any was counted. Clearing on success means the owner is never blocked by their own earlier typos.
- **The admin is limited like any account.** Its login names `ADMIN_EMAIL` with role admin, so it gets its own account bucket and the same clearing on success.
- **The signed-in user**, read from a token with a valid signature and expiry, for the 200/min default, change-password, resend-verification (3/h) and bug reports (10/min). The blocklist and revocation epoch are not checked here: a revoked token still belongs to its owner, and minting one needs the secret.
- **The client address**, only as a ceiling sized for a whole venue behind one NAT address: register and login 300/min, reset requests and reset confirm 100/min, verify-email 300/min, resend-verification and bug reports 30/min (accounts are cheap, so a per-user limit alone would let one address multiply it), the anonymous default 3000/min per route and 6000/min across all routes together. The windows are a minute, not an hour, because on a shared address the risk is one person exhausting the bucket for everyone: a minute caps that outage at a minute.
- A 429 carries an `error` message, so the SPA shows why instead of "HTTP 429".
- `RATELIMIT_MULTIPLIER` still scales every limit, and `/api/config`, `/api/teams/rankings` and the health probes stay exempt.

## Consequences

- **Easier**: participants on one network no longer take each other's turns, and a full venue fits under every address ceiling. Guessing one account's password is capped at 15 a minute however many addresses or parallel requests the attacker uses. A blocked account gets 429 before bcrypt runs, so it costs no CPU.
- **Harder**: anyone can keep an account's login blocked for as long as they keep sending 15 wrong passwords a minute, from any address. That includes the admin, for anyone who knows `ADMIN_EMAIL`: the organiser should log in before registration opens and the event starts, since a session lasts 3 days and a blocked login doesn't end it. Someone already signed in keeps their session (3 days); only a fresh login waits, and the 429 says so. A third party can also use up a victim's 5 reset requests an hour, but each of those requests emails the victim a working link, the latest one valid.
- **Harder**: at 300 registrations a minute per address, one person can create accounts fast enough to fill teams and take slots in a first come, first served race. `REQUIRE_EMAIL_VERIFICATION` is the guard against throwaway emails. Every registration also sends a verification email (through a bounded pool of 4 senders), and the Gmail account's daily send limit is a ceiling for the whole rush (#219).
- **Limit**: one address can still force about 600 bcrypt hashes a minute, 300 through login and 300 through register (which hashes before its uniqueness check), about 4 cores at the cost measured on staging (about 0.42 CPU-seconds a hash). Capacity has to absorb that (#219). Each limited request decodes the JWT once more, which is microseconds and no network call.
