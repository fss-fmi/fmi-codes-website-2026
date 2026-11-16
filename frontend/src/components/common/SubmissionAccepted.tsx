import type { ReactNode } from 'react';
import Panel from '@/components/common/Panel';

interface Props {
  ranking: { id: number; name: string }[];
  updated: boolean;
  onUpdate: () => void;
  children?: ReactNode;
}

export default function SubmissionAccepted({ ranking, updated, onUpdate, children }: Props) {
  return (
    <Panel title="SUBMISSION ACCEPTED">
      <p
        role="status"
        className="px-body"
        style={{ color: 'var(--px-teal)', margin: '0 0 16px 0' }}
      >
        &gt; {updated ? 'Preferences updated.' : 'Preferences saved successfully.'}
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
