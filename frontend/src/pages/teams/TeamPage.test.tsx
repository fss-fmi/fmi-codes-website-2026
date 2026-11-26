import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '@/components/common/useToast';
import { TEAMS_LOCKED } from '@/lib/teamsLock';
import { TeamPageContent } from './TeamPage';

const config = vi.hoisted(() => ({
  PREFERENCES_OPEN: false,
  MATCHING_CONFIRMED: false,
  REQUIRE_EMAIL_VERIFICATION: false,
  isLoading: false,
  isLoaded: true,
}));
const me = vi.hoisted(() => ({ teamId: 7 as number | null }));

vi.mock('@/context/ConfigContext', () => ({ useConfig: () => config }));

vi.mock('@/hooks/useMe', () => ({
  useMe: () => ({
    data: { success: true, user: { id: 1, role: 'participant', team_id: me.teamId } },
    isPending: false,
    refetch: () => Promise.resolve(),
  }),
}));

const TEAM = vi.hoisted(() => ({
  id: 7,
  team_name: 'Night Owls',
  status: 'active',
  captain_id: 1,
  is_registered: true,
  participant_count: 3,
  join_code: 'ABCD1234',
  members: [
    { id: 1, first_name: 'Ana', last_name: 'Petrova', email: 'ana@example.test', is_captain: true },
    {
      id: 2,
      first_name: 'Ivan',
      last_name: 'Ivanov',
      email: 'ivan@example.test',
      is_captain: false,
    },
    {
      id: 3,
      first_name: 'Mila',
      last_name: 'Koleva',
      email: 'mila@example.test',
      is_captain: false,
    },
  ],
  mentors: [],
}));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => {
      if (url === '/api/teams/7') return Promise.resolve({ team: TEAM });
      if (url === '/api/teams/7/requests')
        return Promise.resolve({
          requests: [
            {
              request_id: 9,
              participant_id: 5,
              first_name: 'Rada',
              last_name: 'Stoeva',
              created_at: '2026-03-01T10:00:00Z',
            },
          ],
        });
      if (url === '/api/teams/my-applications') return Promise.resolve({ applications: [] });
      return Promise.resolve({ preferences: [] });
    },
  },
}));

afterEach(() => {
  config.MATCHING_CONFIRMED = false;
  me.teamId = 7;
});

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <ToastProvider>
          <TeamPageContent />
        </ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

test('while frozen the captain gets the lock note and no REMOVE, DISBAND or ACCEPT', async () => {
  config.MATCHING_CONFIRMED = true;
  renderPage();
  expect(await screen.findByText(`> ${TEAMS_LOCKED}`)).toBeInTheDocument();
  expect(await screen.findByRole('button', { name: 'Decline Rada Stoeva' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Accept Rada Stoeva' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'REMOVE' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'DISBAND TEAM' })).toBeNull();
  expect(
    screen.getByText("> The organizers haven't assigned mentors to your team yet."),
  ).toBeInTheDocument();
});

test('before the freeze the captain can remove, accept and disband', async () => {
  renderPage();
  expect(await screen.findByRole('button', { name: 'Accept Rada Stoeva' })).toBeInTheDocument();
  expect(screen.getAllByRole('button', { name: 'REMOVE' })).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'DISBAND TEAM' })).toBeInTheDocument();
  expect(screen.queryByText(`> ${TEAMS_LOCKED}`)).toBeNull();
});

test('while frozen a member gets no LEAVE', async () => {
  config.MATCHING_CONFIRMED = true;
  TEAM.captain_id = 2;
  try {
    renderPage();
    expect(await screen.findByText(`> ${TEAMS_LOCKED}`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'LEAVE TEAM' })).toBeNull();
  } finally {
    TEAM.captain_id = 1;
  }
});

test('while frozen a participant with no team is offered no way to join one', async () => {
  config.MATCHING_CONFIRMED = true;
  me.teamId = null;
  renderPage();
  expect(await screen.findByText(`> ${TEAMS_LOCKED}`)).toBeInTheDocument();
  for (const name of ['CREATE TEAM', 'JOIN WITH CODE', 'BROWSE TEAMS']) {
    expect(screen.queryByText(name)).toBeNull();
  }
});
