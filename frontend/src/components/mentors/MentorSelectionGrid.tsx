import MentorCard from './MentorCard';
import type { Mentor } from '@/types/mentor';

interface Props {
  mentors: Mentor[];
  isLoading?: boolean;
}

function Skeleton() {
  return (
    <div
      className="glass-card"
      style={{ padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        <div
          style={{
            width: '60px',
            height: '60px',
            borderRadius: '50%',
            background: 'rgba(255,255,255,0.06)',
          }}
        />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <div
            style={{
              height: '14px',
              borderRadius: '6px',
              background: 'rgba(255,255,255,0.06)',
              width: '60%',
            }}
          />
          <div
            style={{
              height: '12px',
              borderRadius: '6px',
              background: 'rgba(255,255,255,0.04)',
              width: '40%',
            }}
          />
        </div>
      </div>
      <div
        style={{
          height: '12px',
          borderRadius: '6px',
          background: 'rgba(255,255,255,0.04)',
          width: '100%',
        }}
      />
      <div
        style={{
          height: '12px',
          borderRadius: '6px',
          background: 'rgba(255,255,255,0.04)',
          width: '80%',
        }}
      />
    </div>
  );
}

export default function MentorSelectionGrid({ mentors, isLoading = false }: Props) {
  if (isLoading) {
    return (
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
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
      <div style={{ textAlign: 'center', padding: '60px 24px', color: 'var(--muted)' }}>
        No mentors found.
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
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
  );
}
