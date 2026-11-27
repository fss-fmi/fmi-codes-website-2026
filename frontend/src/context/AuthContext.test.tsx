import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './AuthContext';

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const ANA = { success: true, user: { id: 1, role: 'participant', email: 'ana@example.test' } };

function answer(status: number, body: object = {}) {
  fetchMock.mockResolvedValueOnce(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  );
}

function Probe() {
  const { user, isLoading, login, refreshUser } = useAuth();
  return (
    <>
      <span data-testid="user">{isLoading ? 'loading' : (user?.email ?? 'nobody')}</span>
      <button
        type="button"
        onClick={() => void refreshUser()}
      >
        refresh
      </button>
      <button
        type="button"
        onClick={() => login('participant', { role: 'participant', email: 'new@example.test' })}
      >
        login
      </button>
    </>
  );
}

function renderAuth() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  return client;
}

const shown = () => screen.getByTestId('user').textContent;

test('a 401 from /api/auth/me means nobody is signed in', async () => {
  answer(401, { success: false });
  renderAuth();
  await waitFor(() => expect(shown()).toBe('nobody'));
});

test('a 503 on a refresh keeps the signed-in user', async () => {
  answer(200, ANA);
  renderAuth();
  await waitFor(() => expect(shown()).toBe('ana@example.test'));

  answer(503, { success: false, error: 'Service unavailable' });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'refresh' }));
  });
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(shown()).toBe('ana@example.test');
});

test('a refresh shows a change someone else made to the user', async () => {
  answer(200, ANA);
  const client = renderAuth();
  await waitFor(() => expect(shown()).toBe('ana@example.test'));

  answer(200, { success: true, user: { ...ANA.user, email: 'ana.new@example.test' } });
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'refresh' }));
  });
  await waitFor(() => expect(shown()).toBe('ana.new@example.test'));
  // One source: the page queries read the same entry AuthContext does.
  expect(client.getQueryData(['me'])).toEqual({
    success: true,
    user: { ...ANA.user, email: 'ana.new@example.test' },
  });
});

test('a /me answer requested before a login does not undo it', async () => {
  let answerLate: (res: Response) => void = () => {};
  fetchMock.mockReturnValueOnce(new Promise<Response>((resolve) => (answerLate = resolve)));
  renderAuth();
  fireEvent.click(screen.getByRole('button', { name: 'login' }));
  await waitFor(() => expect(shown()).toBe('new@example.test'));

  answerLate(new Response('{}', { status: 401, headers: { 'content-type': 'application/json' } }));
  // Give the late answer time to land and its observers time to be told.
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
  expect(shown()).toBe('new@example.test');
});

test('a 401 anywhere else signs the user out', async () => {
  answer(200, ANA);
  const client = renderAuth();
  await waitFor(() => expect(shown()).toBe('ana@example.test'));
  act(() => {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'));
  });
  expect(client.getQueryData(['me'])).toBeNull();
  // The query cache tells its observers on the next tick.
  await waitFor(() => expect(shown()).toBe('nobody'));
});
