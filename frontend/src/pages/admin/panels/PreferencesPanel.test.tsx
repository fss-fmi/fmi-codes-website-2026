import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import PreferencesPanel from './PreferencesPanel';
import type { PrefStatus } from './shared';

const get = vi.fn();

vi.mock('@/lib/api', () => ({ default: { get: (url: string) => get(url) } }));

// recharts' ResponsiveContainer needs a ResizeObserver, which jsdom lacks.
vi.mock('@/components/admin/DonutChart', () => ({ default: () => null }));

test('team and mentor rows show their names', async () => {
  const data: PrefStatus = {
    teams_submitted: 1,
    teams_total: 2,
    mentors_submitted: 0,
    mentors_total: 1,
    teams: [
      { id: 3, team_name: 'Code Wizards', submitted: true },
      { id: 8, team_name: 'Null Pointers', submitted: false },
    ],
    mentors: [{ id: 4, name: 'Maria Petrova', submitted: false }],
  };
  get.mockResolvedValue({ success: true, ...data });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PreferencesPanel />
    </QueryClientProvider>,
  );

  expect(await screen.findByText('Code Wizards')).toBeInTheDocument();
  expect(screen.getByText('Null Pointers')).toBeInTheDocument();
  expect(screen.getByText('Maria Petrova')).toBeInTheDocument();
});
