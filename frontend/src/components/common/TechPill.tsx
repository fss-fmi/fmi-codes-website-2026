// Round-robin color palette matching the original Jinja template
const TECH_COLORS = [
  { bg: 'rgba(96,165,250,0.12)', border: 'rgba(96,165,250,0.25)', text: '#60a5fa' },
  { bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.25)', text: '#a78bfa' },
  { bg: 'rgba(34,211,238,0.12)', border: 'rgba(34,211,238,0.25)', text: '#22d3ee' },
  { bg: 'rgba(52,211,153,0.12)', border: 'rgba(52,211,153,0.25)', text: '#34d399' },
  { bg: 'rgba(244,114,182,0.12)', border: 'rgba(244,114,182,0.25)', text: '#f472b6' },
  { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.25)', text: '#f59e0b' },
];

interface Props {
  tech: string;
  index?: number;
}

export default function TechPill({ tech, index = 0 }: Props) {
  const c = TECH_COLORS[index % TECH_COLORS.length];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: '100px',
        fontSize: '0.7rem',
        fontWeight: 600,
        background: c.bg,
        border: `1px solid ${c.border}`,
        color: c.text,
        letterSpacing: '0.03em',
      }}
    >
      {tech}
    </span>
  );
}
