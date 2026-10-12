# FMI{Codes} 2026 frontend

The React single-page app for the FMI{Codes} platform. React 19, TypeScript, Vite, Tailwind CSS v4, React Router 7 and TanStack Query.

Project-wide docs live at the repo root: [README](../README.md), [ARCHITECTURE](../ARCHITECTURE.md), [ONBOARDING](../ONBOARDING.md), [API reference](../docs/api.md).

## Scripts

| Command           | What it does                                                                                                               |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `npm install`     | Install dependencies from the committed `package-lock.json` (see ONBOARDING for why not to regenerate it from scratch)     |
| `npm run dev`     | Vite dev server on http://localhost:5173, proxying `/api` and `/static` to `BACKEND_URL` (default `http://localhost:5001`) |
| `npm run build`   | Type-check (`tsc -b`) and build to `dist/`                                                                                 |
| `npm run preview` | Serve the production build locally                                                                                         |
| `npm run lint`    | ESLint                                                                                                                     |
| `npm test`        | Vitest (jsdom + Testing Library)                                                                                           |

From the repo root, `python dev.py` starts this dev server together with the backend.

## Structure

```
src/
  App.tsx          flat route table + global providers
  pages/           one folder per area: auth, teams, mentors, admin, rankings, regulations
  components/      shared UI grouped by area (common, layout, teams, admin, home, mentors)
  context/         AuthContext (current user) and ConfigContext (feature flags)
  hooks/           useApplyToTeam, useConfirmAction, useIsMobile, useVisuals
  lib/api.ts       the only fetch wrapper
  lib/queryClient.ts  shared TanStack Query client
  types/           hand-written API response types
```

## Conventions

- **API calls** go through `src/lib/api.ts` (`api.get/post/put/patch/delete`). It sends cookies, throws an `Error` with the server's `error` message on non-2xx, and fires a window `auth:unauthorized` event on 401 that logs the user out.
- **Server state** lives in TanStack Query. Defaults: 30 s stale time, no retries, no refetch on window focus.
- **Auth** is an httpOnly cookie set by the backend; the SPA never touches the token. `AuthContext` hydrates the user from `GET /api/auth/me` on load.
- **Role-gated pages** wrap themselves in `<RequireAuth roles={[...]}>`. The routes in `App.tsx` are not guarded, so a new protected page must add its own wrapper.
- **Feature flags** (`REGISTRATION_OPEN`, `MENTORS_STAY_TUNED`, `RANKINGS_LIVE`) come from `useConfig()`.
- **Types** in `src/types/` are maintained by hand to match the backend. Update them with any API change.
- Import from `src` with the `@/` alias.

## Production build

`Dockerfile` builds the app with Node 22 and serves `dist/` from Nginx (`nginx.conf`) as a non-root user. Nginx falls back to `index.html` for client routes and proxies `/api/` and `/static/` to `http://backend:5001`.
