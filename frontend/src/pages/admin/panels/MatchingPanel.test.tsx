import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import MatchingPanel from './MatchingPanel';

// `polled` is what ConfigContext last fetched; `live` is what /api/config answers now.
const flags = vi.hoisted(() => ({ polled: true, live: true as boolean | 'down' }));
const runMatching = vi.hoisted(() => ({ reject: null as Error | null }));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => {
      if (url === '/api/config') {
        return flags.live === 'down'
          ? Promise.reject(new TypeError('Failed to fetch'))
          : Promise.resolve({ PREFERENCES_OPEN: flags.live });
      }
      return Promise.resolve(
        url === '/api/matching-status'
          ? { success: true, confirmed: false }
          : { success: true, results: [] },
      );
    },
    post: () =>
      runMatching.reject ? Promise.reject(runMatching.reject) : Promise.resolve({ success: true }),
  },
}));

vi.mock('@/context/ConfigContext', () => ({
  useConfig: () => ({ PREFERENCES_OPEN: flags.polled }),
}));

const WARNING = /preference submissions are still open/i;

async function openRunDialog() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MatchingPanel />
      </ToastProvider>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole('button', { name: 'RUN MATCHING' }));
  // jsdom never opens the <dialog>, so read its text directly.
  const dialog = () => (document.querySelector('dialog') as HTMLElement).textContent ?? '';
  await waitFor(() => expect(dialog()).toMatch(/overwrite any previous results/i));
  return dialog();
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

test.each([
  [
    'refused by the server',
    new Error('No registered teams to match'),
    'No registered teams to match',
  ],
  ['with no answer', new TypeError('Failed to fetch'), 'Network error. Please try again.'],
])('a run %s toasts the reason', async (_case, err, shown) => {
  Object.assign(flags, { polled: false, live: false });
  runMatching.reject = err;
  try {
    await openRunDialog();
    fireEvent.click(within(document.querySelector('dialog') as HTMLElement).getByText('CONFIRM'));
    expect(await screen.findByText(shown)).toBeInTheDocument();
  } finally {
    runMatching.reject = null;
  }
});
