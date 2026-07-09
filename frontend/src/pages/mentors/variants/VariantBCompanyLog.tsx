import { useId, useState } from 'react';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import type { Mentor } from '@/types/mentor';
import MentorsHeader from './MentorsHeader';
import {
  availabilityStatus,
  capTechs,
  groupByCompany,
  mentorNumber,
  pictureFor,
  useMentors,
  type AvailabilityStatus,
} from './shared';

/**
 * `> COMPANY_LOG` — the mentors page layout.
 *
 * The sponsor floor plan. Mentors are grouped by company and rendered as
 * a series of Briefing-style chapters — company name on the left rail,
 * mentor portrait cards on the right. Turns the roster into an implicit
 * sponsor showcase and makes "who's from SAP?" a one-glance answer.
 *
 * Each mentor's tech stack starts collapsed at the top 5. Clicking the
 * `+N` control expands the row inline to reveal the rest.
 */
export default function VariantBCompanyLog() {
  const { data, isLoading, error } = useMentors();
  const mentors = data ?? [];
  const groups = groupByCompany(mentors);

  // Build a stable global M.NN number map so a mentor's number matches
  // their overall position in the API response, not their position within
  // their company chapter.
  const numberFor = new Map<number, string>();
  mentors.forEach((m, i) => numberFor.set(m.mentor_id, mentorNumber(i)));

  return (
    <main
      style={{
        background: 'var(--px-bg)',
        padding: 'clamp(48px, 8vw, 96px) 24px clamp(64px, 8vw, 96px)',
      }}
    >
      <div style={{ maxWidth: 1280, margin: '0 auto' }}>
        <MentorsHeader
          title="COMPANY_LOG // FMI CODES 2026"
          caption={`${mentors.length || 20} engineers across ${groups.length || 12} companies. Grouped by shop.`}
        />

        {isLoading && (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
            <LoadingSpinner />
          </div>
        )}
        {error && (
          <p className="px-body" style={{ color: 'var(--px-danger)' }}>
            &gt; ERROR: Failed to load mentors.
          </p>
        )}

        {groups.map((g, gi) => (
          <CompanyChapter
            key={g.company}
            company={g.company}
            mentors={g.mentors}
            chapterIndex={gi}
            numberFor={numberFor}
          />
        ))}
      </div>
    </main>
  );
}

function CompanyChapter({
  company,
  mentors,
  chapterIndex,
  numberFor,
}: {
  company: string;
  mentors: Mentor[];
  chapterIndex: number;
  numberFor: Map<number, string>;
}) {
  return (
    <section
      className="companylog-chapter"
      style={{
        padding: 'clamp(40px, 5vw, 64px) 0',
        borderBottom: '1px solid var(--px-teal-dim)',
      }}
    >
      {/* Left rail — company name + mentor-count tally */}
      <div
        className="companylog-chapter__rail"
      >
        <div
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '0.5rem',
            letterSpacing: '0.18em',
            color: 'var(--px-salmon)',
            textTransform: 'uppercase',
          }}
          aria-hidden="true"
        >
          CH.{String(chapterIndex + 1).padStart(2, '0')}
        </div>
        <h2
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: 'clamp(1rem, 2.2vw, 1.5rem)',
            lineHeight: 1.2,
            letterSpacing: '0.02em',
            color: 'var(--px-white)',
            textTransform: 'uppercase',
            margin: 0,
            textWrap: 'balance',
          }}
        >
          {company}
        </h2>
        <div
          aria-label={`${mentors.length} ${mentors.length === 1 ? 'mentor' : 'mentors'} from ${company}`}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontFamily: 'var(--px-font)',
            fontSize: '0.5rem',
            letterSpacing: '0.14em',
            color: 'var(--px-muted-strong)',
            textTransform: 'uppercase',
          }}
        >
          <span style={{ display: 'flex', gap: '4px' }} aria-hidden="true">
            {Array.from({ length: mentors.length }).map((_, i) => (
              <span
                key={i}
                style={{
                  width: 10,
                  height: 10,
                  background: 'var(--px-teal)',
                }}
              />
            ))}
          </span>
          <span>
            {mentors.length} {mentors.length === 1 ? 'MENTOR' : 'MENTORS'}
          </span>
        </div>
      </div>

      {/* Right column — mentor cards laid out as a responsive row */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 'clamp(16px, 2vw, 24px)',
        }}
      >
        {mentors.map((m) => (
          <MentorCard
            key={m.mentor_id}
            mentor={m}
            number={numberFor.get(m.mentor_id) ?? '00'}
          />
        ))}
      </div>
    </section>
  );
}

