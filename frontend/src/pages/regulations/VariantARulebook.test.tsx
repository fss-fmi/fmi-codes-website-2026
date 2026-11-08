import { act, fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import VariantARulebook from './VariantARulebook';
import { CHAPTERS } from './shared';

vi.mock('@/lib/api', () => ({
  default: {
    get: () =>
      Promise.resolve({
        success: true,
        regulations: Array.from({ length: 13 }, (_, i) => ({
          question: `Question ${i + 1}`,
          answer: `Answer ${i + 1}`,
        })),
      }),
  },
}));

let navHeight = 0;
let resize: (() => void) | undefined;
let reducedMotion = false;

class FakeResizeObserver {
  constructor(callback: () => void) {
    resize = callback;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

class FakeIntersectionObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  navHeight = 57;
  reducedMotion = false;
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver);
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: reducedMotion, media: query }));
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    return { height: this.classList.contains('rulebook-nav') ? navHeight : 0 } as DOMRect;
  });
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.scrollTo = vi.fn();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderRulebook() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <VariantARulebook />
    </QueryClientProvider>,
  );
}

const chapterNavHeight = () => screen.getByRole('main').style.getPropertyValue('--rulebook-nav-h');

test('publishes the chapter nav height on its page and updates it on resize', () => {
  renderRulebook();
  expect(chapterNavHeight()).toBe('57px');
  navHeight = 104;
  act(() => resize?.());
  expect(chapterNavHeight()).toBe('104px');
});

test('a chapter button scrolls its chapter to the top, offset by scroll-margin-top', async () => {
  renderRulebook();
  await screen.findByText('Question 1');
  const chapter = CHAPTERS[2];
  fireEvent.click(screen.getByRole('button', { name: `${chapter.num} · ${chapter.title}` }));
  const scroll = vi.mocked(Element.prototype.scrollIntoView);
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(scroll.mock.contexts[0]).toBe(document.getElementById(`chapter-${chapter.key}`));
  // No behavior: smooth or instant comes from the page's reduced-motion-aware CSS.
  expect(scroll).toHaveBeenCalledWith({ block: 'start' });
});

describe('the chapter row on phones, when it overflows', () => {
  beforeEach(() => {
    vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockImplementation(function (this: Element) {
      return this.classList.contains('rulebook-nav-list') ? 600 : 0;
    });
    vi.spyOn(Element.prototype, 'clientWidth', 'get').mockImplementation(function (this: Element) {
      return this.classList.contains('rulebook-nav-list') ? 300 : 0;
    });
  });

  const rowScroll = () => {
    const list = document.querySelector('.rulebook-nav-list');
    const scroll = vi.mocked(Element.prototype.scrollTo);
    return scroll.mock.calls.filter((_, i) => scroll.mock.contexts[i] === list);
  };

  const expectOneRowScroll = (behavior: ScrollBehavior) => {
    const calls = rowScroll();
    expect(calls).toHaveLength(1);
    expect(calls[0][0]).toMatchObject({ behavior });
  };

  test('slides the active chapter into view smoothly', () => {
    renderRulebook();
    expectOneRowScroll('smooth');
  });

  test('slides it instantly when the user prefers reduced motion', () => {
    reducedMotion = true;
    renderRulebook();
    expectOneRowScroll('auto');
  });
});
