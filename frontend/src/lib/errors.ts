export const NETWORK_ERROR = 'Network error. Please try again.';
export const GENERIC_ERROR = 'Something went wrong. Please try again.';

/**
 * A non-2xx answer. The message is the server's `error` text, or GENERIC_ERROR
 * when the answer carried none (an HTML 502 from the ingress during a rollout).
 */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
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
