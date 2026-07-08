import type { ReactNode } from 'react';

/**
 * Header row shared by all Mentors variants. Same shape as
 * BriefingSection / RegulationsHeader — title left, sub-caption right,
 * single teal-dim rule underneath.
 */
export default function MentorsHeader({
  title,
  caption,
  right,
}: {
  title: string;
  caption: string;
  right?: ReactNode;
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        gap: '16px',
        marginBottom: 'clamp(40px, 5vw, 64px)',
        paddingBottom: '24px',
        borderBottom: '1px solid var(--px-teal-dim)',
      }}
    >
      <h1
        className="px-prompt-heading"
        style={{
          margin: 0,
          fontSize: 'clamp(0.85rem, 1.8vw, 1.15rem)',
          color: 'var(--px-white)',
        }}
      >
        {title}
      </h1>
      {right ?? (
        <p
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.8rem',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: 'var(--px-muted-strong)',
            margin: 0,
            maxWidth: '46ch',
            textAlign: 'right',
          }}
        >
          {caption}
        </p>
      )}
    </div>
  );
}
