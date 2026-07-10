// Shared TanStack Query client. One instance for the whole app so cache lives
// across route changes.
//
// Defaults chosen for this app:
//   - staleTime 30s so tab focus / component remounts don't spam the backend
//   - retry: false — the api.ts wrapper already surfaces useful errors, and
//     auto-retrying 4xx responses (e.g. 401, 403) is worse than useless.
//   - refetchOnWindowFocus off — most of this UI is admin dashboards where
//     silent refetches on focus are noisy, not helpful.

import { QueryClient } from '@tanstack/react-query';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: false,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: false,
    },
  },
});

export default queryClient;
