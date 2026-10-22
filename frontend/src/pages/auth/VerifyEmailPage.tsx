import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import FormAlert from '@/components/common/FormAlert';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';

type State =
  | { kind: 'pending' }
  | { kind: 'success'; text: string }
  | { kind: 'error'; text: string };

const linkStyle = { color: 'var(--px-teal)', textDecoration: 'underline' };

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const { user, refreshUser } = useAuth();
  const [state, setState] = useState<State>(
    token ? { kind: 'pending' } : { kind: 'error', text: 'This verification link is invalid.' },
  );
  // Tokens are single-use: StrictMode's double effect run must not spend it twice.
  const submitted = useRef(false);

  useEffect(() => {
    if (!token || submitted.current) return;
    submitted.current = true;
    api
      .post<{ success: boolean; message?: string }>('/api/auth/verify-email', { token })
      .then((data) => {
        setState({ kind: 'success', text: data.message ?? 'Your email address is verified.' });
        void refreshUser();
      })
      .catch((err: unknown) => {
        setState({
          kind: 'error',
          text: (err as Error)?.message ?? 'Could not verify your email. Please try again.',
        });
      });
  }, [token, refreshUser]);

  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '80vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 24px',
        }}
      >
        <div style={{ width: '100%', maxWidth: '460px' }}>
          <Panel title="VERIFY EMAIL">
            {state.kind === 'pending' && <LoadingSpinner />}

            {state.kind === 'success' && (
              <FormAlert kind="success">
                {state.text}{' '}
                <Link
                  to={user ? '/team' : '/login'}
                  style={linkStyle}
                >
                  {user ? 'Go to your team' : 'Sign in'}
                </Link>
              </FormAlert>
            )}

            {state.kind === 'error' && (
              <FormAlert kind="error">
                {state.text}{' '}
                {user?.role === 'participant' ? (
                  <>
                    Request a new link from your{' '}
                    <Link
                      to="/profile"
                      style={linkStyle}
                    >
                      profile
                    </Link>
                    .
                  </>
                ) : (
                  <>
                    <Link
                      to="/login"
                      style={linkStyle}
                    >
                      Sign in
                    </Link>{' '}
                    and request a new link from your profile.
                  </>
                )}
              </FormAlert>
            )}
          </Panel>
        </div>
      </main>
    </>
  );
}
