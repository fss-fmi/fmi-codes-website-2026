import type { ReactNode } from 'react';

type AlertKind = 'error' | 'success';

const STYLES: Record<AlertKind, { role: 'alert' | 'status'; color: string }> = {
  error: { role: 'alert', color: 'var(--px-danger)' },
  success: { role: 'status', color: 'var(--px-green)' },
};

/**
 * Inline form feedback banner shared across the auth pages. Consolidates the
 * previously copy-pasted role="alert"/role="status" boxes so styling and
 * accessibility semantics live in one place.
 */
export default function FormAlert({
  kind,
  children,
  style,
}: {
  kind: AlertKind;
  children: ReactNode;
  style?: React.CSSProperties;
}) {
  const { role, color } = STYLES[kind];
  return (
    <div
      role={role}
      style={{
        background: 'var(--px-bg-panel)',
        border: `1px solid ${color}`,
        borderLeft: `2px solid ${color}`,
        color,
        fontFamily: 'var(--px-mono)',
        fontSize: '0.85rem',
        padding: '12px 14px',
        marginBottom: '20px',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
