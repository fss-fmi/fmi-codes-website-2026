# FMI{Codes} 2026 frontend

The React single-page app for the FMI{Codes} platform. React 19, TypeScript, Vite, Tailwind CSS v4, React Router 7 and TanStack Query.

Project-wide docs live in [`docs/`](../docs/) and at https://fss-fmi.github.io/fmi-codes-website-2026/: [Architecture](../docs/architecture.md), [Onboarding](../docs/onboarding.md), [API reference](../docs/api.md).

## Scripts

| Command           | What it does                                                                                                 |
| ----------------- | ------------------------------------------------------------------------------------------------------------ |
| `npm install`     | Install dependencies from the committed `package-lock.json`                                                  |
| `npm run dev`     | Vite dev server on http://localhost:5173, proxying `/api` to `BACKEND_URL` (default `http://localhost:5001`) |
| `npm run build`   | Type-check (`tsc -b`) and build to `dist/`                                                                   |
| `npm run preview` | Serve the production build locally                                                                           |
| `npm run lint`    | ESLint                                                                                                       |
| `npm test`        | Vitest (jsdom + Testing Library)                                                                             |

From the repo root, `python dev.py` starts this dev server together with the backend.

## Structure

```
src/
  App.tsx          flat route table + global providers
  pages/           one folder per area: auth, teams, mentors, admin, rankings, regulations
  components/      shared UI grouped by area (common, layout, teams, admin, home, mentors)
  context/         AuthContext (current user) and ConfigContext (feature flags)
  hooks/           useApplyToTeam, useConfirmAction, useIsMobile, useRateLimitRetry, useVisuals
  lib/api.ts       the only fetch wrapper
  lib/errors.ts    ApiError, NetworkError and errorMessage()
  lib/queryClient.ts  shared TanStack Query client
  lib/             also the ranking-window helpers, the rate-limit retry and form validation
  types/           hand-written API response types
```

## Conventions

- **API calls** go through `src/lib/api.ts` (`api.get/post/put/patch/delete`). It sends cookies, throws an `ApiError` (status, the server's `error` message and any `Retry-After`) on non-2xx and a `NetworkError` when no answer arrives, and fires a window `auth:unauthorized` event on 401 that logs the user out. Show a caught error with `errorMessage()` from `src/lib/errors.ts`.
- **Server state** lives in TanStack Query. Defaults: 30 s stale time, no retries, no refetch on window focus.
- **Auth** is an httpOnly cookie set by the backend; the SPA never touches the token. The signed-in user is one TanStack query, `['me']` (`useMe()` in `src/hooks/useMe.ts`), that `AuthContext` and the pages read; only a 401 or 404 there signs the user out. `RequireAuth` mounts it too, so opening a protected page refetches a stale user. After a change to the user's own team, await `refreshUser()` before navigating.
- **Role-gated pages** wrap themselves in `<RequireAuth roles={[...]}>`. The routes in `App.tsx` are not guarded, so a new protected page must add its own wrapper.
- **Feature flags** (`REGISTRATION_OPEN`, `PREFERENCES_OPEN`, `MENTORS_STAY_TUNED`, `RANKINGS_LIVE`, `MATCHING_CONFIRMED`, `REQUIRE_EMAIL_VERIFICATION`) come from `useConfig()`. `ConfigContext` refetches `/api/config` every 30 s and on window focus, because the admin switches the first four live from Mission Control's SITE tab and confirms matching from its MATCHING tab. `MATCHING_CONFIRMED` freezes teams: hide every team change and show `TeamsLockedNotice` while it is true, and call `refetchConfigIfLocked` (`src/lib/teamsLock.ts`) on a refused team change so the page locks at once.
- **Types** in `src/types/` are maintained by hand to match the backend. Update them with any API change.
- Import from `src` with the `@/` alias.

## Production build

`Dockerfile` builds the app with Node 22 and serves `dist/` from Nginx (`nginx.conf`) as a non-root user. Nginx falls back to `index.html` for client routes and proxies `/api/` to `http://backend:5001`. Under `/assets/` (Vite's hashed build files) a missing file is a 404 instead, the files are cached as immutable and any other answer there is `no-store`; `index.html` and `public/asset-guard.js` are revalidated on every load. The guard reloads the page when a build file fails to load, which happens mid-rollout when the page and the file come from different versions ([Rollouts](../docs/deployment.md#rollouts)).
