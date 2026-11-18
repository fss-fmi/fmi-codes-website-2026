import type { ReactNode } from 'react';

type AlertKind = 'error' | 'success' | 'info';

// `info` has no role of its own: it goes inside a live region that is always mounted
// (RetryNotice), since screen readers often skip a region inserted with its text in it.
const STYLES: Record<AlertKind, { role?: 'alert' | 'status'; color: string }> = {
  error: { role: 'alert', color: 'var(--px-danger)' },
  success: { role: 'status', color: 'var(--px-green)' },
  info: { color: 'var(--px-teal)' },
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
