import { useEffect, useRef, type ReactNode } from 'react';
import Panel from '@/components/common/Panel';

interface Props {
  ranking: { id: number; name: string }[];
  // Set right after a save: picks the message and moves focus here, since the
  // button that was clicked is gone.
  justSaved: 'submitted' | 'updated' | null;
  onUpdate: () => void;
  children?: ReactNode;
}

export default function SubmissionAccepted({ ranking, justSaved, onUpdate, children }: Props) {
  const messageRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (justSaved) messageRef.current?.focus();
  }, [justSaved]);

  return (
    <Panel title="SUBMISSION ACCEPTED">
      <p
        ref={messageRef}
        tabIndex={-1}
        className="px-body"
        style={{ color: 'var(--px-teal)', margin: '0 0 16px 0', outline: 'none' }}
      >
        &gt; {justSaved === 'updated' ? 'Preferences updated.' : 'Preferences saved successfully.'}
      </p>
      <ol
        aria-label="Your ranking"
        style={{ listStyle: 'none', margin: 0, padding: 0 }}
      >
        {ranking.map((item, i) => (
          <li
            key={item.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 16,
              padding: '12px 0',
              borderBottom: '1px solid var(--px-teal-dim)',
            }}
          >
            <span
              className="px-label"
              style={{
                color: 'var(--px-teal)',
                minWidth: 36,
                textAlign: 'center',
                fontSize: '0.6rem',
              }}
            >
              #{i + 1}
            </span>
            <span
              style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}
            >
              {item.name}
            </span>
          </li>
        ))}
      </ol>
      <div style={{ marginTop: 24, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <button
          type="button"
          className="px-btn-secondary"
          onClick={onUpdate}
        >
          UPDATE PREFERENCES
        </button>
        {children}
      </div>
    </Panel>
  );
}
