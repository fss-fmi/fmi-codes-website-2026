import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import TeamsPanel from './TeamsPanel';

const calls = vi.hoisted(() => ({
  del: [] as string[],
  put: [] as { url: string; body: unknown }[],
}));

const TEAM = vi.hoisted(() => ({
  id: 7,
  team_name: 'Night Owls',
  status: 'active',
  captain_id: 1,
  is_registered: true,
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
  mentors: [{ mentor_id: 41, mentor_name: 'Kalin Stoev' }],
}));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => {
      if (url === '/api/admin/teams/registration-status')
        return Promise.resolve({
          registered_count: 1,
          max_registered: 18,
          queue_count: 0,
          registered_teams: [{ id: 7, team_name: 'Night Owls', participant_count: 3 }],
          queued_teams: [],
          unregistered_teams: [],
          pending_teams: [{ id: 8, team_name: 'Duo', participant_count: 2 }],
        });
      if (url === '/api/teams/7') return Promise.resolve({ team: TEAM });
      if (url === '/api/mentors')
        return Promise.resolve({
          mentors: [
            { mentor_id: 41, name: 'Kalin Stoev' },
            { mentor_id: 42, name: 'Vera Dimova' },
          ],
        });
      if (url === '/api/admin/matching-results')
        return Promise.resolve({
          results: [
            { team_id: 7, mentor_id: 41 },
            { team_id: 9, mentor_id: 42 },
            { team_id: 10, mentor_id: 42 },
          ],
        });
      return Promise.reject(new Error(`unexpected ${url}`));
    },
    delete: (url: string) => {
      calls.del.push(url);
      return Promise.resolve({ success: true });
    },
    put: (url: string, body: unknown) => {
      calls.put.push({ url, body });
      return Promise.resolve({ success: true, changed: true, mentor_count: 2, warnings: [] });
    },
    post: () => Promise.resolve({ success: true }),
  },
}));

afterEach(() => {
  calls.del = [];
  calls.put = [];
});

async function openTeam() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <TeamsPanel />
      </ToastProvider>
    </QueryClientProvider>,
  );
  const select = await screen.findByLabelText('TEAM');
  expect(within(select).getByText('Duo (PENDING, 2/6)')).toBeInTheDocument();
  fireEvent.change(select, { target: { value: '7' } });
  await screen.findByText('MEMBERS (3/6)');
}

const dialog = () => document.querySelector('dialog') as HTMLElement;

test('a captain is removed only once a new captain is picked', async () => {
  await openTeam();
  const removeCaptain = screen.getByRole('button', { name: 'Remove Ana Petrova' });
  expect(removeCaptain).toBeDisabled();

  fireEvent.change(screen.getByLabelText('New captain'), { target: { value: '3' } });
  expect(removeCaptain).toBeEnabled();
  fireEvent.click(removeCaptain);
  await waitFor(() => expect(dialog().textContent).toContain('Mila Koleva becomes the captain.'));
  fireEvent.click(within(dialog()).getByText('REMOVE'));

  await waitFor(() => expect(calls.del).toEqual(['/api/admin/teams/7/members/1?new_captain_id=3']));
});

test('a member who is not captain is removed without a successor', async () => {
  await openTeam();
  fireEvent.click(screen.getByRole('button', { name: 'Remove Ivan Ivanov' }));
  await waitFor(() =>
    expect(dialog().textContent).toContain('Remove Ivan Ivanov from Night Owls?'),
  );
  fireEvent.click(within(dialog()).getByText('REMOVE'));
  await waitFor(() => expect(calls.del).toEqual(['/api/admin/teams/7/members/2']));
});

test('SAVE MENTORS sends the edited list, and each option shows its load', async () => {
  await openTeam();
  const add = screen.getByLabelText('Add mentor');
  await waitFor(() => expect(within(add).getByText('Vera Dimova (2 teams)')).toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'SAVE MENTORS' })).toBeDisabled();

  fireEvent.change(add, { target: { value: '42' } });
  fireEvent.click(screen.getByRole('button', { name: 'ADD' }));
  fireEvent.click(screen.getByRole('button', { name: 'SAVE MENTORS' }));

  await waitFor(() =>
    expect(calls.put).toEqual([
      { url: '/api/admin/teams/7/mentors', body: { mentor_ids: [41, 42] } },
    ]),
  );
  expect(await screen.findByText('Mentors saved.')).toBeInTheDocument();
});

test('removing every mentor saves an empty list', async () => {
  await openTeam();
  fireEvent.click(await screen.findByRole('button', { name: 'Remove mentor Kalin Stoev' }));
  fireEvent.click(screen.getByRole('button', { name: 'SAVE MENTORS' }));
  await waitFor(() => expect(calls.put[0]?.body).toEqual({ mentor_ids: [] }));
});
