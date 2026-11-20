// Reloads the page when a build file under /assets/ fails to load. Mid-rollout that means the
// HTML came from one frontend version and the file was asked of a pod running the other. This is
// a plain script loaded before the bundle because the bundle is the whole app: if it fails, no
// app code runs to notice.
(() => {
  const KEY = 'asset-guard-reloads';
  const MAX_RELOADS = 5;
  const DELAY_MS = 2000;

  let store;
  try {
    store = sessionStorage;
    store.getItem(KEY);
  } catch {
    // Without storage the reloads can't be counted, so a broken deploy would loop.
    return;
  }

  let failed = false;

  const isBuildAsset = (target) => {
    let url = '';
    if (target instanceof window.HTMLScriptElement) url = target.src;
    else if (target instanceof window.HTMLLinkElement) url = target.href;
    if (!url) return false;
    try {
      const parsed = new URL(url, location.href);
      return parsed.origin === location.origin && parsed.pathname.startsWith('/assets/');
    } catch {
      return false;
    }
  };

  // Load errors don't bubble, so only a capturing listener on window sees them.
  window.addEventListener(
    'error',
    (event) => {
      if (failed || !isBuildAsset(event.target)) return;
      failed = true;
      try {
        const reloads = Number(store.getItem(KEY)) || 0;
        if (reloads >= MAX_RELOADS) return;
        store.setItem(KEY, String(reloads + 1));
        setTimeout(() => location.reload(), DELAY_MS * (reloads + 1));
      } catch {
        // Storage refused the write: stop rather than reload uncounted.
      }
    },
    true,
  );

  // load fires after a failed file too, so only a page that loaded everything resets the count.
  window.addEventListener('load', () => {
    if (failed) return;
    try {
      store.removeItem(KEY);
    } catch {
      // Nothing to reset.
    }
  });
})();
