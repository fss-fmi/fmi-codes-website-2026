// api.ts throws an Error carrying the server's message for any non-2xx answer.
// fetch itself rejects with a TypeError when no answer came back at all, and its
// text ("Failed to fetch") means nothing to a user.
export function errorMessage(err: unknown): string {
  if (err instanceof Error && !(err instanceof TypeError) && err.message) return err.message;
  return 'Network error. Please try again.';
}
