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

test('a mentor row says how many picks still count', async () => {
  const data: PrefStatus = {
    teams_submitted: 0,
    teams_total: 0,
    mentors_submitted: 2,
    mentors_total: 4,
    teams: [],
    mentors: [
      { id: 1, name: 'All Count', submitted: true, picks_counting: 3, picks_saved: 3 },
      { id: 2, name: 'Some Count', submitted: true, picks_counting: 2, picks_saved: 3 },
      { id: 3, name: 'None Count', submitted: false, picks_counting: 0, picks_saved: 3 },
      { id: 4, name: 'Never Ranked', submitted: false, picks_counting: 0, picks_saved: 0 },
    ],
  };
  get.mockResolvedValue({ success: true, ...data });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PreferencesPanel />
    </QueryClientProvider>,
  );

  const mark = async (name: string) =>
    (await screen.findByText(name)).nextElementSibling?.textContent;
  expect(await mark('All Count')).toBe('✓');
  expect(await mark('Some Count')).toBe('✓ (2 of 3 picks count)');
  expect(await mark('None Count')).toBe('— (0 of 3 picks count)');
  expect(await mark('Never Ranked')).toBe('—');
});
