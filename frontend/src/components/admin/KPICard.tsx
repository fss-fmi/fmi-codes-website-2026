interface Props {
  label: string;
  value: number | string;
  unit?: string;
}

export default function KPICard({ label, value, unit }: Props) {
  return (
    <div
      style={{
        background: 'var(--px-bg-card)',
        border: '1px solid var(--px-teal-dim)',
        padding: '20px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
      }}
    >
      <span className="px-label">{label}</span>
      <div
        style={{
          fontFamily: 'var(--px-font)',
          fontSize: '1.4rem',
          lineHeight: 1.2,
          color: 'var(--px-teal)',
          letterSpacing: '0.02em',
          wordBreak: 'break-word',
        }}
      >
        {value}
        {unit && (
          <span
            style={{
              fontFamily: 'var(--px-mono)',
              fontSize: '0.8rem',
              color: 'var(--px-muted-strong)',
              marginLeft: 8,
            }}
          >
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
