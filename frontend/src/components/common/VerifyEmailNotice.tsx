import { useState } from 'react';
import Button from '@/components/common/Button';
import FormAlert from '@/components/common/FormAlert';
import api from '@/lib/api';

/**
 * Tells an unverified participant to check their inbox and lets them request
 * a fresh verification link. Renders nothing once the email is verified.
 */
export default function VerifyEmailNotice({
  email,
  verified,
  message = 'Verify your email address to create, join or apply to a team.',
}: {
  email?: string;
  verified?: boolean;
  message?: string;
}) {
  const [status, setStatus] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const [sending, setSending] = useState(false);

  if (verified !== false) return null;

  async function resend() {
    setSending(true);
    setStatus(null);
    try {
      const data = await api.post<{ success: boolean; message?: string }>(
        '/api/auth/resend-verification',
        {},
      );
      setStatus({ kind: 'success', text: data.message ?? 'Verification link sent.' });
    } catch (err: unknown) {
      setStatus({ kind: 'error', text: (err as Error)?.message ?? 'Could not send the link.' });
    } finally {
      setSending(false);
    }
  }

  return (
    <FormAlert kind="error">
      <p style={{ margin: '0 0 12px 0' }}>
        {message}
        {email && (
          <>
            {' '}
            We sent a link to <strong>{email}</strong>.
          </>
        )}
      </p>
      {status && (
        <p
          style={{
            margin: '0 0 12px 0',
            color: `var(--px-${status.kind === 'success' ? 'green' : 'danger'})`,
          }}
        >
          {status.text}
        </p>
      )}
      <Button
        variant="secondary"
        type="button"
        onClick={resend}
        disabled={sending}
      >
        {sending ? 'SENDING…' : 'RESEND VERIFICATION EMAIL'}
      </Button>
    </FormAlert>
  );
}
