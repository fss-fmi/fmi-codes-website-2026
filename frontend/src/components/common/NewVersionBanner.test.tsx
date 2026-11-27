import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import NewVersionBanner from './NewVersionBanner';
import { reloadPage } from '@/lib/buildId';

vi.mock('@/lib/buildId', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/buildId')>()),
  reloadPage: vi.fn(),
}));

const fetchMock = vi.fn();
const TEXT = 'A new version of the site is available.';

function page(id: string | null, status = 200) {
  const meta = id === null ? '' : `<meta name="build-id" content="${id}">`;
  return new Response(`<!doctype html><html><head>${meta}</head><body></body></html>`, {
    status,
    headers: { 'content-type': 'text/html' },
  });
}

function serve(...ids: string[]) {
  for (const id of ids) fetchMock.mockResolvedValueOnce(page(id));
}

function runBuild(id: string) {
  const meta = document.createElement('meta');
  meta.name = 'build-id';
  meta.content = id;
  document.head.appendChild(meta);
}

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <NewVersionBanner />
    </QueryClientProvider>,
  );
}

async function poll() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30_000);
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  fetchMock.mockReset();
  vi.mocked(reloadPage).mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  document.head.querySelectorAll('meta[name="build-id"]').forEach((meta) => meta.remove());
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test('the same build served shows nothing', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('aaaaaaaaaaaa');
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledWith('/index.html', { cache: 'no-cache' });
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('a different build served shows the banner after a poll', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('bbbbbbbbbbbb');
  renderBanner();
  expect(fetchMock).not.toHaveBeenCalled();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  expect(screen.getByRole('status')).toBeInTheDocument();
});

test('the banner stays when a later poll reaches a pod with the running build again', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('bbbbbbbbbbbb', 'aaaaaaaaaaaa');
  renderBanner();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.getByText(TEXT)).toBeInTheDocument();
});

test('a failed fetch shows nothing', async () => {
  runBuild('aaaaaaaaaaaa');
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('an error page with no build id shows nothing', async () => {
  runBuild('aaaaaaaaaaaa');
  fetchMock.mockResolvedValue(page(null, 503));
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('a page without a build id (dev) never fetches', async () => {
  renderBanner();
  await poll();
  await act(async () => {
    window.dispatchEvent(new Event('visibilitychange'));
  });
  expect(fetchMock).not.toHaveBeenCalled();
});

test('RELOAD reloads the page', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('bbbbbbbbbbbb');
  renderBanner();
  await poll();
  fireEvent.click(await screen.findByRole('button', { name: 'RELOAD' }));
  expect(reloadPage).toHaveBeenCalledTimes(1);
});

test('a dismissed build stays hidden, and an even newer one shows the banner again', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('bbbbbbbbbbbb', 'bbbbbbbbbbbb', 'cccccccccccc');
  renderBanner();
  await poll();
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();

  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();

  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
});

test('coming back to the tab checks at once', async () => {
  runBuild('aaaaaaaaaaaa');
  serve('bbbbbbbbbbbb');
  renderBanner();
  expect(fetchMock).not.toHaveBeenCalled();
  await act(async () => {
    window.dispatchEvent(new Event('visibilitychange'));
  });
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
