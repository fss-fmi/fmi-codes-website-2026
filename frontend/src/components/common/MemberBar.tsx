interface Props {
  name: string;
  isCaptain?: boolean;
  role?: string;
}

export default function MemberBar({ name, isCaptain = false, role }: Props) {
  const initial = name ? name[0].toUpperCase() : '?';
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '10px 0',
      }}
    >
      <div
        aria-hidden="true"
        style={{
          width: '36px',
          height: '36px',
          background: 'var(--px-bg-elevated)',
          border: '1px solid var(--px-teal-dim)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontFamily: 'var(--px-font)',
          fontSize: '0.65rem',
          color: 'var(--px-teal)',
          flexShrink: 0,
        }}
      >
        {initial}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.9rem',
            fontWeight: 700,
            color: 'var(--px-white)',
          }}
        >
          {name}
        </div>
        {role && (
          <div
            style={{
              fontFamily: 'var(--px-mono)',
              fontSize: '0.75rem',
              color: 'var(--px-muted-strong)',
            }}
          >
            {role}
          </div>
        )}
      </div>

      {isCaptain && <span className="px-status-chip">CAPTAIN</span>}
    </div>
  );
}
