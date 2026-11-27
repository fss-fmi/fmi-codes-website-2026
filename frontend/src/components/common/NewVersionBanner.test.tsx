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

type Stamp = [id: string, builtAt: number];
const A: Stamp = ['aaaaaaaaaaaa', 2000];
const B: Stamp = ['bbbbbbbbbbbb', 3000];
const C: Stamp = ['cccccccccccc', 4000];
const OLDER: Stamp = ['999999999999', 1000];

function page(stamp: Stamp | null, status = 200) {
  const meta =
    stamp === null
      ? ''
      : `<meta name="build-id" content="${stamp[0]}" data-built-at="${stamp[1]}">`;
  return new Response(`<!doctype html><html><head>${meta}</head><body></body></html>`, {
    status,
    headers: { 'content-type': 'text/html' },
  });
}

function serve(...stamps: Stamp[]) {
  for (const stamp of stamps) fetchMock.mockResolvedValueOnce(page(stamp));
}

function runBuild([id, builtAt]: Stamp) {
  const meta = document.createElement('meta');
  meta.name = 'build-id';
  meta.content = id;
  meta.dataset.builtAt = String(builtAt);
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
  runBuild(A);
  serve(A);
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledWith('/index.html', { cache: 'no-cache' });
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('a newer build served shows the banner in the live region after a poll', async () => {
  runBuild(A);
  serve(B);
  renderBanner();
  const region = screen.getByRole('status');
  expect(region).toBeEmptyDOMElement();
  expect(fetchMock).not.toHaveBeenCalled();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  expect(region).toContainElement(screen.getByText(TEXT));
});

test('an earlier build served once, an old pod mid-rollout, shows nothing', async () => {
  runBuild(A);
  serve(OLDER, A, OLDER);
  renderBanner();
  await poll();
  await poll();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('an earlier build served on two checks in a row, a rollback, shows the banner', async () => {
  runBuild(A);
  serve(OLDER, OLDER);
  renderBanner();
  await poll();
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
});

test('an old pod reached once after the banner shows neither hides nor replaces it', async () => {
  runBuild(A);
  serve(B, OLDER, B);
  renderBanner();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  await poll();
  expect(screen.getByText(TEXT)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('a dismissed banner stays hidden when an old pod is reached once', async () => {
  runBuild(A);
  serve(B, OLDER);
  renderBanner();
  await poll();
  fireEvent.click(await screen.findByRole('button', { name: 'Dismiss' }));
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test("the server serving the tab's own code again, rebuilt later, hides the banner", async () => {
  runBuild(A);
  serve(B, [A[0], 9000]);
  renderBanner();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('a rebuild of the same code shows nothing', async () => {
  runBuild(A);
  serve([A[0], 9000]);
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('the banner stays when a later poll reaches a pod with the running build again', async () => {
  runBuild(A);
  serve(B, A);
  renderBanner();
  await poll();
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  expect(screen.getByText(TEXT)).toBeInTheDocument();
});

test('a failed fetch shows nothing', async () => {
  runBuild(A);
  fetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
  renderBanner();
  await poll();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(screen.queryByText(TEXT)).not.toBeInTheDocument();
});

test('an error page with no build id shows nothing', async () => {
  runBuild(A);
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
  runBuild(A);
  serve(B);
  renderBanner();
  await poll();
  fireEvent.click(await screen.findByRole('button', { name: 'RELOAD' }));
  expect(reloadPage).toHaveBeenCalledTimes(1);
});

test('a dismissed build stays hidden, and an even newer one shows the banner again', async () => {
  runBuild(A);
  serve(B, B, C);
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
  runBuild(A);
  serve(B);
  renderBanner();
  expect(fetchMock).not.toHaveBeenCalled();
  await act(async () => {
    window.dispatchEvent(new Event('visibilitychange'));
  });
  expect(await screen.findByText(TEXT)).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});
