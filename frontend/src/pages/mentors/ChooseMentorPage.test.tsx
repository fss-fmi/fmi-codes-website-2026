import { fireEvent, render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ApiError, NetworkError } from '@/lib/errors';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '@/context/AuthContext';
import { ChooseMentorContent } from './ChooseMentorPage';

const get = vi.fn();
const post = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => get(url),
    post: (url: string, body: unknown) => post(url, body),
  },
}));

const mockConfig = vi.hoisted(() => ({ PREFERENCES_OPEN: true, isLoading: false, isLoaded: true }));

vi.mock('@/context/ConfigContext', () => ({ useConfig: () => mockConfig }));

beforeEach(() => {
  mockConfig.PREFERENCES_OPEN = true;
  mockConfig.isLoading = false;
  mockConfig.isLoaded = true;
});

const MENTORS = [
  { mentor_id: 1, name: 'Ada Lovelace', company_name: 'Engines' },
  { mentor_id: 2, name: 'Grace Hopper', company_name: 'Compilers' },
  { mentor_id: 3, name: 'Alan Turing', company_name: 'Machines' },
  { mentor_id: 4, name: 'Linus Torvalds', company_name: 'Kernels' },
];

function answer(
  isRegistered: boolean,
  {
    preferences = [] as { mentor_id: number; rank: number; mentor_name: string }[],
    confirmed = false,
    mentors = [] as typeof MENTORS,
  } = {},
) {
  get.mockReset().mockImplementation((url: string) => {
    if (url === '/api/teams/7')
      return Promise.resolve({ team: { id: 7, is_registered: isRegistered } });
    if (url === '/api/matching-status') return Promise.resolve({ confirmed });
    if (url === '/api/teams/7/mentor-preferences') return Promise.resolve({ preferences });
    if (url === '/api/teams/7/available-mentors') return Promise.resolve({ mentors });
    return Promise.reject(new Error(`unexpected ${url}`));
  });
  post.mockReset();
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

async function pick(...names: string[]) {
  for (const name of names) {
    fireEvent.click(await screen.findByRole('button', { name: new RegExp(name) }));
  }
  fireEvent.click(screen.getByRole('button', { name: 'NEXT: RANK MENTORS' }));
}

function rankingShown() {
  const list = screen.getByRole('list', { name: 'Your ranking' });
  return within(list)
    .getAllByRole('listitem')
    .map((li) => li.textContent);
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

test('first submit shows SUBMISSION ACCEPTED with the mentor names, no reload', async () => {
  answer(true, { mentors: MENTORS });
  post.mockResolvedValue({ success: true });
  renderAsCaptain();

  await pick('Ada', 'Grace', 'Alan');
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByText(/Preferences saved successfully\./)).toHaveFocus();
  expect(screen.getByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Ada Lovelace', '#2Grace Hopper', '#3Alan Turing']);
  expect(screen.getByRole('button', { name: 'UPDATE PREFERENCES' })).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith('/api/teams/7/mentor-preferences', {
    preferences: [
      { mentor_id: 1, rank: 1 },
      { mentor_id: 2, rank: 2 },
      { mentor_id: 3, rank: 3 },
    ],
  });
});

test('loading with a saved ranking shows SUBMISSION ACCEPTED straight away', async () => {
  answer(true, {
    preferences: [
      { mentor_id: 3, rank: 3, mentor_name: 'Alan Turing' },
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 2, rank: 2, mentor_name: 'Grace Hopper' },
    ],
  });
  renderAsCaptain();

  expect(await screen.findByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(
    screen.getByText('SUBMISSION ACCEPTED', { selector: '.px-status-chip' }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Preferences saved successfully\./)).not.toHaveFocus();
  expect(rankingShown()).toEqual(['#1Ada Lovelace', '#2Grace Hopper', '#3Alan Turing']);
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(get).not.toHaveBeenCalledWith('/api/teams/7/available-mentors');
});

test('CANCEL leaves the edit flow without saving', async () => {
  answer(true, {
    mentors: MENTORS,
    preferences: [
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 2, rank: 2, mentor_name: 'Grace Hopper' },
      { mentor_id: 3, rank: 3, mentor_name: 'Alan Turing' },
    ],
  });
  renderAsCaptain();

  fireEvent.click(await screen.findByRole('button', { name: 'UPDATE PREFERENCES' }));
  fireEvent.click(await screen.findByRole('button', { name: /Ada/ }));
  fireEvent.click(screen.getByRole('button', { name: 'CANCEL' }));

  expect(screen.getByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Ada Lovelace', '#2Grace Hopper', '#3Alan Turing']);
  expect(post).not.toHaveBeenCalled();
});

test('a saved mentor who is no longer offered drops out of the pre-filled pick', async () => {
  answer(true, {
    mentors: MENTORS,
    preferences: [
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 9, rank: 2, mentor_name: 'Gone Mentor' },
      { mentor_id: 2, rank: 3, mentor_name: 'Grace Hopper' },
    ],
  });
  post.mockResolvedValue({ success: true });
  renderAsCaptain();

  fireEvent.click(await screen.findByRole('button', { name: 'UPDATE PREFERENCES' }));
  expect(await screen.findByText('STEP 1 — SELECT 3 MENTORS (2/3)')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'NEXT: RANK MENTORS' })).toBeDisabled();

  await pick('Linus');
  expect(screen.getByText('Engines')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'UPDATE PREFERENCES' }));

  expect(await screen.findByText(/Preferences updated\./)).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith('/api/teams/7/mentor-preferences', {
    preferences: [
      { mentor_id: 1, rank: 1 },
      { mentor_id: 2, rank: 2 },
      { mentor_id: 4, rank: 3 },
    ],
  });
});

