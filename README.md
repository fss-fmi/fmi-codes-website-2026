# FMI{Codes} 2026

The platform behind **FMI{Codes}**, a 48-hour student hackathon. It runs everything around the coding itself: participant registration, team formation, the 18 event slots and their waiting queue, mentor and team preferences, mentor matching and the published results. Code lives in public GitHub repos, team chat happens on Discord and judging is done by an in-person jury.

One web app serves three kinds of users:

- **Participants** register, create or join a team (by join code or by applying) and, as captain, rank mentors.
- **Mentors** publish a profile, rank teams and see the teams they are assigned.
- **The admin** runs Mission Control: registration slots, feature switches, mentor matching (Gale-Shapley plus a greedy fill, 2 or 3 mentors per team) and the final scores for the live leaderboard.

**Stack:** React 19 + TypeScript SPA (Vite, Tailwind) · Flask 3 API on Python 3.12 · PostgreSQL 16 · Redis (optional). Deployed to a self-hosted k3s cluster with a staging and prod split, Kustomize, SOPS and Flux GitOps.

## Repository

```
backend/     Flask API, schema, migrations and seed data
frontend/    React SPA and its Nginx image
tests/       Backend unit tests and API integration tests (tests/e2e/)
infra/k8s/   Cluster manifests and scripts (bootstrap.sh runs them)
docs/        All documentation, published to GitHub Pages
```

## Documentation

Everything else (local setup, architecture, API, data model, testing, deployment and the cluster runbook) is at **https://fss-fmi.github.io/fmi-codes-website-2026/**, built from the Markdown in [`docs/`](docs/). Start with [Getting Started](docs/onboarding.md) to run it locally.
