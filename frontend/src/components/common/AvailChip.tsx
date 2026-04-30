interface Props {
  text: string;
}

function getColor(text: string) {
  const lower = text.toLowerCase();
  if (lower.includes('available') || lower.includes('yes'))
    return { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.3)', color: '#34d399' };
  if (lower.includes('limited') || lower.includes('maybe'))
    return { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)', color: '#f59e0b' };
  return { bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.25)', color: '#ef4444' };
}

export default function AvailChip({ text }: Props) {
  const c = getColor(text);
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '4px 10px',
        borderRadius: '100px',
        fontSize: '0.72rem',
        fontWeight: 600,
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.color,
      }}
    >
      <span
        style={{
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: c.color,
          flexShrink: 0,
        }}
      />
      {text}
    </span>
  );
}
