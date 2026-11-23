import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import RegistrationPanel from './RegistrationPanel';
import type { RegStatus } from './shared';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => get(url),
    post: (url: string, body: unknown) => post(url, body),
  },
}));

// recharts' ResponsiveContainer needs a ResizeObserver, which jsdom lacks.
vi.mock('@/components/admin/DonutChart', () => ({ default: () => null }));

function status(overrides: Partial<RegStatus> = {}): RegStatus {
  return {
    registered_count: 1,
    max_registered: 18,
    queue_count: 0,
    registered_teams: [{ id: 1, team_name: 'Alpha' }],
    queued_teams: [],
    unregistered_teams: [],
    ...overrides,
  };
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RegistrationPanel />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset();
  post.mockReset().mockResolvedValue({ success: true });
});

test('an unregistered active team is listed and can be registered again', async () => {
  get.mockResolvedValue(status({ unregistered_teams: [{ id: 7, team_name: 'Bravo' }] }));
  renderPanel();

  expect(await screen.findByText('UNREGISTERED (1)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Register Bravo' }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/api/admin/teams/7/register', {}));
});

test('no unregistered panel when every active team has a slot or a queue place', async () => {
  get.mockResolvedValue(status());
  renderPanel();

  expect(await screen.findByText('Alpha')).toBeInTheDocument();
  expect(screen.queryByText(/^UNREGISTERED/)).toBeNull();
});
