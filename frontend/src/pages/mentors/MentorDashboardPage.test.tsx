import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MentorDashboardContent } from './MentorDashboardPage';

const get = vi.fn();
const post = vi.fn();
const mockConfig = vi.hoisted(() => ({ PREFERENCES_OPEN: true, isLoading: false }));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => get(url),
    post: (url: string, body: unknown) => post(url, body),
  },
}));

vi.mock('@/context/ConfigContext', () => ({ useConfig: () => mockConfig }));

const TEAMS = [
  { team_id: 1, team_name: 'Night Owls', participant_count: 3 },
  { team_id: 2, team_name: 'Lockstep', participant_count: 4 },
  { team_id: 3, team_name: 'Keystone', participant_count: 5 },
];

function answer(preferences: { team_id: number; rank: number; team_name: string }[] = []) {
  get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/matching-status') return Promise.resolve({ confirmed: false });
    if (url === '/api/mentors/team-preferences') return Promise.resolve({ preferences });
    if (url === '/api/mentors/available-teams') return Promise.resolve({ teams: TEAMS });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const tree = () => (
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <MentorDashboardContent />
      </QueryClientProvider>
    </MemoryRouter>
  );
  const view = render(tree());
  return { invalidate, rerender: () => view.rerender(tree()) };
}

beforeEach(() => {
  mockConfig.PREFERENCES_OPEN = true;
  mockConfig.isLoading = false;
  post.mockReset();
});

test('while submissions are closed a mentor without a ranking gets no picker', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer();
  renderDashboard();
  expect(await screen.findByText(/preference submission is closed\. you can/i)).toBeInTheDocument();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(get).not.toHaveBeenCalledWith('/api/mentors/available-teams');
});

test('while submissions are closed a saved ranking is read-only', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer(TEAMS.map((t, i) => ({ team_id: t.team_id, rank: i + 1, team_name: t.team_name })));
  renderDashboard();
  expect(await screen.findByText('Night Owls')).toBeInTheDocument();
  expect(screen.getByText(/this ranking can no longer be changed/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'CHANGE PREFERENCES' })).toBeNull();
});

test('closing submissions mid-edit drops the page into the closed state', async () => {
  answer();
  const { rerender } = renderDashboard();
  expect(await screen.findByText(/STEP 1/)).toBeInTheDocument();

  mockConfig.PREFERENCES_OPEN = false;
  rerender();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(screen.getByText('SUBMISSIONS CLOSED', { selector: 'span' })).toBeInTheDocument();
});

test('a submit refused because submissions just closed says so and refetches the flags', async () => {
  answer();
  post.mockRejectedValue(new Error('Preference submission is closed'));
  const { invalidate } = renderDashboard();
  for (const t of TEAMS) fireEvent.click(await screen.findByText(t.team_name));
  fireEvent.click(screen.getByRole('button', { name: 'NEXT: RANK TEAMS' }));
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Preference submission closed before your ranking was saved.',
  );
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['config'] });
});
