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
        borderBottom: '1px solid rgba(148,163,184,0.08)',
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: '36px',
          height: '36px',
          borderRadius: '50%',
          background: 'linear-gradient(135deg, #6366f1, #60a5fa)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: '0.85rem',
          fontWeight: 700,
          color: '#fff',
          flexShrink: 0,
        }}
      >
        {initial}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)' }}>{name}</div>
        {role && <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{role}</div>}
      </div>

      {isCaptain && (
        <span
          style={{
            fontSize: '0.7rem',
            fontWeight: 700,
            background: 'rgba(251,191,36,0.12)',
            color: '#fbbf24',
            border: '1px solid rgba(251,191,36,0.25)',
            padding: '2px 8px',
            borderRadius: '100px',
          }}
        >
          ★ Captain
        </span>
      )}
    </div>
  );
}
