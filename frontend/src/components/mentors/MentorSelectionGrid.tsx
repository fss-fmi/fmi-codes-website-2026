import MentorCard from './MentorCard';
import type { Mentor } from '@/types/mentor';

interface Props {
  mentors: Mentor[];
  isLoading?: boolean;
}

function Skeleton() {
  return (
    <div
      className="px-card"
      style={{ overflow: 'hidden' }}
    >
      <div
        style={{
          width: '100%',
          aspectRatio: '1',
          background: 'var(--px-teal-dim)',
          borderBottom: '2px solid var(--px-teal-border)',
          animation: 'pixelBlink 1.2s step-start infinite',
        }}
      />
      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
        <div style={{ height: '10px', background: 'var(--px-teal-dim)', width: '65%' }} />
        <div style={{ height: '8px', background: 'var(--px-teal-dim)', width: '45%' }} />
        <div style={{ height: '8px', background: 'var(--px-teal-dim)', width: '80%' }} />
      </div>
    </div>
  );
}

export default function MentorSelectionGrid({ mentors, isLoading = false }: Props) {
  if (isLoading) {
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: '20px',
        }}
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }

  if (!mentors.length) {
    return (
      <div
        style={{
          textAlign: 'center',
          padding: '60px 24px',
          fontFamily: 'var(--px-font)',
          fontSize: '0.55rem',
          color: 'var(--px-muted)',
          lineHeight: 2,
        }}
      >
        &gt; NO MENTORS FOUND
      </div>
    );
  }

  return (
    <>
      <div style={{ marginBottom: '40px' }}>
        <h2
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: 'clamp(0.7rem, 2vw, 1rem)',
            color: 'var(--px-teal)',
            margin: 0,
          }}
        >
          &gt; MENTORS
        </h2>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
          gap: '20px',
        }}
      >
        {mentors.map((mentor) => (
          <MentorCard
            key={mentor.mentor_id}
            mentor={mentor}
          />
        ))}
      </div>
    </>
  );
}
