import type { ReactNode } from 'react';

type Tone = 'warning' | 'success';

const TONE_COLOR: Record<Tone, string> = {
  warning: 'var(--px-amber)',
  success: 'var(--px-green)',
};

/**
 * The left-bordered info banner used on the team dashboard. Replaces three
 * copy-pasted colored boxes that differed only by tone and copy.
 */
export default function StatusBanner({ tone, children }: { tone: Tone; children: ReactNode }) {
  const color = TONE_COLOR[tone];
  return (
    <div
      style={{
        background: 'var(--px-bg-panel)',
        border: `1px solid ${color}`,
        borderLeft: `2px solid ${color}`,
        color,
        fontFamily: 'var(--px-mono)',
        fontSize: '0.85rem',
        padding: '10px 14px',
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  );
}
