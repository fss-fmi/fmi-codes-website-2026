# ADR-014: Rate limits key on the account and the user, not only the network

**Status**: accepted.

## Context

Every limit keyed on the client address (#207). That is wrong for this event in two ways. During the hackathon every participant sits on the university network behind one address, and registration is first come, first served, so the whole venue shared one bucket: the 11th registration in a minute (10/min) or the 16th login (15/min) from anyone there got 429, and every device shared the 200/min default. The same happens to students who register from a lab when registration opens. Raising the address limits alone would also raise how much an attacker gets from one address, because each login attempt costs a bcrypt hash.

A per-device key was considered: a device ID cookie or header, or a browser fingerprint. A session token was considered too, either the login JWT itself or an anonymous session stored in Redis for every visitor. The client decides whether to send any of these back, so an attacker drops it and gets a fresh bucket on every request, and limiting how many it can mint brings back the per-address bucket. Fingerprints also collide on identical university laptops. A per-JWT key is multiplied by logging in again, because successful logins don't count. Storing login sessions in Redis would reverse [ADR-002](002-jwt-httponly-cookie-layered-revocation.md) and make Redis mandatory ([ADR-003](003-redis-optional-fail-open.md)), a new single point of failure during the opening minute.

## Decision

Each limit keys on what it protects (`backend/app/utils/rate_limits.py`):

- **The account a request names**, for login (15 failed attempts per minute; successful logins don't count) and password reset requests (5 per hour). The key is an HMAC of role and email with `SECRET_KEY`, so Redis never holds an email and a list of known addresses can't be hashed to find one.
- **The signed-in user**, read from a token with a valid signature and expiry, for the 200/min default, change-password, resend-verification and bug reports. The blocklist and revocation epoch are not checked here: a revoked token still belongs to its owner, and minting one needs the secret.
- **The client address**, only as a ceiling sized for a whole venue behind one NAT address: register and login 300/min, the anonymous default 3000/min, reset requests and reset confirm 100/min, verify-email 300/min. The tokens behind reset confirm and verify-email are 256-bit, so guessing them is hopeless either way. These windows are a minute, not an hour, because on a shared address the risk is one person exhausting the bucket for everyone: a minute caps that outage at a minute, while the per-email limit already stops a flood of one inbox.
- `RATELIMIT_MULTIPLIER` still scales every limit, and `/api/config`, `/api/teams/rankings` and the health probes stay exempt.

## Consequences

- **Easier**: participants on one network no longer take each other's turns, and a full venue fits under every address ceiling. Guessing one account's password is limited however many addresses the attacker uses. The account limit is checked before bcrypt runs, so a blocked account costs no CPU.
- **Harder**: anyone can block an account's logins for the rest of a minute with 15 wrong passwords, from any address. Someone already signed in keeps their session; only a fresh login waits. Each limited request decodes the JWT once more, which is microseconds and no network call.
- **Limit**: one address can still force 300 bcrypt hashes a minute through login, about 2 cores at the cost measured on staging (about 0.42 CPU-seconds a hash). Capacity has to absorb that (#219).
