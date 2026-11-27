const SELECTOR = 'meta[name="build-id"]';

/** The build id the `build-id` Vite plugin wrote into a page; null in dev, which has none. */
export function readBuildId(doc: Document): string | null {
  return doc.querySelector(SELECTOR)?.getAttribute('content') ?? null;
}

/**
 * The build id of the index.html served now. Plain fetch, not api.ts: the page isn't JSON
 * and a 401 here means nothing. 'no-cache' revalidates, so nginx can answer 304 on the ETag.
 */
export async function fetchServedBuildId(): Promise<string | null> {
  const res = await fetch('/index.html', { cache: 'no-cache' });
  if (!res.ok) return null;
  const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
  return readBuildId(doc);
}

/** Its own export so tests can mock it: jsdom can't spy on location.reload. */
export const reloadPage = () => window.location.reload();
