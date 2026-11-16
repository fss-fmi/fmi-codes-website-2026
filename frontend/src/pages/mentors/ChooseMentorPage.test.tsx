import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '@/context/AuthContext';
import { ChooseMentorContent } from './ChooseMentorPage';

const get = vi.fn();
const mockConfig = vi.hoisted(() => ({ PREFERENCES_OPEN: true, isLoading: false }));

vi.mock('@/lib/api', () => ({
  default: { get: (url: string) => get(url), post: vi.fn() },
}));

vi.mock('@/context/ConfigContext', () => ({ useConfig: () => mockConfig }));

const SAVED = [
  { mentor_id: 4, rank: 1, mentor_name: 'Ana Petrova' },
  { mentor_id: 5, rank: 2, mentor_name: 'Boris Ivanov' },
  { mentor_id: 6, rank: 3, mentor_name: 'Vera Koleva' },
];

function answer(isRegistered: boolean, preferences: typeof SAVED = []) {
  get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/teams/7')
      return Promise.resolve({ team: { id: 7, is_registered: isRegistered } });
    if (url === '/api/matching-status') return Promise.resolve({ confirmed: false });
    if (url === '/api/teams/7/mentor-preferences') return Promise.resolve({ preferences });
    if (url === '/api/teams/7/available-mentors') return Promise.resolve({ mentors: [] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

function renderAsCaptain() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <AuthContext.Provider
          value={{
            user: { role: 'participant', team_id: 7, is_captain: true },
            role: 'participant',
            isLoading: false,
            login: () => {},
            logout: () => {},
            refreshUser: () => Promise.resolve(),
          }}
        >
          <ChooseMentorContent />
        </AuthContext.Provider>
      </QueryClientProvider>
    </MemoryRouter>
  );
  const view = render(tree());
  return { rerender: () => view.rerender(tree()) };
}

beforeEach(() => {
  mockConfig.PREFERENCES_OPEN = true;
  mockConfig.isLoading = false;
});

test('a team that is not registered is told so before choosing anything', async () => {
  answer(false);
  renderAsCaptain();
  expect(await screen.findByText('NOT REGISTERED')).toBeInTheDocument();
  expect(
    screen.getByText(/only registered teams take part in mentor matching/i),
  ).toBeInTheDocument();
  expect(get).not.toHaveBeenCalledWith('/api/teams/7/available-mentors');
});

test('a registered team gets the mentor picker', async () => {
  answer(true);
  renderAsCaptain();
  expect(await screen.findByText(/STEP 1/)).toBeInTheDocument();
  expect(screen.queryByText('NOT REGISTERED')).toBeNull();
  expect(get).toHaveBeenCalledWith('/api/teams/7/available-mentors');
});

test('while submissions are closed a team without a ranking gets no picker', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer(true);
  renderAsCaptain();
  expect(
    await screen.findByText(/preference submission is closed\. your team/i),
  ).toBeInTheDocument();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(get).not.toHaveBeenCalledWith('/api/teams/7/available-mentors');
});

test('while submissions are closed a saved ranking is read-only', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer(true, SAVED);
  renderAsCaptain();
  expect(await screen.findByText('Ana Petrova')).toBeInTheDocument();
  expect(screen.getByText(/this ranking can no longer be changed/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'CHANGE PREFERENCES' })).toBeNull();
});

test('closing submissions on an open page hides the edit button without a reload', async () => {
  answer(true, SAVED);
  const { rerender } = renderAsCaptain();
  expect(await screen.findByRole('button', { name: 'CHANGE PREFERENCES' })).toBeInTheDocument();

  mockConfig.PREFERENCES_OPEN = false;
  rerender();
  expect(screen.queryByRole('button', { name: 'CHANGE PREFERENCES' })).toBeNull();
  expect(screen.getByText(/this ranking can no longer be changed/i)).toBeInTheDocument();
});

test('nothing renders as closed while the flags are still loading', () => {
  mockConfig.PREFERENCES_OPEN = false;
  mockConfig.isLoading = true;
  answer(true);
  renderAsCaptain();
  expect(screen.queryByText(/preference submission is closed/i)).toBeNull();
});
