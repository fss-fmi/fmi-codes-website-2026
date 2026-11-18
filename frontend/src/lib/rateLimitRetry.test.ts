import { ApiError, NetworkError } from './errors';
import { MAX_RETRIES, retryOnRateLimit } from './rateLimitRetry';

const limited = (retryAfter: number | null = 2) =>
  new ApiError(429, 'Too many requests', retryAfter);

let waits: (number | null)[];
let controller: AbortController;

beforeEach(() => {
  vi.useFakeTimers();
  waits = [];
  controller = new AbortController();
});

afterEach(() => {
  vi.useRealTimers();
});

function retry<T>(attempt: () => Promise<T>, random = () => 0.5) {
  const result = retryOnRateLimit(attempt, {
    onWait: (s) => waits.push(s),
    signal: controller.signal,
    random,
  });
  // Rejections are asserted later; without this they surface as unhandled first.
  result.catch(() => {});
  return result;
}

test('a 429 is sent again after Retry-After plus jitter, counting down each second', async () => {
  const attempt = vi.fn().mockRejectedValueOnce(limited(2)).mockResolvedValueOnce('ok');
  const result = retry(attempt);

  await vi.advanceTimersByTimeAsync(3499);
  expect(attempt).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect(attempt).toHaveBeenCalledTimes(2);
  await expect(result).resolves.toBe('ok');
  expect(waits).toEqual([4, 3, 2, 1, null]);
});

test('the jitter adds nothing at its low end and under 3 s at its high end', async () => {
  const low = vi.fn().mockRejectedValueOnce(limited(2)).mockResolvedValueOnce('ok');
  const lowResult = retry(low, () => 0);
  await vi.advanceTimersByTimeAsync(1999);
  expect(low).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  await expect(lowResult).resolves.toBe('ok');

  const high = vi.fn().mockRejectedValueOnce(limited(2)).mockResolvedValueOnce('ok');
  const highResult = retry(high, () => 0.9999);
  await vi.advanceTimersByTimeAsync(4000);
  expect(high).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1000);
  await expect(highResult).resolves.toBe('ok');
});

test(`it gives up after ${MAX_RETRIES} retries and throws the last 429`, async () => {
  const last = limited(1);
  const attempt = vi
    .fn()
    .mockRejectedValueOnce(limited(1))
    .mockRejectedValueOnce(limited(1))
    .mockRejectedValueOnce(limited(1))
    .mockRejectedValueOnce(last);
  const result = retry(attempt, () => 0);

  await vi.advanceTimersByTimeAsync(10_000);
  await expect(result).rejects.toBe(last);
  expect(attempt).toHaveBeenCalledTimes(MAX_RETRIES + 1);
  expect(waits.at(-1)).toBeNull();
});

test('a wait of exactly 60 s is still retried', async () => {
  const attempt = vi.fn().mockRejectedValueOnce(limited(60)).mockResolvedValueOnce('ok');
  const result = retry(attempt, () => 0);

  await vi.advanceTimersByTimeAsync(60_000);
  await expect(result).resolves.toBe('ok');
});

test.each([
  ['a 429 asking for more than 60 s', limited(61)],
  ['a 429 without Retry-After', limited(null)],
  ['a wrong password', new ApiError(401, 'Invalid email or password')],
  ['a server error, which may have gone through', new ApiError(502, 'Bad gateway')],
  ['a lost answer, which may have gone through', new NetworkError()],
])('%s is thrown without a retry', async (_, err) => {
  const attempt = vi.fn().mockRejectedValue(err);
  const result = retry(attempt);

  await vi.advanceTimersByTimeAsync(120_000);
  await expect(result).rejects.toBe(err);
  expect(attempt).toHaveBeenCalledTimes(1);
  expect(waits).toEqual([]);
});

test('cancelling during a wait stops the retry', async () => {
  const attempt = vi.fn().mockRejectedValueOnce(limited(5)).mockResolvedValueOnce('ok');
  const result = retry(attempt);

  await vi.advanceTimersByTimeAsync(1000);
  controller.abort();
  await expect(result).rejects.toMatchObject({ name: 'AbortError' });
  await vi.advanceTimersByTimeAsync(10_000);
  expect(attempt).toHaveBeenCalledTimes(1);
  expect(waits.at(-1)).toBeNull();
});
