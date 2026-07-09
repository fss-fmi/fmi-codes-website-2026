import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';
import type { TeamMentor } from '@/types/team';

interface MentorPref {
  mentor_id: number;
  rank: number;
  mentor_name?: string;
}

/**
 * Active-team mentor state, in priority order:
 * confirmed assignments → submitted preferences → captain CTA / waiting note.
 */
export default function MentorsPanel({
  confirmed,
  mentors,
  prefs,
  isCaptain,
}: {
  confirmed: boolean | undefined;
  mentors: TeamMentor[];
  prefs: MentorPref[];
  isCaptain: boolean;
}) {
  if (confirmed && mentors.length > 0) {
    return (
      <Panel title="MENTORS">
        {mentors.map((m) => (
          <div
            key={m.mentor_id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 0',
              borderBottom: '1px solid var(--px-teal-dim)',
            }}
          >
            <img
              src={`/api/mentors/${m.mentor_id}/picture`}
              alt={m.mentor_name ?? 'Mentor'}
              loading="lazy"
              onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
              style={{
                width: 36,
                height: 36,
                objectFit: 'cover',
                border: '1px solid var(--px-teal-dim)',
              }}
            />
            <div>
              <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
                {m.mentor_name}
              </div>
              <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
                {m.company_name}
              </div>
            </div>
          </div>
        ))}
      </Panel>
    );
  }

  if (prefs.length > 0) {
    return (
      <Panel title="MENTORS">
        <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', marginBottom: 12 }}>
          &gt; Preferences submitted. Waiting for matching.
        </p>
        {prefs.map((p, i) => (
          <div
            key={p.mentor_id}
            style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0' }}
          >
            <span className="px-label" style={{ color: 'var(--px-teal)', minWidth: 30 }}>
              #{i + 1}
            </span>
            <span style={{ fontFamily: 'var(--px-mono)', color: 'var(--px-white)' }}>
              {p.mentor_name ?? `Mentor #${p.mentor_id}`}
            </span>
          </div>
        ))}
      </Panel>
    );
  }

  return (
    <Panel title="MENTORS">
      {isCaptain ? (
        <>
          <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', marginBottom: 16 }}>
            &gt; Your team is active. As captain, rank your preferred mentors so the matching
            algorithm can find the best fit.
          </p>
          <Button variant="primary" href="/chooseMentor">
            CHOOSE MENTORS
          </Button>
        </>
      ) : (
        <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
          &gt; Waiting for the captain to select mentor preferences.
        </p>
      )}
    </Panel>
  );
}