test('an update is labelled as one and shows the new ranking, not the old', async () => {
  answer(true, {
    mentors: MENTORS,
    preferences: [
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 2, rank: 2, mentor_name: 'Grace Hopper' },
      { mentor_id: 3, rank: 3, mentor_name: 'Alan Turing' },
    ],
  });
  post.mockResolvedValue({ success: true });
  renderAsCaptain();

  fireEvent.click(await screen.findByRole('button', { name: 'UPDATE PREFERENCES' }));
  expect(await screen.findByRole('button', { name: /Ada/ })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(screen.getByRole('button', { name: /Grace/ })).toHaveAttribute('aria-pressed', 'true');
  expect(screen.getByRole('button', { name: /Alan/ })).toHaveAttribute('aria-pressed', 'true');

  fireEvent.click(screen.getByRole('button', { name: /Ada/ }));
  await pick('Linus');
  expect(screen.queryByRole('button', { name: 'SUBMIT PREFERENCES' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'UPDATE PREFERENCES' }));

  expect(await screen.findByText(/Preferences updated\./)).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Grace Hopper', '#2Alan Turing', '#3Linus Torvalds']);
});

test('a failed submit keeps the form and shows the server error', async () => {
  answer(true, { mentors: MENTORS });
  post.mockRejectedValue(new ApiError(400, 'Only registered teams can rank mentors'));
  renderAsCaptain();

  await pick('Ada', 'Grace', 'Alan');
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Only registered teams can rank mentors',
  );
  expect(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' })).toBeEnabled();
  expect(screen.getByText('STEP 2 — DRAG TO RANK')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeNull();
});

test('a submit that never reaches the server says so in plain words', async () => {
  answer(true, { mentors: MENTORS });
  post.mockRejectedValue(new NetworkError());
  renderAsCaptain();

  await pick('Ada', 'Grace', 'Alan');
  fireEvent.click(screen.getByRole('button', { name: 'SUBMIT PREFERENCES' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('Network error. Please try again.');
});

test('confirmed matching shows MATCHING CONFIRMED instead', async () => {
  answer(true, {
    confirmed: true,
    preferences: [{ mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' }],
  });
  renderAsCaptain();

  expect(await screen.findByRole('heading', { name: '> MATCHING CONFIRMED' })).toBeInTheDocument();
  expect(screen.queryByText('SUBMISSION ACCEPTED')).toBeNull();
});

// ── preference submission switched off ────────────────────────────

test('while submissions are closed a team without a ranking gets no picker', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer(true);
  renderAsCaptain();
  expect(await screen.findByRole('heading', { name: 'SUBMISSIONS CLOSED' })).toBeInTheDocument();
  expect(screen.getByText(/your team can rank mentors only while/i)).toBeInTheDocument();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(get).not.toHaveBeenCalledWith('/api/teams/7/available-mentors');
});

test('while submissions are closed a saved ranking is read-only', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  answer(true, {
    preferences: [
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 2, rank: 2, mentor_name: 'Grace Hopper' },
      { mentor_id: 3, rank: 3, mentor_name: 'Alan Turing' },
    ],
  });
  renderAsCaptain();
  expect(await screen.findByRole('heading', { name: 'SUBMISSION ACCEPTED' })).toBeInTheDocument();
  expect(rankingShown()).toEqual(['#1Ada Lovelace', '#2Grace Hopper', '#3Alan Turing']);
  expect(screen.getByText(/this ranking can no longer be changed/i)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'UPDATE PREFERENCES' })).toBeNull();
});

test('a close mid-edit drops back to the saved ranking, and a reopen does not resume the edit', async () => {
  answer(true, {
    preferences: [
      { mentor_id: 1, rank: 1, mentor_name: 'Ada Lovelace' },
      { mentor_id: 2, rank: 2, mentor_name: 'Grace Hopper' },
      { mentor_id: 3, rank: 3, mentor_name: 'Alan Turing' },
    ],
    mentors: MENTORS,
  });
  const { rerender } = renderAsCaptain();
  fireEvent.click(await screen.findByRole('button', { name: 'UPDATE PREFERENCES' }));
  expect(await screen.findByText(/STEP 1/)).toBeInTheDocument();

  mockConfig.PREFERENCES_OPEN = false;
  rerender();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(screen.queryByRole('button', { name: 'UPDATE PREFERENCES' })).toBeNull();
  expect(rankingShown()).toEqual(['#1Ada Lovelace', '#2Grace Hopper', '#3Alan Turing']);

  mockConfig.PREFERENCES_OPEN = true;
  rerender();
  expect(screen.queryByText(/STEP 1/)).toBeNull();
  expect(screen.getByRole('button', { name: 'UPDATE PREFERENCES' })).toBeInTheDocument();
});

test('nothing renders as closed while the flags are still loading', () => {
  mockConfig.PREFERENCES_OPEN = false;
  mockConfig.isLoading = true;
  mockConfig.isLoaded = false;
  answer(true);
  renderAsCaptain();
  expect(screen.queryByText(/preference submission is closed/i)).toBeNull();
});

test('flags that never loaded are not mistaken for closed submissions', async () => {
  mockConfig.PREFERENCES_OPEN = false;
  mockConfig.isLoaded = false;
  answer(true);
  renderAsCaptain();
  expect(
    await screen.findByText(/could not check whether preference submission is open/i),
  ).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'SUBMISSIONS CLOSED' })).toBeNull();
});
