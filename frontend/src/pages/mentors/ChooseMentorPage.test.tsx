import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '@/context/AuthContext';
import { ChooseMentorContent } from './ChooseMentorPage';

const get = vi.fn();

vi.mock('@/lib/api', () => ({
  default: { get: (url: string) => get(url), post: vi.fn() },
}));

function answer(isRegistered: boolean) {
  get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/teams/7')
      return Promise.resolve({ team: { id: 7, is_registered: isRegistered } });
    if (url === '/api/matching-status') return Promise.resolve({ confirmed: false });
    if (url === '/api/teams/7/mentor-preferences') return Promise.resolve({ preferences: [] });
    if (url === '/api/teams/7/available-mentors') return Promise.resolve({ mentors: [] });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
}

function renderAsCaptain() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
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
    </MemoryRouter>,
  );
}

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
