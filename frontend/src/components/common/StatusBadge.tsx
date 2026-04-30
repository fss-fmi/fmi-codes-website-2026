type Variant =
  | 'active'
  | 'registered'
  | 'queued'
  | 'inactive'
  | 'captain'
  | 'member'
  | 'pending'
  | 'accepted'
  | 'declined';

const configs: Record<Variant, { bg: string; color: string; label?: string }> = {
  active: { bg: 'rgba(52,211,153,0.12)', color: '#34d399' },
  registered: { bg: 'rgba(96,165,250,0.12)', color: '#60a5fa' },
  queued: { bg: 'rgba(245,158,11,0.12)', color: '#f59e0b' },
  inactive: { bg: 'rgba(100,116,139,0.12)', color: '#64748b' },
  captain: { bg: 'rgba(251,191,36,0.15)', color: '#fbbf24', label: '★ Captain' },
  member: { bg: 'rgba(148,163,184,0.1)', color: '#94a3b8' },
  pending: { bg: 'rgba(245,158,11,0.12)', color: '#f59e0b' },
  accepted: { bg: 'rgba(52,211,153,0.12)', color: '#34d399' },
  declined: { bg: 'rgba(239,68,68,0.12)', color: '#ef4444' },
};

interface Props {
  variant: Variant;
  label?: string;
}

export default function StatusBadge({ variant, label }: Props) {
  const cfg = configs[variant];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '5px',
        padding: '3px 10px',
        borderRadius: '100px',
        fontSize: '0.72rem',
        fontWeight: 700,
        background: cfg.bg,
        color: cfg.color,
        letterSpacing: '0.04em',
      }}
    >
      {label ?? cfg.label ?? variant}
    </span>
  );
}
