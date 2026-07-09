import Panel from '@/components/common/Panel';

/** Captain-only panel showing the team invite code. */
export default function JoinCodePanel({ joinCode }: { joinCode: string }) {
  return (
    <Panel title="JOIN CODE">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <span className="px-label">CODE</span>
        <code
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '0.85rem',
            color: 'var(--px-teal)',
            letterSpacing: '0.15em',
            background: 'var(--px-bg-elevated)',
            padding: '8px 14px',
            border: '1px solid var(--px-teal-dim)',
          }}
        >
          {joinCode}
        </code>
      </div>
    </Panel>
  );
}
