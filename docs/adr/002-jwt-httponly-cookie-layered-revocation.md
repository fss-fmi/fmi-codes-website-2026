# ADR-002: JWT in an httpOnly cookie with layered revocation

**Status**: accepted

## Context

The SPA and API are served from the same origin. The platform has three flat roles (participant, mentor, admin) and no need for third-party login. Stateless JWTs avoid a session table, but they cannot be withdrawn once issued, and storing them where JavaScript can read them exposes them to XSS.

## Decision

The API issues an HS256 JWT (3-day expiry) carrying `user_id`, `role` and a unique `jti`, and sets it as an httpOnly `token` cookie with `SameSite=Lax` (`Secure` in production). `Authorization: Bearer` is accepted as a fallback for tooling and tests. Role checks are decorators on every protected route.

Revocation has two layers:

1. **Per token**: logout and password change store the `jti` in Redis with a TTL equal to the token's remaining life.
2. **Per user**: password change and reset set `tokens_valid_from`; any token with an earlier `iat` is rejected. The value is cached in Redis for about 45 seconds.

Both checks fail open when Redis is unavailable.

## Consequences

- **Easier**: no session storage; tokens are unreadable from JavaScript; a password reset evicts an attacker's existing sessions.
- **Harder**: revocation depends on Redis; without it, logout only clears the cookie and a stolen token stays valid until expiry. Every protected request makes up to two Redis calls and, on a cache miss, one DB read.
- **Technical debt**: the role is taken on trust from the token payload, so `JWT_SECRET_KEY` must stay secret and strong (production refuses to boot with known weak values). Optional-auth endpoints must use `extract_token()`; `/api/bug-report` does not, which is why SPA bug reports arrive anonymous.
