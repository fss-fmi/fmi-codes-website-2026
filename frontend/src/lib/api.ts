// Minimal fetch wrapper used across the app as `api.get` / `api.post` / etc.
//
// Contract:
//   - Always sends cookies (`credentials: 'include'`) so the HttpOnly JWT cookie
//     set by the backend on login is attached to every subsequent request.
//   - Parses JSON responses and returns the parsed body (typed via the generic).
//   - On HTTP 401, dispatches a global `auth:unauthorized` event that
//     AuthContext listens for to clear its user/role state.
//   - On any non-2xx response, throws an Error whose message is the server's
//     `error` field (if present) or a generic "HTTP <status>" fallback so
//     callers can `catch` and surface the message to the user.
//
// Requests hit relative paths (`/api/...`). In dev, Vite proxies `/api` to the
// backend (see vite.config.ts). In prod, Nginx does the same routing.

type Json = Record<string, unknown> | unknown[] | string | number | boolean | null;

interface RequestOptions {
  headers?: Record<string, string>;
  signal?: AbortSignal;
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

  const res = await fetch(url, init);

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
    let message = `HTTP ${res.status}`;
    if (
      isJson &&
      payload &&
      typeof payload === 'object' &&
      'error' in payload &&
      typeof (payload as { error: unknown }).error === 'string'
    ) {
      message = (payload as { error: string }).error;
    }
    throw new Error(message);
  }

  return payload as T;
}

const api = {
  get: <T>(url: string, opts?: RequestOptions) => request<T>('GET', url, undefined, opts),
  post: <T>(url: string, body?: Json, opts?: RequestOptions) => request<T>('POST', url, body, opts),
  put: <T>(url: string, body?: Json, opts?: RequestOptions) => request<T>('PUT', url, body, opts),
  patch: <T>(url: string, body?: Json, opts?: RequestOptions) => request<T>('PATCH', url, body, opts),
  delete: <T>(url: string, opts?: RequestOptions) => request<T>('DELETE', url, undefined, opts),
};

export default api;
