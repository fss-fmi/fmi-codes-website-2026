import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import LoginPage from './LoginPage';

const post = vi.fn();

vi.mock('@/lib/api', () => ({
  default: { post: (...args: unknown[]) => post(...args) },
}));

let mobile = false;
const mediaListeners = new Set<(e: { matches: boolean }) => void>();

function setMobile(value: boolean) {
  mobile = value;
  act(() => mediaListeners.forEach((listener) => listener({ matches: value })));
}

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  mobile = false;
  mediaListeners.clear();
  post.mockReset();
  vi.stubGlobal('ResizeObserver', FakeResizeObserver);
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return mobile;
    },
    media: query,
    addEventListener: (_: string, listener: (e: { matches: boolean }) => void) =>
      mediaListeners.add(listener),
    removeEventListener: (_: string, listener: (e: { matches: boolean }) => void) =>
      mediaListeners.delete(listener),
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderLogin() {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route
          path="/login"
          element={<LoginPage />}
        />
        <Route
          path="/team"
          element={<p>TEAM PAGE</p>}
        />
        <Route
          path="/mentorDashboard"
          element={<p>MENTOR DASHBOARD</p>}
        />
        <Route
          path="/admin/matching"
          element={<p>MISSION CONTROL</p>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

const roleSelect = () => screen.queryByRole('combobox', { name: /sign in as/i });
const roleButtons = () => screen.queryByRole('group', { name: /sign in role/i });

function signIn() {
  fireEvent.change(screen.getByLabelText(/email/i), { target: { value: 'user@example.com' } });
  fireEvent.change(screen.getByLabelText(/password/i), {
    target: { value: 'correct horse battery' },
  });
  fireEvent.click(screen.getByRole('button', { name: /sign in/i }));
}

test('desktop shows the three role buttons and no role dropdown', () => {
  renderLogin();
  expect(roleButtons()).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'PARTICIPANT' })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  expect(roleSelect()).toBeNull();
});

test('phones show a labelled role dropdown with every role and no role buttons', () => {
  mobile = true;
  renderLogin();
  const select = roleSelect();
  expect(select).toHaveValue('participant');
  expect(
    Array.from((select as HTMLSelectElement).options).map((o) => [o.value, o.textContent]),
  ).toEqual([
    ['participant', 'PARTICIPANT'],
    ['mentor', 'MENTOR'],
    ['admin', 'ADMIN'],
  ]);
  expect(roleButtons()).toBeNull();
});

test.each([
  ['participant', 'TEAM PAGE'],
  ['mentor', 'MENTOR DASHBOARD'],
  ['admin', 'MISSION CONTROL'],
] as const)('the dropdown signs in as %s and redirects there', async (role, landing) => {
  mobile = true;
  post.mockResolvedValue({
    success: true,
    role,
    user_id: 1,
    user: { role, email: 'user@example.com' },
  });
  renderLogin();
  fireEvent.change(roleSelect()!, { target: { value: role } });
  signIn();
  expect(await screen.findByText(landing)).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith('/api/auth/login', {
    email: 'user@example.com',
    password: 'correct horse battery',
    role,
  });
});

test('ADMIN in the dropdown hides FORGOT PASSWORD, as the button does', () => {
  mobile = true;
  renderLogin();
  expect(screen.getByRole('button', { name: /forgot password/i })).toBeInTheDocument();
  fireEvent.change(roleSelect()!, { target: { value: 'admin' } });
  expect(screen.queryByRole('button', { name: /forgot password/i })).toBeNull();
});

test('the chosen role survives crossing the breakpoint both ways', () => {
  renderLogin();
  fireEvent.click(screen.getByRole('button', { name: 'MENTOR' }));

  setMobile(true);
  expect(roleButtons()).toBeNull();
  expect(roleSelect()).toHaveValue('mentor');

  fireEvent.change(roleSelect()!, { target: { value: 'admin' } });
  setMobile(false);
  expect(roleSelect()).toBeNull();
  expect(screen.getByRole('button', { name: 'ADMIN' })).toHaveAttribute('aria-pressed', 'true');
});

test('the reset view hides the dropdown, as it hides the buttons', () => {
  mobile = true;
  renderLogin();
  fireEvent.click(screen.getByRole('button', { name: /forgot password/i }));
  expect(roleSelect()).toBeNull();
  expect(roleButtons()).toBeNull();
});
