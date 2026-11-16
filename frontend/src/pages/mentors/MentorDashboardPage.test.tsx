import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MentorDashboardContent } from './MentorDashboardPage';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => get(url),
    post: (url: string, body: unknown) => post(url, body),
  },
}));

const TEAMS = [
  { team_id: 1, team_name: 'Alpha', participant_count: 3 },
  { team_id: 2, team_name: 'Bravo', participant_count: 4 },
  { team_id: 3, team_name: 'Charlie', participant_count: 5 },
  { team_id: 4, team_name: 'Delta', participant_count: 6 },
];

function answer({
  preferences = [] as { team_id: number; rank: number; team_name: string }[],
  confirmed = false,
} = {}) {
  get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/matching-status') return Promise.resolve({ confirmed });
    if (url === '/api/mentors/team-preferences') return Promise.resolve({ preferences });
    if (url === '/api/mentors/available-teams') return Promise.resolve({ teams: TEAMS });
    if (url === '/api/mentors/assigned-teams') return Promise.resolve({ teams: [TEAMS[3]] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  post.mockReset();
}

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <MentorDashboardContent />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function pick(...names: string[]) {
  for (const name of names) {
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(name) }));
  }
  fireEvent.click(screen.getByRole('button', { name: 'NEXT: RANK TEAMS' }));
}

function rankingShown() {
  const list = screen.getByRole('list', { name: 'Your ranking' });
  return within(list)
    .getAllByRole('listitem')
    .map((li) => li.textContent);
}

test('first submit shows SUBMISSION ACCEPTED with the ranking, no reload', async () => {
  answer();
  post.mockResolvedValue({ success: true });
  renderDashboard();

  await pick('Alpha', 'Bravo', 'Charlie');
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByText(/Preferences saved successfully\./)).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Alpha', '#2Bravo', '#3Charlie']);
  expect(screen.getByRole('button', { name: 'UPDATE PREFERENCES' })).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith('/api/mentors/team-preferences', {
    preferences: [
      { team_id: 1, rank: 1 },
      { team_id: 2, rank: 2 },
      { team_id: 3, rank: 3 },
    ],
  });
  expect(get.mock.calls.filter(([url]) => url === '/api/mentors/team-preferences')).toHaveLength(1);
});

test('loading with a saved ranking shows SUBMISSION ACCEPTED straight away', async () => {
  answer({
    preferences: [
      { team_id: 2, rank: 2, team_name: 'Bravo' },
      { team_id: 1, rank: 1, team_name: 'Alpha' },
      { team_id: 3, rank: 3, team_name: 'Charlie' },
    ],
  });
  renderDashboard();

  expect(await screen.findByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(
    screen.getByText('SUBMISSION ACCEPTED', { selector: '.px-status-chip' }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Preferences saved successfully\./)).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Alpha', '#2Bravo', '#3Charlie']);
});

test('an update is labelled as one and shows the new ranking, not the old', async () => {
  answer({
    preferences: [
      { team_id: 1, rank: 1, team_name: 'Alpha' },
      { team_id: 2, rank: 2, team_name: 'Bravo' },
      { team_id: 3, rank: 3, team_name: 'Charlie' },
    ],
  });
  post.mockResolvedValue({ success: true });
  renderDashboard();

  fireEvent.click(await screen.findByRole('button', { name: 'UPDATE PREFERENCES' }));
  expect(await screen.findByRole('button', { name: /Alpha/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(screen.getByRole('button', { name: /Bravo/ })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: /Charlie/ })).toHaveAttribute('aria-pressed', 'true');

  fireEvent.click(screen.getByRole('button', { name: /Alpha/ }));
  await pick('Delta');
  expect(screen.queryByRole('button', { name: 'SUBMIT PREFERENCES' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'UPDATE PREFERENCES' }));

  expect(await screen.findByText(/Preferences updated\./)).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Bravo', '#2Charlie', '#3Delta']);
});

test('a failed submit keeps the form and shows the server error', async () => {
  answer();
  post.mockRejectedValue(new Error('Only registered teams can be ranked'));
  renderDashboard();

  await pick('Alpha', 'Bravo', 'Charlie');
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('Only registered teams can be ranked');
  expect(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' })).toBeEnabled();
  expect(screen.getByText('STEP 2 — DRAG TO RANK')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeNull();
});

test('confirmed matching shows the assigned teams instead', async () => {
  answer({
    confirmed: true,
    preferences: [{ team_id: 1, rank: 1, team_name: 'Alpha' }],
  });
  renderDashboard();

  expect(await screen.findByRole('heading', { name: 'ASSIGNED TEAMS' })).toBeInTheDocument();
  expect(await screen.findByText('Delta')).toBeInTheDocument();
  expect(screen.queryByText('SUBMISSION ACCEPTED')).toBeNull();
});
