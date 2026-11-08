import { act, render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Navbar from './Navbar';

let barHeight = 0;
let resize: (() => void) | undefined;
const disconnect = vi.fn();

class FakeResizeObserver {
  constructor(callback: () => void) {
    resize = callback;
  }
  observe() {}
  unobserve() {}
  disconnect = disconnect;
}

beforeEach(() => {
  barHeight = 76;
  resize = undefined;
  disconnect.mockClear();
  document.documentElement.style.removeProperty('--px-navbar-h');
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    return { height: this.classList.contains('px-navbar') ? barHeight : 0 } as DOMRect;
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const navbarHeight = () => document.documentElement.style.getPropertyValue('--px-navbar-h');

function renderNavbar() {
  return render(
    <MemoryRouter>
      <Navbar />
    </MemoryRouter>,
  );
}

test('publishes the bar height on mount', () => {
  renderNavbar();
  expect(navbarHeight()).toBe('76px');
});

test('republishes when the bar resizes, e.g. its links wrap to two rows', () => {
  renderNavbar();
  barHeight = 115;
  act(() => resize?.());
  expect(navbarHeight()).toBe('115px');
});

test('stops observing on unmount and keeps the last value for the next page', () => {
  const { unmount } = renderNavbar();
  unmount();
  expect(disconnect).toHaveBeenCalledTimes(1);
  expect(navbarHeight()).toBe('76px');
});
