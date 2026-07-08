import type { Mentor } from '@/types/mentor';

interface Props {
  mentor: Mentor;
}

function AvailDot({ text }: { text: string }) {
  const t = text.toLowerCase();
  let color = 'rgba(176,190,197,0.7)';
  if (t.includes('free') || t.includes('available') || t.includes('свободен')) {
    color = '#4ade80';
  } else if (t.includes('partial') || t.includes('частично')) {
    color = 'var(--px-salmon)';
  } else if (t.includes('full') || t.includes('taken') || t.includes('зает')) {
    color = '#f87171';
  }
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontFamily: 'var(--px-font)',
        fontSize: '0.38rem',
        color: 'var(--px-muted)',
        textTransform: 'uppercase' as const,
        letterSpacing: '0.08em',
      }}
    >
      <span
        style={{
          width: '8px',
          height: '8px',
          background: color,
          flexShrink: 0,
        }}
      />
      {text}
    </div>
  );
}

export default function MentorCard({ mentor }: Props) {
  const techs = Array.isArray(mentor.technologies) ? mentor.technologies.filter(Boolean) : [];

  return (
    <div
      className="px-card"
      style={{ padding: '0', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
    >
      {/* Photo */}
      <div
        style={{
          width: '100%',
          aspectRatio: '1',
          overflow: 'hidden',
          borderBottom: '2px solid var(--px-teal-border)',
          background: 'var(--px-bg)',
          flexShrink: 0,
          position: 'relative',
        }}
      >
        {mentor.picture_filename ? (
          <img
            src={
              mentor.picture_url?.startsWith('/')
                ? mentor.picture_url
                : `/static/mentorPictures/${mentor.picture_filename}`
            }
            alt={mentor.name}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              display: 'block',
            }}
          />
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              background: 'var(--px-bg-panel)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--px-font)',
              fontSize: '2rem',
              color: 'var(--px-teal)',
            }}
          >
            {mentor.name[0]?.toUpperCase() ?? '?'}
          </div>
        )}
      </div>

      {/* Info */}
      <div
        style={{
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          flex: 1,
        }}
      >
        <h3
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '0.5rem',
            color: 'var(--px-white)',
            lineHeight: 1.5,
            margin: 0,
          }}
        >
          {mentor.name}
        </h3>

        {mentor.company_name && (
          <div
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.75rem',
              color: 'var(--px-teal)',
            }}
          >
            {mentor.company_name}
          </div>
        )}

        {mentor.availability_text && <AvailDot text={mentor.availability_text} />}

        {mentor.bio && (
          <p
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.75rem',
              color: 'var(--px-muted)',
              lineHeight: 1.7,
              flexGrow: 1,
              margin: 0,
            }}
          >
            {mentor.bio}
          </p>
        )}

        {techs.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: 'auto' }}>
            {techs.map((tech) => (
              <span
                key={tech}
                className="px-chip"
              >
                {tech}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
