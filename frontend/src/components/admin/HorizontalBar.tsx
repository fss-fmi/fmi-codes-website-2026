interface Props {
  label: string;
  value: number;
  max: number;
  color?: string;
}

export default function HorizontalBar({ label, value, max, color = '#60a5fa' }: Props) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '4px 0' }}>
      <div
        style={{
          width: '130px',
          fontSize: '0.8rem',
          color: 'var(--muted)',
          flexShrink: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
      <div
        style={{
          flex: 1,
          height: '6px',
          background: 'rgba(255,255,255,0.06)',
          borderRadius: '100px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: '100px',
            background: color,
            transition: 'width 0.6s ease',
          }}
        />
      </div>
      <div
        style={{
          width: '40px',
          fontSize: '0.8rem',
          fontWeight: 700,
          color: 'var(--text)',
          textAlign: 'right',
          flexShrink: 0,
        }}
      >
        {value}
      </div>
    </div>
  );
}
