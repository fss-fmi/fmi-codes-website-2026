interface Props {
  label: string;
  value: number | string;
  unit?: string;
  color?: string;
  icon?: string;
}

export default function KPICard({ label, value, unit, color = '#60a5fa', icon }: Props) {
  return (
    <div
      className="glass-card"
      style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '4px' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
        {icon && <span style={{ fontSize: '1.2rem' }}>{icon}</span>}
        <span
          style={{
            fontSize: '0.75rem',
            fontWeight: 700,
            color: 'var(--muted)',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ fontSize: '2rem', fontWeight: 900, color, letterSpacing: '-0.02em' }}>
        {value}
        {unit && (
          <span style={{ fontSize: '1rem', color: 'var(--muted)', marginLeft: '4px' }}>{unit}</span>
        )}
      </div>
    </div>
  );
}
