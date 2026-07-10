interface Props {
  label: string;
  value: number;
  max: number;
  color?: string;
}

export default function HorizontalBar({ label, value, max, color = 'var(--px-teal)' }: Props) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '4px 0' }}>
      <div
        style={{
          width: '150px',
          fontFamily: 'var(--px-mono)',
          fontSize: '0.85rem',
          color: 'var(--px-muted-strong)',
          flexShrink: 0,
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {label}
      </div>
      <div
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={`${label} score`}
        style={{
          flex: 1,
          height: '6px',
          background: 'var(--px-teal-dim)',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            background: color,
            transition: 'width 0.4s var(--px-ease)',
          }}
        />
      </div>
      <div
        style={{
          width: '48px',
          fontFamily: 'var(--px-mono)',
          fontSize: '0.9rem',
          fontWeight: 700,
          color: 'var(--px-white)',
          textAlign: 'right',
          flexShrink: 0,
        }}
      >
        {value}
      </div>
    </div>
  );
}
