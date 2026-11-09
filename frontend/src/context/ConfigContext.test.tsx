import { act, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ConfigProvider, useConfig } from './ConfigContext';

const get = vi.fn();

vi.mock('@/lib/api', () => ({ default: { get: (url: string) => get(url) } }));

function flags(registrationOpen: boolean) {
  return {
    REGISTRATION_OPEN: registrationOpen,
    MENTORS_STAY_TUNED: false,
    RANKINGS_LIVE: false,
    REQUIRE_EMAIL_VERIFICATION: false,
  };
}

function Probe() {
  const { REGISTRATION_OPEN, isLoading } = useConfig();
  return <span>{isLoading ? 'loading' : REGISTRATION_OPEN ? 'open' : 'closed'}</span>;
}

function renderProbe() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ConfigProvider>
        <Probe />
      </ConfigProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  get.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

test('an open page picks up a flag switched in Mission Control without a reload', async () => {
  get.mockResolvedValueOnce(flags(false)).mockResolvedValue(flags(true));
  renderProbe();
  expect(await screen.findByText('closed')).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000);
  });
  expect(await screen.findByText('open')).toBeInTheDocument();
  expect(get).toHaveBeenCalledWith('/api/config');
});

test('a failed refetch keeps the last flags', async () => {
  get.mockResolvedValueOnce(flags(true)).mockRejectedValue(new Error('HTTP 503'));
  renderProbe();
  expect(await screen.findByText('open')).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000);
  });
  expect(get).toHaveBeenCalledTimes(2);
  expect(screen.getByText('open')).toBeInTheDocument();
});

test('a failed first load leaves everything closed', async () => {
  get.mockRejectedValue(new Error('HTTP 503'));
  renderProbe();
  expect(await screen.findByText('closed')).toBeInTheDocument();
});
