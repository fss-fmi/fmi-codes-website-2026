import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import type { Mock } from 'vitest';
import { ApiError, NetworkError } from '@/lib/errors';
import MatchingPanel from './MatchingPanel';

// `polled` is what ConfigContext last fetched; `live` is what /api/config answers now.
const flags = vi.hoisted(() => ({ polled: true, live: true as boolean | 'down' }));
const runMatching = vi.hoisted(() => ({
  reject: null as Error | null,
  warnings: [] as string[],
  // Set to hold the run request open until the test resolves it.
  gate: null as Promise<object> | null,
}));
const exportFailure = vi.hoisted(() => ({ reject: null as Error | null }));
const exportBody = vi.hoisted(() => ({ value: null as object | null }));
// Set to hold the export request open until the test resolves it.
const exportGate = vi.hoisted(() => ({ promise: null as Promise<object> | null }));
// The body is built when the request is made, so a later change to `confirmed`
// only reaches requests made after it.
const status = vi.hoisted(() => ({ confirmed: false }));
const results = vi.hoisted(() => ({ rows: [] as { team_name: string; mentor_name: string }[] }));

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
      if (url === '/api/admin/matching-export' && exportGate.promise) {
        return exportGate.promise;
      }
      if (url === '/api/admin/matching-export' && exportBody.value) {
        return Promise.resolve(exportBody.value);
      }
      if (url === '/api/matching-status') {
        return Promise.resolve({ success: true, confirmed: status.confirmed });
      }
      return Promise.resolve({ success: true, results: results.rows });
    },
    post: () =>
      runMatching.reject
        ? Promise.reject(runMatching.reject)
        : (runMatching.gate ?? Promise.resolve({ success: true, warnings: runMatching.warnings })),
  },
}));

// jsdom has no URL.createObjectURL, and Node's own rejects a jsdom Blob. The anchor is
// removed right after its click, so the click records what it would have downloaded.
const download = { clicks: [] as { name: string; href: string }[] };
let createObjectURL: Mock<(blob: Blob) => string>;
let revokeObjectURL: Mock<(url: string) => void>;
const URL_KEYS = ['createObjectURL', 'revokeObjectURL'] as const;
const urlDescriptors = new Map<string, PropertyDescriptor | undefined>();

beforeEach(() => {
  let made = 0;
  createObjectURL = vi.fn(() => `blob:export-${++made}`);
  revokeObjectURL = vi.fn();
  for (const key of URL_KEYS) {
    urlDescriptors.set(key, Object.getOwnPropertyDescriptor(URL, key));
    Object.defineProperty(URL, key, {
      value: key === 'createObjectURL' ? createObjectURL : revokeObjectURL,
      configurable: true,
      writable: true,
    });
  }
  download.clicks = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    download.clicks.push({ name: this.download, href: this.href });
  });
});

