import { useCallback, useEffect, useRef, useState } from 'react';
import { retryOnRateLimit } from '@/lib/rateLimitRetry';

/**
 * `run` sends a request through retryOnRateLimit; `waitSeconds` is the countdown while a
 * retry waits, null otherwise. `cancel` drops a waiting retry, so a form edited during the
 * countdown never sends what it held before; the run then rejects with an AbortError. A
 * request already in flight is left alone. Leaving the page cancels too.
 */
export function useRateLimitRetry() {
  const [waitSeconds, setWaitSeconds] = useState<number | null>(null);
  const pending = useRef<AbortController | null>(null);
  const waiting = useRef(false);

  useEffect(() => () => pending.current?.abort(), []);

  const run = useCallback(<T>(attempt: () => Promise<T>) => {
    const controller = new AbortController();
    pending.current = controller;
    return retryOnRateLimit(attempt, {
      onWait: (seconds) => {
        waiting.current = seconds !== null;
        setWaitSeconds(seconds);
      },
      signal: controller.signal,
    });
  }, []);

  const cancel = useCallback(() => {
    if (waiting.current) pending.current?.abort();
  }, []);

  return { run, cancel, waitSeconds };
}
