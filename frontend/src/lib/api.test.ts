import api from './api';
import { ApiError, GENERIC_ERROR, NetworkError } from './errors';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function answer(
  status: number,
  body: string,
  contentType: string,
  headers: Record<string, string> = {},
) {
  fetchMock.mockResolvedValue(
    new Response(body, { status, headers: { 'content-type': contentType, ...headers } }),
  );
}

const RATE_LIMITED = JSON.stringify({ success: false, error: 'Too many requests' });

async function rejection(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (err) {
    return err;
  }
  throw new Error('expected the request to throw');
}

test("a JSON error answer throws an ApiError with the server's text and status", async () => {
  answer(
    401,
    JSON.stringify({ success: false, error: 'Invalid email or password' }),
    'application/json',
  );
  const err = await rejection(api.post('/api/auth/login', {}));
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ status: 401, message: 'Invalid email or password' });
});

test('an HTML error page from the ingress throws the generic text, not "HTTP 502"', async () => {
  answer(502, '<html><body>Bad Gateway</body></html>', 'text/html');
  const err = await rejection(api.get('/api/teams'));
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ status: 502, message: GENERIC_ERROR });
});

test("a 429's Retry-After seconds travel on the ApiError", async () => {
  answer(429, RATE_LIMITED, 'application/json', { 'Retry-After': '42' });
  expect(await rejection(api.post('/api/auth/register', {}))).toMatchObject({
    status: 429,
    retryAfter: 42,
  });
});

test.each([
  ['no header', {}],
  ['an HTTP date', { 'Retry-After': 'Wed, 18 Nov 2026 12:00:00 GMT' }],
  ['a negative number', { 'Retry-After': '-5' }],
])('Retry-After with %s is null', async (_, headers) => {
  answer(429, RATE_LIMITED, 'application/json', headers);
  expect(await rejection(api.post('/api/auth/register', {}))).toMatchObject({ retryAfter: null });
});

test('no answer at all throws a NetworkError', async () => {
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
  expect(await rejection(api.get('/api/teams'))).toBeInstanceOf(NetworkError);
});

test('an aborted request rethrows the AbortError for the caller to ignore', async () => {
  const abort = new DOMException('The operation was aborted.', 'AbortError');
  fetchMock.mockRejectedValue(abort);
  expect(await rejection(api.get('/api/teams'))).toBe(abort);
});
