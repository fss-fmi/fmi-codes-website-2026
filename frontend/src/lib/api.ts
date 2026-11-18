// Minimal fetch wrapper used across the app as `api.get` / `api.post` / etc.
//
// Contract:
//   - Always sends cookies (`credentials: 'include'`) so the HttpOnly JWT cookie
//     set by the backend on login is attached to every subsequent request.
//   - Parses JSON responses and returns the parsed body (typed via the generic).
//   - On HTTP 401, dispatches a global `auth:unauthorized` event that
//     AuthContext listens for to clear its user/role state.
//   - On any non-2xx response, throws an ApiError whose message is the server's
//     `error` field, or a generic text when the answer has none. When no answer
//     comes back at all, throws a NetworkError. Callers show either one through
//     errorMessage() from lib/errors.ts.
//
// Requests hit relative paths (`/api/...`). In dev, Vite proxies `/api` to the
// backend (see vite.config.ts). In prod, Nginx does the same routing.

import { ApiError, GENERIC_ERROR, isAbortError, NetworkError } from './errors';

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

interface RequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

// Only the delta-seconds form: the backend never sends the HTTP-date one.
function retryAfterSeconds(res: Response): number | null {
  const value = res.headers.get('Retry-After')?.trim() ?? '';
  return /^\d+$/.test(value) ? Number(value) : null;
}

async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  url: string,
  body?: Json,
  opts: RequestOptions = {},
): Promise<T> {
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...(opts.headers ?? {}),
    },
    signal: opts.signal,
  };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch (err) {
    if (isAbortError(err)) throw err;
    throw new NetworkError();
  }

  if (res.status === 401) {
    // Let AuthContext know the session is gone so it can clear state and
    // route the user back to login. Non-authoritative: components can still
    // handle the thrown error however they want.
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  }

  // 204 No Content — no body to parse.
  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') ?? '';
  const isJson = contentType.includes('application/json');
  const payload: unknown = isJson ? await res.json().catch(() => null) : await res.text();

  if (!res.ok) {
    let message = GENERIC_ERROR;
    if (
      isJson &&
      payload &&
      typeof payload === 'object' &&
      'error' in payload &&
      typeof (payload as { error: unknown }).error === 'string'
    ) {
      message = (payload as { error: string }).error;
    }
    throw new ApiError(res.status, message, retryAfterSeconds(res));
  }

  return payload as T;
}

const api = {
  get: <T>(url: string, opts?: RequestOptions) => request<T>('GET', url, undefined, opts),
  post: <T>(url: string, body?: Json, opts?: RequestOptions) => request<T>('POST', url, body, opts),
  put: <T>(url: string, body?: Json, opts?: RequestOptions) => request<T>('PUT', url, body, opts),
  patch: <T>(url: string, body?: Json, opts?: RequestOptions) =>
    request<T>('PATCH', url, body, opts),
  delete: <T>(url: string, opts?: RequestOptions) => request<T>('DELETE', url, undefined, opts),
};

export default api;
