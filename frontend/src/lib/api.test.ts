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

function answer(status: number, body: string, contentType: string) {
  fetchMock.mockResolvedValue(
    new Response(body, { status, headers: { 'content-type': contentType } }),
  );
}

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

test('no answer at all throws a NetworkError', async () => {
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
  expect(await rejection(api.get('/api/teams'))).toBeInstanceOf(NetworkError);
});

test('an aborted request rethrows the AbortError for the caller to ignore', async () => {
  const abort = new DOMException('The operation was aborted.', 'AbortError');
  fetchMock.mockRejectedValue(abort);
  expect(await rejection(api.get('/api/teams'))).toBe(abort);
});
