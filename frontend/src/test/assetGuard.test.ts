import guardSource from '../../public/asset-guard.js?raw';

type Listener = { fn: (event: { target: unknown }) => void; capture: unknown };

function makeStore(initial?: string) {
  const data = new Map<string, string>();
  if (initial !== undefined) data.set('asset-guard-reloads', initial);
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  };
}

function runGuard(store: unknown, target: Window | Record<string, unknown> = {}) {
  const listeners: Record<string, Listener> = {};
  const fakeWindow =
    target instanceof Window
      ? target
      : {
          HTMLScriptElement: window.HTMLScriptElement,
          HTMLLinkElement: window.HTMLLinkElement,
          addEventListener: (type: string, fn: Listener['fn'], capture: unknown) => {
            listeners[type] = { fn, capture };
          },
          ...target,
        };
  const fakeLocation = {
    href: window.location.href,
    origin: window.location.origin,
    reload: vi.fn(),
  };
  new Function('window', 'location', 'sessionStorage', 'setTimeout', guardSource)(
    fakeWindow,
    fakeLocation,
    store,
    setTimeout,
  );
  return { listeners, reload: fakeLocation.reload };
}

function script(src: string) {
  const el = document.createElement('script');
  el.src = src;
  return el;
}

function stylesheet(href: string) {
  const el = document.createElement('link');
  el.rel = 'stylesheet';
  el.href = href;
  return el;
}

describe('asset-guard.js', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('reloads 2 s after a build script fails and counts the reload', () => {
    const store = makeStore();
    const { listeners, reload } = runGuard(store);
    expect(listeners.error.capture).toBe(true);

    listeners.error.fn({ target: script('/assets/index-abc.js') });
    expect(store.data.get('asset-guard-reloads')).toBe('1');
    vi.advanceTimersByTime(1999);
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('treats a failed build stylesheet the same way', () => {
    const store = makeStore();
    const { listeners, reload } = runGuard(store);
    listeners.error.fn({ target: stylesheet('/assets/index-abc.css') });
    vi.runAllTimers();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('schedules one reload however many files fail on the page', () => {
    const store = makeStore();
    const { listeners, reload } = runGuard(store);
    listeners.error.fn({ target: script('/assets/index-abc.js') });
    listeners.error.fn({ target: stylesheet('/assets/index-abc.css') });
    vi.runAllTimers();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(store.data.get('asset-guard-reloads')).toBe('1');
  });

  it('ignores other origins, other paths and errors that are not file loads', () => {
    const store = makeStore();
    const { listeners, reload } = runGuard(store);
    listeners.error.fn({ target: stylesheet('https://fonts.googleapis.com/assets/x.css') });
    listeners.error.fn({ target: script('/images/logo.js') });
    listeners.error.fn({ target: window });
    listeners.error.fn({ target: document.createElement('img') });
    vi.runAllTimers();
    expect(reload).not.toHaveBeenCalled();
    expect(store.data.has('asset-guard-reloads')).toBe(false);
  });

  it('waits longer on each reload in a row', () => {
    const store = makeStore('2');
    const { listeners, reload } = runGuard(store);
    listeners.error.fn({ target: script('/assets/index-abc.js') });
    vi.advanceTimersByTime(5999);
    expect(reload).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(store.data.get('asset-guard-reloads')).toBe('3');
  });

  it('gives up after 5 reloads', () => {
    const store = makeStore('5');
    const { listeners, reload } = runGuard(store);
    listeners.error.fn({ target: script('/assets/index-abc.js') });
    vi.runAllTimers();
    expect(reload).not.toHaveBeenCalled();
    expect(store.data.get('asset-guard-reloads')).toBe('5');
  });

  it('resets the count only after a load with no failed file', () => {
    const clean = makeStore('3');
    runGuard(clean).listeners.load.fn({ target: window });
    expect(clean.data.has('asset-guard-reloads')).toBe(false);

    const broken = makeStore('3');
    const { listeners } = runGuard(broken);
    listeners.error.fn({ target: script('/assets/index-abc.js') });
    listeners.load.fn({ target: window });
    expect(broken.data.get('asset-guard-reloads')).toBe('4');
  });

  it('does nothing when storage is blocked', () => {
    const blocked = {
      getItem: () => {
        throw new DOMException('denied', 'SecurityError');
      },
    };
    const { listeners } = runGuard(blocked);
    expect(listeners.error).toBeUndefined();
    expect(listeners.load).toBeUndefined();
  });

  it('stops without reloading when storage refuses the write', () => {
    const full = {
      ...makeStore(),
      setItem: () => {
        throw new DOMException('full', 'QuotaExceededError');
      },
    };
    const { listeners, reload } = runGuard(full);
    listeners.error.fn({ target: script('/assets/index-abc.js') });
    vi.runAllTimers();
    expect(reload).not.toHaveBeenCalled();
  });

  it('sees a real load error, which does not bubble, through its capturing listener', () => {
    const store = makeStore();
    const { reload } = runGuard(store, window);
    const el = script('/assets/index-abc.js');
    document.head.appendChild(el);
    el.dispatchEvent(new Event('error'));
    el.remove();
    vi.runAllTimers();
    expect(reload).toHaveBeenCalledTimes(1);
  });
});
