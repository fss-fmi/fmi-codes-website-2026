import { useCallback, useEffect, useRef, useState } from 'react';
import { retryOnRateLimit } from '@/lib/rateLimitRetry';

/**
 * `run` sends a request through retryOnRateLimit; `waitSeconds` is the countdown while a
 * retry waits, null otherwise. Leaving the page cancels a pending retry.
 */
export function useRateLimitRetry() {
  const [waitSeconds, setWaitSeconds] = useState<number | null>(null);
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    return () => current.abort();
  }, []);

  const run = useCallback(
    <T>(attempt: () => Promise<T>) =>
      retryOnRateLimit(attempt, {
        onWait: setWaitSeconds,
        signal: controller.current?.signal ?? AbortSignal.abort(),
      }),
    [],
  );

  return { run, waitSeconds };
}
