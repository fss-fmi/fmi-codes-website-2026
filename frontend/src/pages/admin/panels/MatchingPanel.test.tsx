import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import MatchingPanel from './MatchingPanel';

const mockConfig = vi.hoisted(() => ({ PREFERENCES_OPEN: true }));

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) =>
      Promise.resolve(
        url === '/api/matching-status'
          ? { success: true, confirmed: false }
          : { success: true, results: [] },
      ),
    post: () => Promise.resolve({ success: true }),
  },
}));

vi.mock('@/context/ConfigContext', () => ({ useConfig: () => mockConfig }));

const WARNING = /preference submissions are still open/i;

function openRunDialog() {
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
  return (document.querySelector('dialog') as HTMLElement).textContent ?? '';
}

test('RUN MATCHING warns while submissions are open', () => {
  mockConfig.PREFERENCES_OPEN = true;
  expect(openRunDialog()).toMatch(WARNING);
});

test('RUN MATCHING has no warning once submissions are closed', () => {
  mockConfig.PREFERENCES_OPEN = false;
  const text = openRunDialog();
  expect(text).toMatch(/overwrite any previous results/i);
  expect(text).not.toMatch(WARNING);
});
