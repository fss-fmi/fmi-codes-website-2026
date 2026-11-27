export interface Build {
  id: string;
  builtAt: number;
}

/** `offer` is the build the card offers; `pending` an earlier build seen once, waiting for a second check. */
export interface CheckState {
  offer: Build | null;
  pending: Build | null;
}

export const IDLE: CheckState = { offer: null, pending: null };

/** The build the `build-id` Vite plugin wrote into a page; null in dev, which has none. */
export function readBuild(doc: Document): Build | null {
  const meta = doc.querySelector('meta[name="build-id"]');
  const id = meta?.getAttribute('content');
  const builtAt = Number(meta?.getAttribute('data-built-at'));
  if (!id || !Number.isFinite(builtAt) || builtAt <= 0) return null;
  return { id, builtAt };
}

/**
 * What one check of the served build means for a tab running `running`. A later build counts at
 * once. An earlier one counts only when two checks in a row serve it: a rollback, or parallel
 * builds that stamped out of order, rather than an old pod still serving for the few seconds of
 * a rollout. The server serving the tab's own code again clears the offer.
 */
export function nextState(state: CheckState, served: Build | null, running: Build): CheckState {
  if (served === null) return state;
  const reference = state.offer ?? running;
  if (served.id === reference.id) return { offer: state.offer, pending: null };
  const settled =
    served.builtAt > reference.builtAt ||
    (state.pending !== null && state.pending.id === served.id);
  if (!settled) return { offer: state.offer, pending: served };
  return { offer: served.id === running.id ? null : served, pending: null };
}

/**
 * The build of the index.html served now. Plain fetch, not api.ts: the page isn't JSON and a
 * 401 here means nothing. 'no-cache' revalidates, so nginx can answer 304 on the ETag.
 */
export async function fetchServedBuild(): Promise<Build | null> {
  const res = await fetch('/index.html', { cache: 'no-cache' });
  if (!res.ok) return null;
  return readBuild(new DOMParser().parseFromString(await res.text(), 'text/html'));
}

/** Its own export so tests can mock it: jsdom can't spy on location.reload. */
export const reloadPage = () => window.location.reload();
