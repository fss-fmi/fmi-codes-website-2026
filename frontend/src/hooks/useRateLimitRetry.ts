import { useCallback, useEffect, useRef, useState } from 'react';
import { retryOnRateLimit } from '@/lib/rateLimitRetry';

/** The submit button's name while retrying, so a screen reader isn't fed every tick. */
export const RETRYING_LABEL = 'Retrying automatically';

/** The submit button's text while retrying: the countdown, or no number while a retry is sent. */
export function retryingText(waitSeconds: number | null): string {
  return waitSeconds === null ? 'RETRYING…' : `RETRYING… ${waitSeconds}s`;
}

/**
 * `run` sends a request through retryOnRateLimit. `retrying` is true from the first 429
 * until the run settles, so the page's note and button state hold steady across the retry
 * requests; `waitSeconds` is the countdown while a retry waits, null otherwise. `cancel`
 * drops a waiting retry, so a form edited during the countdown never sends what it held
 * before; the run then rejects with an AbortError. A request already in flight is left
 * alone. Leaving the page cancels too.
 */
export function useRateLimitRetry() {
  const [waitSeconds, setWaitSeconds] = useState<number | null>(null);
  const [retrying, setRetrying] = useState(false);
  const pending = useRef<AbortController | null>(null);
  const waiting = useRef(false);

  useEffect(() => () => pending.current?.abort(), []);

  const run = useCallback(async <T>(attempt: () => Promise<T>): Promise<T> => {
    const controller = new AbortController();
    pending.current = controller;
    try {
      return await retryOnRateLimit(attempt, {
        onWait: (seconds) => {
          waiting.current = seconds !== null;
          setWaitSeconds(seconds);
          if (seconds !== null) setRetrying(true);
        },
        signal: controller.signal,
      });
    } finally {
      setRetrying(false);
    }
  }, []);

  const cancel = useCallback(() => {
    if (waiting.current) pending.current?.abort();
  }, []);

  return { run, cancel, retrying, waitSeconds };
}
