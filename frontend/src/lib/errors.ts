export const NETWORK_ERROR = 'Network error. Please try again.';
export const GENERIC_ERROR = 'Something went wrong. Please try again.';

/**
 * A non-2xx answer. The message is the server's `error` text, or GENERIC_ERROR
 * when the answer carried none (an HTML 502 from the ingress during a rollout).
 * `retryAfter` is the answer's Retry-After in seconds, which the backend sends on 429s.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly retryAfter: number | null;

  constructor(status: number, message: string, retryAfter: number | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

/** The caller cancelled: a fetch with an aborted signal, or a cancelled retry. */
export function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

/** fetch got no answer at all. */
export class NetworkError extends Error {
  constructor() {
    super(NETWORK_ERROR);
    this.name = 'NetworkError';
  }
}

// Anything else is a bug in our own code: its text means nothing to a user, and
// calling it a network error would invite a retry of something that may have worked.
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError || err instanceof NetworkError) return err.message;
  return GENERIC_ERROR;
}
