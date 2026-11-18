import { ApiError } from './errors';

export const MAX_RETRIES = 3;
export const MAX_WAIT_SECONDS = 60;
export const MAX_JITTER_SECONDS = 3;

interface RetryOptions {
  /** Whole seconds left while a retry waits, then null once it is sent. */
  onWait: (secondsLeft: number | null) => void;
  signal: AbortSignal;
  random?: () => number;
}

type RateLimited = ApiError & { retryAfter: number };

function isRetryable(err: unknown): err is RateLimited {
  return (
    err instanceof ApiError &&
    err.status === 429 &&
    err.retryAfter !== null &&
    err.retryAfter <= MAX_WAIT_SECONDS
  );
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException('Retry cancelled', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, ms);
    if (signal.aborted) abort();
    else signal.addEventListener('abort', abort, { once: true });
  });
}

// Sleeps to each whole-second mark so the countdown reads 3, 2, 1 on time.
async function countdown(ms: number, onWait: RetryOptions['onWait'], signal: AbortSignal) {
  const end = Date.now() + ms;
  for (let left = ms; left > 0; left = end - Date.now()) {
    onWait(Math.ceil(left / 1000));
    await sleep(((left - 1) % 1000) + 1, signal);
  }
}

/**
 * Sends `attempt` again after a 429. The limiter answers before the route runs, so the
 * request did nothing and is safe to repeat; a 5xx or a lost answer may have gone through
 * and is never retried. Each wait is Retry-After plus 0 to 3 s of jitter, so everyone limited
 * in one window doesn't come back at the same instant. The last 429, one without Retry-After
 * or one asking for more than a minute is thrown for the caller to show.
 */
export async function retryOnRateLimit<T>(
  attempt: () => Promise<T>,
  { onWait, signal, random = Math.random }: RetryOptions,
): Promise<T> {
  for (let retries = 0; ; retries++) {
    try {
      return await attempt();
    } catch (err) {
      if (!isRetryable(err) || retries === MAX_RETRIES) throw err;
      try {
        await countdown((err.retryAfter + random() * MAX_JITTER_SECONDS) * 1000, onWait, signal);
      } finally {
        onWait(null);
      }
    }
  }
}
