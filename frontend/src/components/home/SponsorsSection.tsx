import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { PREMIUM_SPONSORS, SUPPORTING_SPONSORS } from './homeData';

/**
 * SponsorsSection — matches Briefing's editorial rhythm.
 *
 * No outer panel wrap. Header row (title left, caption right, rule below).
 * Full-bleed marquee escapes the section maxWidth so logos scroll edge-to-edge
 * — the Neo Mirai full-bleed strip move, in arcade form. Below the marquee,
 * a numbered credits ladder that names the premium partners in prose (the
 * "cast list" pattern), then supporting sponsors as an inline monospace roll.
 */

const PREMIUM = PREMIUM_SPONSORS;
const SUPPORTING = SUPPORTING_SPONSORS;

// Some logos have proportions that need visual balancing at the small tile size
const SCALE_OVERRIDES: Record<string, number> = {
  Milestone: 1.5,
  Astea: 1.2,
  Dreamix: 1.4,
  'Engineer Access': 1.15,
  Raven: 1.25,
  Experian: 1.2,
  Waracle: 1.2,
};

const CAROUSEL_SOURCE = [...PREMIUM, ...SUPPORTING];
const TRACK = [...CAROUSEL_SOURCE, ...CAROUSEL_SOURCE];

function useMarquee(trackRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    if (
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ) {
      return;
    }
    let pos = 0;
    let rafId: number;
    const speed = 0.4;
    const halfW = el.scrollWidth / 2;

    const step = () => {
      pos += speed;
      if (pos >= halfW) pos = 0;
      el.style.transform = `translateX(-${pos}px)`;
      rafId = requestAnimationFrame(step);
    };
    rafId = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafId);
  }, [trackRef]);
}

function SponsorTile({
  file,
  alt,
  premium,
}: {
  file: string;
  alt: string;
  premium: boolean;
}) {
  const scale = SCALE_OVERRIDES[alt];
  return (
    <Link
      to="/partners"
      aria-label={alt}
      style={{
        position: 'relative',
        width: 'clamp(88px, calc(100vw / 11), 140px)',
        flexShrink: 0,
        margin: '0 10px',
        padding: '12px',
        border: premium
          ? '2px solid var(--px-teal-border)'
          : '1px solid var(--px-teal-dim)',
        background: 'var(--px-bg-panel)',
        display: 'grid',
        placeItems: 'center',
        aspectRatio: '1/1',
        textDecoration: 'none',
        outline: 'none',
        transition: 'border-color 180ms var(--px-ease), background 180ms var(--px-ease)',
      }}
      onFocus={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.boxShadow =
          'var(--px-focus-glow)';
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.boxShadow = 'none';
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background =
          'var(--px-bg-elevated)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.background =
          'var(--px-bg-panel)';
      }}
    >
      <img
        src={`/companyLogos/${file}`}
        alt={alt}
        loading="lazy"
        style={{
          width: '80%',
          height: '80%',
          objectFit: 'contain',
          filter: 'brightness(0.95) contrast(1.05)',
          ...(scale ? { transform: `scale(${scale})` } : {}),
        }}
      />
    </Link>
  );
}

export default function SponsorsSection() {
  const trackRef = useRef<HTMLDivElement>(null);
  useMarquee(trackRef);

  return (
    <section
      aria-labelledby="sponsors-heading"
      style={{
        background: 'var(--px-bg)',
        paddingTop: 'clamp(72px, 10vw, 120px)',
        paddingBottom: 'clamp(72px, 10vw, 120px)',
      }}
    >
      {/* Constrained header, mirroring BriefingSection */}
      <div
        style={{
          maxWidth: 1180,
          margin: '0 auto',
          padding: '0 24px',
        }}
      >
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
          <h2
            id="sponsors-heading"
            className="px-prompt-heading"
            style={{
              margin: 0,
              fontSize: 'clamp(0.85rem, 1.8vw, 1.15rem)',
              color: 'var(--px-white)',
            }}
          >
            SPONSORS // WHO&apos;S BACKING THIS
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
            Twelve companies. Real prizes. Real mentors on the floor.
          </p>
        </div>
      </div>

      {/* Full-bleed marquee — breaks out of the section maxWidth */}
      <div
        style={{
          position: 'relative',
          width: '100%',
          overflow: 'hidden',
        }}
      >
        {/* Edge fades so tiles vanish into the bg rather than clip hard */}
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            bottom: 0,
            width: 'clamp(60px, 8vw, 120px)',
            zIndex: 2,
            background:
              'linear-gradient(to right, var(--px-bg), transparent)',
            pointerEvents: 'none',
          }}
        />
        <div
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: 'clamp(60px, 8vw, 120px)',
            zIndex: 2,
            background: 'linear-gradient(to left, var(--px-bg), transparent)',
            pointerEvents: 'none',
          }}
        />
        <div
          ref={trackRef}
          className="sponsor-track"
          style={{
            display: 'flex',
            flexWrap: 'nowrap',
            alignItems: 'center',
            padding: '8px 0',
            willChange: 'transform',
          }}
        >
          {TRACK.map((s, i) => (
            <SponsorTile
              key={i}
              file={s.file}
              alt={s.alt}
              premium={PREMIUM.some((p) => p.alt === s.alt)}
            />
          ))}
        </div>
      </div>

      {/* Prose credits row — the "cast list" that named-checks the partners
          instead of forcing readers to squint at cycling logos */}
      <div
        style={{
          maxWidth: 1180,
          margin: '0 auto',
          padding: '0 24px',
          marginTop: 'clamp(48px, 6vw, 72px)',
        }}
        className="sponsors-credits"
      >
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
            12+
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
            PARTNERS
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
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
            The tournament rides on companies who put up real prize money, send
            engineers to mentor on the floor for the full 48h, and turn up on
            Sunday for the ceremony. Headliners:{' '}
            {PREMIUM.map((p, i) => (
              <span key={p.alt}>
                <span className="briefing-emph">{p.alt}</span>
                {i < PREMIUM.length - 1 ? ', ' : '.'}
              </span>
            ))}{' '}
            Supporting:{' '}
            <span
              style={{
                fontFamily: 'var(--px-mono)',
                color: 'var(--px-muted)',
                letterSpacing: '0.02em',
              }}
            >
              {SUPPORTING.map((s) => s.alt).join(' · ')}.
            </span>
          </p>
          <div>
            <Link
              to="/partners"
              className="sponsors-link"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '10px',
                fontFamily: 'var(--px-font)',
                fontSize: '0.6rem',
                letterSpacing: '0.14em',
                color: 'var(--px-teal)',
                textDecoration: 'none',
                padding: '10px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                textTransform: 'uppercase',
                transition: 'color 180ms var(--px-ease), border-color 180ms var(--px-ease)',
              }}
            >
              VIEW ALL PARTNERS
              <span aria-hidden="true">→</span>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
