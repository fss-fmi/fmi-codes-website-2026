type Variant =
  | 'active'
  | 'registered'
  | 'queued'
  | 'inactive'
  | 'captain'
  | 'member'
  | 'pending'
  | 'accepted'
  | 'declined'
  | 'invalidated'
  | 'cancelled';

const configs: Record<Variant, { color: string; label?: string }> = {
  active: { color: 'var(--px-green)', label: 'ACTIVE' },
  registered: { color: 'var(--px-teal)', label: 'REGISTERED' },
  queued: { color: 'var(--px-amber)', label: 'QUEUED' },
  inactive: { color: 'var(--px-muted-strong)', label: 'INACTIVE' },
  captain: { color: 'var(--px-amber)', label: 'CAPTAIN' },
  member: { color: 'var(--px-muted-strong)', label: 'MEMBER' },
  pending: { color: 'var(--px-amber)', label: 'PENDING' },
  accepted: { color: 'var(--px-green)', label: 'ACCEPTED' },
  declined: { color: 'var(--px-danger)', label: 'DECLINED' },
  invalidated: { color: 'var(--px-muted-strong)', label: 'INVALIDATED' },
  cancelled: { color: 'var(--px-muted-strong)', label: 'CANCELLED' },
};

interface Props {
  variant: Variant;
  label?: string;
}

export default function StatusBadge({ variant, label }: Props) {
  const cfg = configs[variant] ?? configs['inactive'];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 10px',
        borderRadius: '999px',
        background: 'var(--px-bg-elevated)',
        color: cfg.color,
        fontFamily: 'var(--px-font)',
        fontSize: '0.55rem',
        letterSpacing: '0.08em',
        textTransform: 'uppercase',
      }}
    >
      {label ?? cfg.label ?? String(variant).toUpperCase()}
    </span>
  );
}
