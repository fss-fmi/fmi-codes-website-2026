import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthContext } from '@/context/AuthContext';
import { ProfileContent } from './ProfilePage';
import type { Role, User } from '@/types/auth';

function makeAuthValue(role: Role, overrides: Partial<User> = {}) {
  const user: User = { role, email: 'user@example.com', ...overrides };
  return {
    user,
    role,
    isLoading: false,
    login: () => {},
    logout: () => {},
    refreshUser: () => Promise.resolve(),
  };
}

function renderAs(role: Role, overrides: Partial<User> = {}) {
  render(
    <MemoryRouter>
      <AuthContext.Provider value={makeAuthValue(role, overrides)}>
        <ProfileContent />
      </AuthContext.Provider>
    </MemoryRouter>,
  );
}

test('admin does not see CHANGE PASSWORD panel', () => {
  renderAs('admin');
  expect(screen.queryByText('CHANGE PASSWORD')).toBeNull();
  expect(screen.queryByRole('button', { name: /update password/i })).toBeNull();
  expect(screen.getByText('ACCOUNT')).toBeInTheDocument();
  expect(screen.getByText('PROFILE INFO')).toBeInTheDocument();
});

test('participant sees CHANGE PASSWORD panel', () => {
  renderAs('participant');
  expect(screen.getByText('CHANGE PASSWORD')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /update password/i })).toBeInTheDocument();
});

test('mentor sees CHANGE PASSWORD panel', () => {
  renderAs('mentor');
  expect(screen.getByText('CHANGE PASSWORD')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /update password/i })).toBeInTheDocument();
});

test('unverified participant sees NOT VERIFIED and a resend button', () => {
  renderAs('participant', { email_verified: false });
  expect(screen.getByText('NOT VERIFIED')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /resend verification email/i })).toBeInTheDocument();
});

test('verified participant sees VERIFIED and no resend button', () => {
  renderAs('participant', { email_verified: true });
  expect(screen.getByText('VERIFIED')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /resend verification email/i })).toBeNull();
});

test('mentor sees no email verification status', () => {
  renderAs('mentor');
  expect(screen.queryByText('EMAIL STATUS')).toBeNull();
  expect(screen.queryByRole('button', { name: /resend verification email/i })).toBeNull();
});
