import { useEffect, useRef } from 'react';

const SPONSORS = [
  { file: 'avenga.svg', alt: 'Avenga', premium: true },
  { file: 'gameloft.png', alt: 'Gameloft', premium: true },
  { file: 'EnduroSat.png', alt: 'EnduroSat', premium: true },
  { file: 'waracle.png', alt: 'Waracle', premium: true },
  { file: 'SAP.png', alt: 'SAP', premium: true },
  { file: 'Milestone.png', alt: 'Milestone', premium: true },
  { file: 'astea.svg', alt: 'Astea', premium: false },
  { file: 'chaos.jpg', alt: 'Chaos', premium: false },
  { file: 'Dreamix.png', alt: 'Dreamix', premium: false },
  { file: 'engineerAcces.png', alt: 'Engineer Access', premium: false },
  { file: 'raven.svg', alt: 'Raven', premium: false },
  { file: 'Experian.jpg', alt: 'Experian', premium: false },
];

const SCALE_OVERRIDES: Record<string, number> = {
  Milestone: 1.5,
  Astea: 1.2,
  Dreamix: 1.4,
  'Engineer Access': 1.15,
  Raven: 1.25,
  Experian: 1.2,
  Waracle: 1.2,
};

// Duplicate for infinite scroll
const TRACK = [...SPONSORS, ...SPONSORS];

function useCarousel(trackRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
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

function SponsorLogo({ file, alt, premium }: { file: string; alt: string; premium: boolean }) {
  const scale = SCALE_OVERRIDES[alt];
  return (
    <div
      style={{
        position: 'relative',
        width: 'clamp(70px, calc(100vw / 12), 120px)',
        flexShrink: 0,
        borderRadius: '16px',
        margin: '8px',
        padding: '6px',
        border: `1px solid ${premium ? 'rgba(235,184,112,0.2)' : 'rgba(255,255,255,0.06)'}`,
        background: premium ? 'rgba(174,129,81,0.05)' : 'rgba(255,255,255,0.02)',
        display: 'grid',
        placeItems: 'center',
        aspectRatio: '1/1',
        transition:
          'transform 0.3s cubic-bezier(0.22,1,0.36,1), box-shadow 0.3s, border-color 0.3s',
        overflow: 'hidden',
      }}
    >
      <img
        src={`/companyLogos/${file}`}
        alt={alt}
        style={{
          width: '78%',
          height: '78%',
          objectFit: 'contain',
          ...(scale ? { transform: `scale(${scale})` } : {}),
        }}
      />
    </div>
  );
}

export default function SponsorsSection() {
  const trackRef = useRef<HTMLDivElement>(null);
  useCarousel(trackRef);

  return (
    <section style={{ padding: '60px 24px 80px', position: 'relative' }}>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: '10%',
          right: '10%',
          height: '1px',
          background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.15), transparent)',
        }}
      />

      {/* Header */}
      <div
        className="reveal"
        style={{ textAlign: 'center', marginBottom: '48px' }}
      >
        <div
          style={{
            display: 'inline-block',
            fontSize: '0.62rem',
            textTransform: 'uppercase',
            letterSpacing: '0.18em',
            color: 'var(--torch-gold)',
            fontFamily: 'var(--font-heading)',
            fontWeight: 700,
            marginBottom: '12px',
            padding: '4px 16px',
            borderRadius: '100px',
            background: 'rgba(212,168,67,0.07)',
            border: '1px solid rgba(212,168,67,0.2)',
          }}
        >
          ⚜️ Patrons of the Realm
        </div>
        <h2
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: 'clamp(1.6rem, 3vw, 2.2rem)',
            fontWeight: 700,
            color: 'var(--parchment)',
            marginBottom: '12px',
            lineHeight: 1.2,
          }}
        >
          Backed by Industry Leaders
        </h2>
        <p
          style={{
            fontSize: '0.95rem',
            color: 'var(--parchment-dim)',
            maxWidth: '500px',
            margin: '0 auto 18px',
            lineHeight: 1.7,
          }}
        >
          The companies shaping tomorrow’s tech — supporting the next generation of builders.
        </p>
        <a
          href="/partners"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '0.82rem',
            fontFamily: 'var(--font-heading)',
            fontWeight: 600,
            color: 'var(--torch-gold)',
            textDecoration: 'none',
            letterSpacing: '0.06em',
            opacity: 0.8,
            transition: 'opacity 0.2s',
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLAnchorElement).style.opacity = '1')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLAnchorElement).style.opacity = '0.8')}
        >
          View All Partners
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M5 12h14" />
            <path d="m12 5 7 7-7 7" />
          </svg>
        </a>
      </div>

      {/* Carousel */}
      <div
        className="reveal"
        style={{ overflow: 'hidden', position: 'relative', width: '100%' }}
      >
        {/* fade edges */}
        <div
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            bottom: 0,
            width: '200px',
            zIndex: 2,
            background: 'linear-gradient(to right, var(--bg), transparent)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: '200px',
            zIndex: 2,
            background: 'linear-gradient(to left, var(--bg), transparent)',
            pointerEvents: 'none',
          }}
        />
        <div
          ref={trackRef}
          style={{ display: 'flex', flexWrap: 'nowrap', willChange: 'transform' }}
        >
          {TRACK.map((s, i) => (
            <SponsorLogo
              key={i}
              {...s}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
