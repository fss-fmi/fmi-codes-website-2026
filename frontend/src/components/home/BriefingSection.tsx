import { useScrollReveal } from '@/hooks/useVisuals';

/**
 * Variant 1 — `> BRIEFING`
 *
 * The mission-dossier. A vertical numbered log where each entry is a real
 * editorial paragraph, not a tile. Numbers earn their place because the
 * three entries form a real sequence — WHEN / WHERE / WHO. Data points
 * survive as inline emphasis inside prose, not as centered tile values.
 * Thin teal-dim horizontal rules separate entries; no card containers.
 */
export default function BriefingSection() {
  useScrollReveal('.briefing-row');

  return (
    <section
      style={{
        padding: 'clamp(72px, 10vw, 120px) 24px',
        maxWidth: 1180,
        margin: '0 auto',
        background: 'var(--px-bg)',
      }}
      aria-labelledby="briefing-heading"
    >
      {/* Header row: title + subhead */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: '16px',
          marginBottom: 'clamp(48px, 6vw, 72px)',
          paddingBottom: '24px',
          borderBottom: '1px solid var(--px-teal-dim)',
        }}
      >
        <h2
          id="briefing-heading"
          className="px-prompt-heading"
          style={{
            margin: 0,
            fontSize: 'clamp(0.85rem, 1.8vw, 1.15rem)',
            color: 'var(--px-white)',
          }}
        >
          BRIEFING // FMI CODES 2026
        </h2>
        <p
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.8rem',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: 'var(--px-muted-strong)',
            margin: 0,
            maxWidth: '38ch',
            textAlign: 'right',
          }}
        >
          A 48-hour quest. Three acts. Watch the clock.
        </p>
      </div>

      {/* Numbered entries */}
      <BriefingRow
        num="01"
        eyebrow="WHEN"
        headline="March 2026 · 48 hours on the clock"
        body={
          <>
            The gate opens on Friday afternoon and closes Sunday afternoon —{' '}
            <span className="briefing-emph">
              48 straight hours
            </span>{' '}
            of coding, sleeping under the desks, and shipping in front of a live
            leaderboard. Registration closes weeks before the doors open, so if
            you're reading this and it's still open,{' '}
            <span className="briefing-emph">this is your window</span>.
          </>
        }
      />
      <BriefingRow
        num="02"
        eyebrow="WHERE"
        headline="Sofia University, FMI"
        body={
          <>
            The building on{' '}
            <span className="briefing-emph">James Bourchier</span> becomes the
            arena — lecture halls turned into team pods, corridors turned into
            the mentor circuit, one hall reserved for the live rankings
            projector. This is a physical event: you show up, you sit next to
            your team, you build.
          </>
        }
      />
      <BriefingRow
        num="03"
        eyebrow="WHO"
        headline="Up to 18 teams · ~90 coders · 20 mentors"
        body={
          <>
            Teams of{' '}
            <span className="briefing-emph">3 to 5</span> — students from FMI, and any friends who code —
            square off against each other for real prizes from{' '}
            <span className="briefing-emph">12+ industry sponsors</span>.
            Mentors from Avenga, Gameloft, EnduroSat, SAP and the rest are on
            the floor for the whole 48h. Bring your own laptop, your own
            caffeine, and one idea that matters.
          </>
        }
      />
    </section>
  );
}

function BriefingRow({
  num,
  eyebrow,
  headline,
  body,
}: {
  num: string;
  eyebrow: string;
  headline: string;
  body: React.ReactNode;
}) {
  return (
    <>
      <article
        className="briefing-row reveal"
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(120px, 200px) 1fr',
          gap: 'clamp(24px, 4vw, 72px)',
          padding: 'clamp(32px, 5vw, 56px) 0',
          alignItems: 'start',
        }}
      >
        {/* Left rail: big number + eyebrow */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: 'clamp(2rem, 4.5vw, 3.4rem)',
              color: 'var(--px-teal)',
              lineHeight: 1,
              letterSpacing: '0.02em',
            }}
            aria-hidden="true"
          >
            {num}
          </div>
          <div
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: '0.55rem',
              letterSpacing: '0.14em',
              color: 'var(--px-salmon)',
              textTransform: 'uppercase',
            }}
          >
            {eyebrow}
          </div>
        </div>

        {/* Right column: headline + body */}
        <div>
          <h3
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: 'clamp(0.85rem, 1.8vw, 1.2rem)',
              color: 'var(--px-white)',
              lineHeight: 1.45,
              letterSpacing: '0.02em',
              margin: 0,
              marginBottom: '20px',
              textWrap: 'balance',
            }}
          >
            {headline}
          </h3>
          <p
            style={{
              fontFamily: 'var(--px-mono)',
              fontSize: 'clamp(0.95rem, 1.4vw, 1.05rem)',
              lineHeight: 1.75,
              color: 'var(--px-muted-strong)',
              margin: 0,
              maxWidth: '62ch',
              textWrap: 'pretty',
            }}
          >
            {body}
          </p>
        </div>
      </article>
      <div
        role="presentation"
        style={{
          height: '1px',
          background: 'var(--px-teal-dim)',
        }}
      />
    </>
  );
}