afterEach(() => {
  // Unmount first, under fake timers: the panel revokes its last file 40 s after
  // unmount, and that must reach the stub now, not a restored URL in a later file.
  vi.useFakeTimers();
  cleanup();
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  for (const key of URL_KEYS) {
    const original = urlDescriptors.get(key);
    if (original) Object.defineProperty(URL, key, original);
    else delete (URL as Partial<Record<(typeof URL_KEYS)[number], unknown>>)[key];
  }
  Object.assign(runMatching, { reject: null, warnings: [], gate: null });
  exportFailure.reject = null;
  exportBody.value = null;
  exportGate.promise = null;
  status.confirmed = false;
  results.rows = [];
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
  return client;
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

const PUBLISHED = 'The current results are published; this run hides them until you confirm again.';

test('RUN MATCHING says a run hides results that are published', async () => {
  Object.assign(flags, { polled: false, live: false });
  status.confirmed = true;
  expect(await openRunDialog()).toContain(PUBLISHED);
});

test('RUN MATCHING says nothing about publishing while results are unconfirmed', async () => {
  Object.assign(flags, { polled: false, live: false });
  expect(await openRunDialog()).not.toContain(PUBLISHED);
});

test('the published sentence follows a confirm made since the panel loaded', async () => {
  Object.assign(flags, { polled: false, live: false });
  const client = renderPanel();
  // The cache must hold the unconfirmed answer, or a dialog reading only the
  // cache would pass too.
  await waitFor(() =>
    expect(client.getQueryData(['matching-status'])).toEqual({ success: true, confirmed: false }),
  );
  status.confirmed = true;
  expect(await clickRun()).toContain(PUBLISHED);
});

test('CONFIRM says what publishing does and that a new run hides it', async () => {
  results.rows = [{ team_name: 'Alpha', mentor_name: 'Ana Petrova' }];
  renderPanel();
  await screen.findByText('RESULTS (1 PAIRS)');
  fireEvent.click(screen.getByRole('button', { name: 'CONFIRM' }));
  await waitFor(() =>
    expect(dialogText()).toContain(
      'Publish the matching results? Teams and mentors will see their assignments. Running matching again hides them until you confirm again.',
    ),
  );
  expect(dialogText()).not.toMatch(/cannot be undone/i);
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
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(download.clicks).toHaveLength(0);
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
  expect(screen.queryByRole('alert')).toBeNull();
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

const EXPORT_MD = {
  ...EXPORT,
  confirmed: false,
  teams_without_mentors: ['Omega'],
};

// No blob.text(): jsdom's Blob may not have it.
function readBlob(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

async function downloaded(count = 1) {
  await waitFor(() => expect(download.clicks).toHaveLength(count));
  const blob = createObjectURL.mock.calls[count - 1][0];
  return { ...download.clicks[count - 1], blob, text: await readBlob(blob) };
}

test('EXPORT downloads the run as a Markdown file', async () => {
  await openExport(EXPORT_MD);
  const file = await downloaded();
  expect(file.name).toBe('matching-export-2026-03-14-1800-utc.md');
  expect(file.href).toBe('blob:export-1');
  expect(file.blob.type).toBe('text/markdown;charset=utf-8');
  const expected = [
    '# 🧭 Matching export',
    '',
    '- 🕒 Generated: 2026-03-14 18:00 UTC',
    '- ⏳ Status: not confirmed',
    '- 🤝 2 assignments, 1 team with mentors',
    '',
    '## 🚀 Assignments',
    '',
    '### 👥 Alpha',
    '',
    '- 💼 Ana Petrova (Acme)',
    '- 💼 Ivan Ivanov',
    '',
    '## \u26A0\uFE0F Teams without mentors',
    '',
    '- 👥 Omega',
    '',
    '## 🚨 Violations',
    '',
    "- Mentor 'Ana Petrova' is assigned to 4 teams (max 3)",
    '',
  ].join('\n');
  expect(file.text).toBe(expected);
  // readAsText drops a BOM, so the byte count is what shows there is none.
  expect(file.blob.size).toBe(new TextEncoder().encode(expected).length);
  // Kept until the next file, so a browser that reads the blob late still gets it.
  expect(revokeObjectURL).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  expect((await downloaded(2)).href).toBe('blob:export-2');
  expect(revokeObjectURL.mock.calls).toEqual([['blob:export-1']]);
  // Leaving the tab revokes the last file only after a grace period (40 s).
  vi.useFakeTimers();
  try {
    cleanup();
    vi.advanceTimersByTime(39_999);
    expect(revokeObjectURL.mock.calls).toEqual([['blob:export-1']]);
    vi.advanceTimersByTime(1);
    expect(revokeObjectURL.mock.calls).toEqual([['blob:export-1'], ['blob:export-2']]);
  } finally {
    vi.useRealTimers();
  }
});

test('a confirmed run says so, and a time without a fraction names the file the same', async () => {
  await openExport({
    ...EXPORT_MD,
    teams: [
      { team_name: 'Alpha', mentors: [{ mentor_name: 'Ana Petrova', company_name: 'Acme' }] },
    ],
    total_assignments: 1,
    confirmed: true,
    teams_without_mentors: [],
    violations: [],
    generated_at: '2026-03-14T18:00:00+00:00',
  });
  const file = await downloaded();
  expect(file.name).toBe('matching-export-2026-03-14-1800-utc.md');
  expect(file.text).toContain('- ✅ Status: confirmed\n- 🤝 1 assignment, 1 team with mentors\n');
});

test('an empty run downloads every section, each saying so', async () => {
  await openExport({
    ...EXPORT_MD,
    teams: [],
    total_assignments: 0,
    teams_without_mentors: [],
    violations: [],
  });
  expect((await downloaded()).text).toBe(
    [
      '# 🧭 Matching export',
      '',
      '- 🕒 Generated: 2026-03-14 18:00 UTC',
      '- ⏳ Status: not confirmed',
      '- 🤝 0 assignments, 0 teams with mentors',
      '',
      '## 🚀 Assignments',
      '',
      'No assignments.',
      '',
      '## \u26A0\uFE0F Teams without mentors',
      '',
      '✅ None.',
      '',
      '## 🚨 Violations',
      '',
      '✅ None.',
      '',
    ].join('\n'),
  );
});

test('names in the file are escaped and kept on one line', async () => {
  await openExport({
    ...EXPORT_MD,
    teams: [
      {
        team_name: 'A|B *x*',
        mentors: [{ mentor_name: 'Ana_Petrova\n<b>', company_name: 'C#Corp' }],
      },
    ],
    total_assignments: 1,
    teams_without_mentors: ['[Omega]'],
    violations: ["Team 'A|B *x*' has 4 mentors (max 3)"],
  });
  const { text } = await downloaded();
  expect(text).toContain(String.raw`### 👥 A\|B \*x\*` + '\n');
  expect(text).toContain(String.raw`- 💼 Ana\_Petrova \<b\> (C\#Corp)` + '\n');
  expect(text).toContain(String.raw`- 👥 \[Omega\]` + '\n');
  expect(text).toContain(String.raw`- Team 'A\|B \*x\*' has 4 mentors (max 3)` + '\n');
});

test('a backend without the new fields still downloads, with the cached status', async () => {
  status.confirmed = true;
  exportBody.value = EXPORT;
  const client = renderPanel();
  await waitFor(() =>
    expect(client.getQueryData(['matching-status'])).toEqual({ success: true, confirmed: true }),
  );
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  const { text } = await downloaded();
  expect(text).toContain('- ✅ Status: confirmed\n');
  expect(text).toContain('## \u26A0\uFE0F Teams without mentors\n\n✅ None.\n');
});

test('a download that fails still shows the export and says only the file failed', async () => {
  createObjectURL.mockImplementation(() => {
    throw new Error('blob refused');
  });
  exportBody.value = EXPORT_MD;
  renderPanel();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  expect(await screen.findByText('Could not download the file.')).toBeInTheDocument();
  expect(document.querySelector('pre')).not.toBeNull();
  expect(screen.queryByText('blob refused')).toBeNull();
  expect(download.clicks).toHaveLength(0);
});

test('an export still in flight when a run finishes is dropped', async () => {
  let resolve!: (body: object) => void;
  exportGate.promise = new Promise((r) => {
    resolve = r;
  });
  Object.assign(flags, { polled: false, live: false });
  renderPanel();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  await clickRun();
  fireEvent.click(within(document.querySelector('dialog') as HTMLElement).getByText('CONFIRM'));
  expect(await screen.findByText('Matching complete.')).toBeInTheDocument();
  await act(async () => {
    resolve(EXPORT_MD);
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(document.querySelector('pre')).toBeNull();
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(download.clicks).toHaveLength(0);
});

test('EXPORT is disabled while its request is in flight, so a double click saves one file', async () => {
  let resolve!: (body: object) => void;
  exportGate.promise = new Promise((r) => {
    resolve = r;
  });
  renderPanel();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  const busy = await screen.findByRole('button', { name: 'EXPORTING…' });
  expect(busy).toBeDisabled();
  fireEvent.click(busy);
  await act(async () => {
    resolve(EXPORT_MD);
    await new Promise((r) => setTimeout(r, 0));
  });
  await downloaded();
  expect(createObjectURL).toHaveBeenCalledTimes(1);
  expect(screen.getByRole('button', { name: 'EXPORT' })).toBeEnabled();
});

test('an export that lands after the admin left the tab downloads nothing', async () => {
  let resolve!: (body: object) => void;
  exportGate.promise = new Promise((r) => {
    resolve = r;
  });
  renderPanel();
  fireEvent.click(screen.getByRole('button', { name: 'EXPORT' }));
  cleanup();
  await act(async () => {
    resolve(EXPORT_MD);
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(createObjectURL).not.toHaveBeenCalled();
  expect(download.clicks).toHaveLength(0);
});

test('EXPORT is disabled while a run is in flight', async () => {
  let resolve!: (body: object) => void;
  runMatching.gate = new Promise((r) => {
    resolve = r;
  });
  Object.assign(flags, { polled: false, live: false });
  renderPanel();
  await clickRun();
  fireEvent.click(within(document.querySelector('dialog') as HTMLElement).getByText('CONFIRM'));
  await screen.findByRole('button', { name: 'RUNNING…' });
  expect(screen.getByRole('button', { name: 'EXPORT' })).toBeDisabled();
  await act(async () => {
    resolve({ success: true, warnings: [] });
    await new Promise((r) => setTimeout(r, 0));
  });
  expect(await screen.findByText('Matching complete.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'EXPORT' })).toBeEnabled();
});
