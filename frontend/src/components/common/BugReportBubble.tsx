import { useState, useRef, useEffect, useCallback, type FormEvent } from 'react';
import api from '@/lib/api';

const MAX_LEN = 2000;

export default function BugReportBubble() {
  const [open, setOpen] = useState(false);
  const [whatDid, setWhatDid] = useState('');
  const [whatHappened, setWhatHappened] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const panelRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setStatus('idle');
    setErrorMsg('');
    setWhatDid('');
    setWhatHappened('');
  }, []);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') close();
    }
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) close();
    }
    document.addEventListener('keydown', handleKey);
    document.addEventListener('mousedown', handleClick);
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.removeEventListener('mousedown', handleClick);
    };
  }, [open, close]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!whatDid.trim() && !whatHappened.trim()) return;
    setStatus('loading');
    try {
      await api.post('/api/bug-report', {
        what_did: whatDid,
        what_happened: whatHappened,
        page: window.location.href,
      });
      setStatus('success');
    } catch (err) {
      setStatus('error');
      setErrorMsg(err instanceof Error ? err.message : 'Something went wrong.');
    }
  }

  return (
    <>
      <button
        type="button"
        aria-label="Report a bug"
        className="bug-bubble-btn"
        onClick={() => setOpen(true)}
      >
        🐛
      </button>

      {open && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 1201,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(8,9,15,0.72)',
            backdropFilter: 'blur(4px)',
          }}
        >
          <div
            ref={panelRef}
            style={{
              background: 'var(--px-bg-panel)',
              border: '2px solid var(--px-teal-border)',
              padding: '28px 28px 24px',
              width: 'min(480px, calc(100vw - 32px))',
              color: 'var(--px-white)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 4,
              }}
            >
              <h2
                className="px-prompt-heading"
                style={{ margin: 0 }}
              >
                Report a Bug
              </h2>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--px-muted)',
                  cursor: 'pointer',
                  fontSize: '1.1rem',
                  padding: '4px 6px',
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>
            <p
              className="px-muted-body"
              style={{ marginBottom: 20 }}
            >
              Found something broken? Let us know and we'll fix it.
            </p>

            {status === 'success' ? (
              <p
                style={{
                  color: 'var(--px-teal)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.9rem',
                  lineHeight: 1.65,
                  padding: '12px 0',
                }}
              >
                ✓ Bug reported — thank you!
              </p>
            ) : (
              <form
                onSubmit={submit}
                style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <label
                    htmlFor="bug-what-did"
                    className="px-label"
                  >
                    What were you doing?
                  </label>
                  <textarea
                    id="bug-what-did"
                    className="px-input-field"
                    rows={3}
                    maxLength={MAX_LEN}
                    placeholder="Describe the steps that led to the issue..."
                    value={whatDid}
                    onChange={(e) => setWhatDid(e.target.value)}
                    style={{ resize: 'vertical' }}
                  />
                  <span
                    className="px-muted-body"
                    style={{ fontSize: '0.75rem', textAlign: 'right' }}
                  >
                    {whatDid.length} / {MAX_LEN}
                  </span>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <label
                    htmlFor="bug-what-happened"
                    className="px-label"
                  >
                    What happened instead?
                  </label>
                  <textarea
                    id="bug-what-happened"
                    className="px-input-field"
                    rows={3}
                    maxLength={MAX_LEN}
                    placeholder="Describe the unexpected behaviour..."
                    value={whatHappened}
                    onChange={(e) => setWhatHappened(e.target.value)}
                    style={{ resize: 'vertical' }}
                  />
                  <span
                    className="px-muted-body"
                    style={{ fontSize: '0.75rem', textAlign: 'right' }}
                  >
                    {whatHappened.length} / {MAX_LEN}
                  </span>
                </div>

                {status === 'error' && (
                  <p
                    style={{
                      color: 'var(--px-danger)',
                      fontFamily: 'var(--px-mono)',
                      fontSize: '0.85rem',
                    }}
                  >
                    ✕ {errorMsg}
                  </p>
                )}

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
                  <button
                    type="button"
                    className="px-btn-ghost"
                    onClick={close}
                  >
                    CANCEL
                  </button>
                  <button
                    type="submit"
                    className="px-btn-primary"
                    disabled={status === 'loading' || (!whatDid.trim() && !whatHappened.trim())}
                  >
                    {status === 'loading' ? 'SENDING...' : 'SEND REPORT'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </>
  );
}