function MentorCard({ mentor, number }: { mentor: Mentor; number: string }) {
  const src = pictureFor(mentor);
  const status = availabilityStatus(mentor.availability_text);
  const bio = mentor.bio?.split('\n')[0];
  const allTechs = Array.isArray(mentor.technologies)
    ? mentor.technologies.filter(Boolean)
    : [];
  const { shown, more } = capTechs(allTechs, 5);
  const [techsOpen, setTechsOpen] = useState(false);
  const techsRegionId = useId();

  const visibleTechs = techsOpen ? allTechs : shown;

  return (
    <article
      style={{
        background: 'var(--px-bg-panel)',
        border: '1px solid var(--px-teal-dim)',
        display: 'flex',
        flexDirection: 'column',
        gap: 0,
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '96px 1fr',
          gap: '16px',
          padding: '16px',
        }}
      >
        <div
          style={{
            width: 96,
            aspectRatio: '1',
            border: '2px solid var(--px-teal-border)',
            overflow: 'hidden',
            position: 'relative',
            background: 'var(--px-bg-elevated)',
          }}
        >
          {src ? (
            <img
              src={src}
              alt=""
              loading="lazy"
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
                display: 'grid',
                placeItems: 'center',
                fontFamily: 'var(--px-font)',
                fontSize: '1.4rem',
                color: 'var(--px-teal)',
              }}
              aria-hidden="true"
            >
              {mentor.name[0]?.toUpperCase() ?? '?'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
          <div
            aria-hidden="true"
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: '0.5rem',
              letterSpacing: '0.14em',
              color: 'var(--px-teal)',
              textTransform: 'uppercase',
            }}
          >
            M.{number}
          </div>
          <div
            style={{
              fontFamily: 'var(--px-mono)',
              fontSize: '0.9rem',
              lineHeight: 1.35,
              color: 'var(--px-white)',
              fontWeight: 500,
            }}
          >
            {mentor.name}
          </div>
          {bio && (
            <div
              style={{
                fontFamily: 'var(--px-mono)',
                fontSize: '0.75rem',
                lineHeight: 1.5,
                color: 'var(--px-muted-strong)',
              }}
            >
              {bio}
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '10px',
          padding: '12px 16px',
          borderTop: '1px solid var(--px-teal-dim)',
        }}
      >
        <AvailabilityInline status={status} text={mentor.availability_text} />
      </div>

      {allTechs.length > 0 && (
        <div
          id={techsRegionId}
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px',
            padding: '12px 16px 16px',
            borderTop: '1px solid var(--px-teal-dim)',
          }}
        >
          {visibleTechs.map((t) => (
            <span
              key={t}
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '0.5rem',
                letterSpacing: '0.08em',
                color: 'var(--px-teal)',
                background: 'var(--px-bg-elevated)',
                padding: '5px 10px',
                textTransform: 'uppercase',
              }}
            >
              {t}
            </span>
          ))}
          {more > 0 && (
            <button
              type="button"
              className="companylog-techs-toggle"
              aria-expanded={techsOpen}
              aria-controls={techsRegionId}
              onClick={() => setTechsOpen((v) => !v)}
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '0.5rem',
                letterSpacing: '0.08em',
                color: techsOpen ? 'var(--px-salmon)' : 'var(--px-muted-strong)',
                background: 'transparent',
                border: `1px solid ${
                  techsOpen ? 'var(--px-salmon)' : 'var(--px-teal-dim)'
                }`,
                padding: '4px 10px',
                textTransform: 'uppercase',
                cursor: 'pointer',
                transition:
                  'color 140ms var(--px-ease), border-color 140ms var(--px-ease)',
              }}
            >
              {techsOpen ? '— HIDE' : `+${more} MORE`}
            </button>
          )}
        </div>
      )}
    </article>
  );
}

function AvailabilityInline({
  status,
  text,
}: {
  status: AvailabilityStatus;
  text?: string;
}) {
  const map: Record<AvailabilityStatus, string> = {
    full: 'var(--px-green)',
    partial: 'var(--px-amber)',
    limited: 'var(--px-salmon)',
    unknown: 'var(--px-muted)',
  };
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        fontFamily: 'var(--px-mono)',
        fontSize: '0.75rem',
        color: 'var(--px-muted-strong)',
      }}
    >
      <span
        aria-hidden="true"
        style={{
          width: 8,
          height: 8,
          background: map[status],
          flexShrink: 0,
        }}
      />
      {text ?? 'TBD'}
    </div>
  );
}
