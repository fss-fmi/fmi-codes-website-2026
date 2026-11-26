import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import { ApiError, NetworkError } from '@/lib/errors';
import MatchingPanel from './MatchingPanel';

// `polled` is what ConfigContext last fetched; `live` is what /api/config answers now.
const flags = vi.hoisted(() => ({ polled: true, live: true as boolean | 'down' }));
const runMatching = vi.hoisted(() => ({
  reject: null as Error | null,
  warnings: [] as string[],
}));
const exportFailure = vi.hoisted(() => ({ reject: null as Error | null }));
const exportBody = vi.hoisted(() => ({ value: null as object | null }));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => {
      if (url === '/api/config') {
        return flags.live === 'down'
          ? Promise.reject(new TypeError('Failed to fetch'))
          : Promise.resolve({ PREFERENCES_OPEN: flags.live });
      }
      if (url === '/api/admin/matching-export' && exportFailure.reject) {
        return Promise.reject(exportFailure.reject);
      }
      if (url === '/api/admin/matching-export' && exportBody.value) {
        return Promise.resolve(exportBody.value);
      }
      return Promise.resolve(
        url === '/api/matching-status'
          ? { success: true, confirmed: false }
          : { success: true, results: [] },
      );
    },
    post: () =>
      runMatching.reject
        ? Promise.reject(runMatching.reject)
        : Promise.resolve({ success: true, warnings: runMatching.warnings }),
  },
}));

afterEach(() => {
  Object.assign(runMatching, { reject: null, warnings: [] });
  exportFailure.reject = null;
  exportBody.value = null;
});

vi.mock('@/context/ConfigContext', () => ({
  useConfig: () => ({ PREFERENCES_OPEN: flags.polled }),
}));

const WARNING = /preference submissions are still open/i;

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MatchingPanel />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// jsdom never opens the <dialog>, so read its text directly.
const dialogText = () => (document.querySelector('dialog') as HTMLElement).textContent ?? '';

async function clickRun() {
  fireEvent.click(screen.getByRole('button', { name: 'RUN MATCHING' }));
  await waitFor(() => expect(dialogText()).toMatch(/overwrite any previous results/i));
  return dialogText();
}

async function openRunDialog() {
  renderPanel();
  return clickRun();
}

test('RUN MATCHING warns while submissions are open', async () => {
  Object.assign(flags, { polled: true, live: true });
  expect(await openRunDialog()).toMatch(WARNING);
});

test('RUN MATCHING has no warning once submissions are closed', async () => {
  Object.assign(flags, { polled: false, live: false });
  expect(await openRunDialog()).not.toMatch(WARNING);
});

test('the warning follows the live flag, not a poll from before a scheduled close', async () => {
  Object.assign(flags, { polled: true, live: false });
  expect(await openRunDialog()).not.toMatch(WARNING);
});

test('if the live check fails the last polled value decides', async () => {
  Object.assign(flags, { polled: true, live: 'down' });
  expect(await openRunDialog()).toMatch(WARNING);
});

async function runIt() {
  Object.assign(flags, { polled: false, live: false });
  await openRunDialog();
  fireEvent.click(within(document.querySelector('dialog') as HTMLElement).getByText('CONFIRM'));
}

test.each([
  [
    'refused by the server',
    new ApiError(400, 'No active registered teams found'),
    'No active registered teams found',
  ],
  ['with no answer', new NetworkError(), 'Network error. Please try again.'],
])('a run %s toasts the reason', async (_case, err, shown) => {
  runMatching.reject = err;
  await runIt();
  expect(await screen.findByText(shown)).toBeInTheDocument();
  expect(screen.queryByText('Matching complete.')).toBeNull();
});

test("a run's warnings reach the admin alongside the success toast", async () => {
  runMatching.warnings = [
    '2 team(s) have not submitted mentor preferences',
    '1 team(s) received fewer than 3 mentors — not enough mentors available to fill all slots',
  ];
  await runIt();
  expect(
    await screen.findByText(
      'Matching warnings: 2 team(s) have not submitted mentor preferences; 1 team(s) received fewer than 3 mentors — not enough mentors available to fill all slots',
    ),
  ).toBeInTheDocument();
  expect(screen.getByText('Matching complete.')).toBeInTheDocument();
});

test('a failed EXPORT toasts the server reason', async () => {
  exportFailure.reject = new ApiError(403, 'Admin access required');
  await openRunDialog();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  expect(await screen.findByText('Admin access required')).toBeInTheDocument();
});

const EXPORT = {
  success: true,
  teams: [
    {
      team_name: 'Alpha',
      mentors: [
        { mentor_name: 'Ana Petrova', company_name: 'Acme' },
        { mentor_name: 'Ivan Ivanov', company_name: '' },
      ],
    },
  ],
  total_assignments: 2,
  violations: ["Mentor 'Ana Petrova' is assigned to 4 teams (max 3)"],
  generated_at: '2026-03-14T18:00:00.123456+00:00',
};

async function openExport(body: object = EXPORT) {
  exportBody.value = body;
  renderPanel();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  await waitFor(() => expect(document.querySelector('pre')).not.toBeNull());
  return document.querySelector('pre') as HTMLElement;
}

test('EXPORT shows the run as readable text', async () => {
  // textContent, not toHaveTextContent: its normaliser would hide the double space.
  expect((await openExport()).textContent).toBe(
    [
      'MATCHING EXPORT  2026-03-14 18:00 UTC',
      '2 assignments, 1 team',
      '',
      'Alpha: Ana Petrova (Acme), Ivan Ivanov',
      '',
      'Violations:',
      "- Mentor 'Ana Petrova' is assigned to 4 teams (max 3)",
    ].join('\n'),
  );
});

test('an empty run exports as no assignments and no violations', async () => {
  const pre = await openExport({ ...EXPORT, teams: [], total_assignments: 0, violations: [] });
  expect(pre.textContent).toBe(
    [
      'MATCHING EXPORT  2026-03-14 18:00 UTC',
      '0 assignments, 0 teams',
      '',
      'No assignments.',
      '',
      'Violations: none',
    ].join('\n'),
  );
});

test('a new run closes the export of the previous one', async () => {
  await openExport();
  Object.assign(flags, { polled: false, live: false });
  await clickRun();
  fireEvent.click(within(document.querySelector('dialog') as HTMLElement).getByText('CONFIRM'));
  expect(await screen.findByText('Matching complete.')).toBeInTheDocument();
  expect(document.querySelector('pre')).toBeNull();
});
