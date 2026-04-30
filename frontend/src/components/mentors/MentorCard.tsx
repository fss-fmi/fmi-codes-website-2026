import TechPill from '@/components/common/TechPill';
import AvailChip from '@/components/common/AvailChip';
import type { Mentor } from '@/types/mentor';

interface Props {
  mentor: Mentor;
}

export default function MentorCard({ mentor }: Props) {
  const techs = mentor.technologies
    ? mentor.technologies
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  return (
    <div
      className="glass-card"
      style={{ padding: '28px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
        {mentor.picture_filename ? (
          <img
            src={`/mentorPictures/${mentor.picture_filename}`}
            alt={mentor.name}
            style={{
              width: '60px',
              height: '60px',
              borderRadius: '50%',
              objectFit: 'cover',
              flexShrink: 0,
              border: '2px solid rgba(96,165,250,0.25)',
            }}
          />
        ) : (
          <div
            style={{
              width: '60px',
              height: '60px',
              borderRadius: '50%',
              flexShrink: 0,
              background: 'linear-gradient(135deg, #6366f1, #60a5fa)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: '1.2rem',
              fontWeight: 700,
              color: '#fff',
            }}
          >
            {mentor.name[0]?.toUpperCase() ?? '?'}
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <h3
            style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text)', marginBottom: '2px' }}
          >
            {mentor.name}
          </h3>
          <div style={{ fontSize: '0.8rem', color: 'var(--accent)', fontWeight: 500 }}>
            {mentor.company_name}
          </div>
        </div>
      </div>

      {/* Availability */}
      {mentor.availability_text && <AvailChip text={mentor.availability_text} />}

      {/* Bio */}
      {mentor.bio && (
        <p style={{ fontSize: '0.85rem', color: 'var(--muted)', lineHeight: 1.7, flexGrow: 1 }}>
          {mentor.bio}
        </p>
      )}

      {/* Technologies */}
      {techs.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {techs.map((tech, i) => (
            <TechPill
              key={tech}
              tech={tech}
              index={i}
            />
          ))}
        </div>
      )}
    </div>
  );
}
