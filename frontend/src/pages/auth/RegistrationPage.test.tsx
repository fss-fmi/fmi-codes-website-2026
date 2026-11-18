import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ApiError } from '@/lib/errors';
import RegistrationPage from './RegistrationPage';

// The backend's 429 body (backend/app/__init__.py).
const RATE_LIMITED = 'Too many requests. Wait a moment and try again.';

const post = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: () => Promise.resolve({ success: true, universities: [], specialties: [] }),
    post: (...args: unknown[]) => post(...args),
  },
}));

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  post.mockReset();
  vi.spyOn(Math, 'random').mockReturnValue(0);
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderRegistration() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={['/registration']}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route
            path="/registration"
            element={<RegistrationPage />}
          />
          <Route
            path="/team"
            element={<p>TEAM PAGE</p>}
          />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'REGISTER' }));
}

test('a rate-limited registration counts down on the button and registers on the retry', async () => {
  post.mockRejectedValueOnce(new ApiError(429, RATE_LIMITED, 1)).mockResolvedValueOnce({
    role: 'participant',
    user_id: 1,
    user: { role: 'participant', email: 'ivan@example.com' },
  });
  renderRegistration();
  const button = await screen.findByRole('button', { name: 'Retrying automatically' });
  expect(button).toHaveAttribute('aria-disabled', 'true');
  expect(button).toHaveTextContent('RETRYING… 1s');
  expect(screen.getByRole('status')).toHaveTextContent(/lots of people are registering/i);
  expect(await screen.findByText('TEAM PAGE', {}, { timeout: 3000 })).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(2);
});

test('editing a field during the countdown drops the retry', async () => {
  post.mockRejectedValue(new ApiError(429, RATE_LIMITED, 1));
  renderRegistration();
  await screen.findByRole('button', { name: 'Retrying automatically' });
  fireEvent.change(screen.getByPlaceholderText('Ivan'), { target: { value: 'Petar' } });
  expect(await screen.findByRole('button', { name: 'REGISTER' })).not.toHaveAttribute(
    'aria-disabled',
  );
  await new Promise((resolve) => setTimeout(resolve, 1500));
  expect(post).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(RATE_LIMITED)).toBeNull();
});

test('a 429 asking for more than a minute shows the server message at once', async () => {
  post.mockRejectedValue(new ApiError(429, RATE_LIMITED, 120));
  renderRegistration();
  expect(await screen.findByText(RATE_LIMITED)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'REGISTER' })).not.toHaveAttribute('aria-disabled');
  expect(post).toHaveBeenCalledTimes(1);
});
