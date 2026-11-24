# ADR-018: The mentor seed lives only in a SOPS-encrypted Secret per environment

**Status**: accepted.

## Context

The backend seeds mentors from a JSON file on every start. That file is the real roster, names, emails and phone numbers, which is personal data: it can't be a plain file shipped with the code the way the curated universities and specialties are. `GET /api/mentors` is public and returned every mentor's email and phone number, and every seeded mentor got the same default password, `mentor123`, when their entry had none.

The cluster already keeps its secrets as SOPS-encrypted manifests in git, one age key per environment, applied by the deploy scripts ([ADR-006](006-self-hosted-k3s-pull-based-gitops.md), [ADR-011](011-one-tailscale-client-staging.md)).

## Decision

- **The real seed is a SOPS-encrypted Secret per environment**, `fmi-codes-mentors-seed` with one key `mentors.json`, the whole JSON encrypted: `infra/k8s/overlays/staging/secrets/mentors-seed.enc.yaml` under the staging key and `infra/k8s/secrets/mentors-seed.enc.yaml` under prod's. Staging holds the 20 current mentors; prod holds `[]` until the official 2027 roster.
- **`deploy-app.sh` applies it**, like the app secret and before handing over to Flux, so Flux never needs a decryption key. The backend mounts it read-only from an **optional** Secret and `MENTORS_SEED_FILE` points at it: a cluster without it still rolls out and seeds nobody.
- **Production config has no default seed.** Development and testing default to `backend/database/seeds/mentors.dev.json`, three fake `@mentor.test` mentors. Any local `mentors*.json` but the dev file is gitignored and excluded from the image by `backend/.dockerignore`. A seed that is missing or can't be read is logged and loads nothing, so a typo in an edited Secret can't stop every worker from booting.
- **No default password.** An entry without a `password` stores a NULL hash, which login always rejects. From the 2027 roster on, mentors are seeded without passwords and set their own through forgot password.
- **`GET /api/mentors` returns only public fields** (a fixed list in `mentor_service`), never email, phone or account state, under a new cache key so a copy cached with contacts is never served again.

## Consequences

- **Easier**: the roster is kept out of the tree and the image build, and each environment's roster is readable only by its own key holders. Editing the roster is a `sops <file>` edit plus a deploy, with no image build.
- **Harder**: seeding only inserts, so an edit never changes or removes a mentor already in the database; those changes are made in the database. The seed is invisible to code review and to tests that read files (the mentor photos are exempt from the "every image is used" check). Mentors without a password can't log in until `MAIL_PASSWORD` is set in that environment.
