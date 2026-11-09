import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from '@/components/common/useToast';
import SitePanel from './SitePanel';
import type { FeatureFlag } from './shared';

const get = vi.fn();
const put = vi.fn();

vi.mock('@/lib/api', () => ({
  default: {
    get: (url: string) => get(url),
    put: (url: string, body: unknown) => put(url, body),
    delete: () => Promise.resolve({ success: true }),
  },
}));

function flag(name: FeatureFlag['name'], enabled: boolean): FeatureFlag {
  return {
    name,
    enabled,
    updated_at: '2026-11-09T08:00:00+00:00',
    scheduled_value: null,
    scheduled_at: null,
  };
}

// jsdom never opens the <dialog>, so its buttons are queried as hidden.
function confirmButton(name: string) {
  const dialog = document.querySelector('dialog') as HTMLElement;
  return within(dialog).getByRole('button', { name, hidden: true });
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <SitePanel />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  get.mockReset().mockResolvedValue({
    success: true,
    flags: [
      flag('registration_open', false),
      flag('rankings_live', false),
      flag('mentors_stay_tuned', true),
    ],
  });
  put.mockReset().mockResolvedValue({ success: true });
});

test('switching now asks first, then sends the opposite value', async () => {
  renderPanel();
  fireEvent.click(await screen.findByRole('button', { name: 'OPEN NOW' }));
  expect(put).not.toHaveBeenCalled();

  fireEvent.click(confirmButton('OPEN'));
  await waitFor(() =>
    expect(put).toHaveBeenCalledWith('/api/admin/flags/registration_open', { enabled: true }),
  );
});

test('a schedule is sent in the admin’s local time with its UTC offset', async () => {
  renderPanel();
  await screen.findByText('PARTICIPANT REGISTRATION');
  const [input] = screen.getAllByLabelText(/SCHEDULE OPEN AT/);
  fireEvent.change(input, { target: { value: '2030-03-14T10:30' } });

  fireEvent.click(screen.getAllByRole('button', { name: 'SCHEDULE' })[0]);
  fireEvent.click(confirmButton('SCHEDULE'));
  await waitFor(() => expect(put).toHaveBeenCalled());

  const [url, body] = put.mock.calls[0] as [string, { value: boolean; at: string }];
  expect(url).toBe('/api/admin/flags/registration_open/schedule');
  expect(body.value).toBe(true);
  expect(body.at).toMatch(/^2030-03-14T10:30:00[+-]\d{2}:\d{2}$/);
  expect(new Date(body.at).getTime()).toBe(new Date('2030-03-14T10:30').getTime());
});

test('the roster panel reads ON as the coming-soon placeholder', async () => {
  renderPanel();
  expect(await screen.findByText('COMING SOON')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'SHOW ROSTER NOW' })).toBeInTheDocument();
});
