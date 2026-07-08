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

const TRACK = [...SPONSORS, ...SPONSORS];

function useCarousel(trackRef: React.RefObject<HTMLDivElement | null>) {
  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
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

function SponsorLogo({ file, alt, premium }: { file: string; alt: string; premium: boolean }) {
  const scale = SCALE_OVERRIDES[alt];
  return (
    <a
      href="/partners"
      aria-label={alt}
      style={{
        position: 'relative',
        width: 'clamp(80px, calc(100vw / 12), 130px)',
        flexShrink: 0,
        margin: '8px',
        padding: '10px',
        border: premium ? '2px solid var(--px-teal-border)' : '1px solid var(--px-teal-dim)',
        background: 'var(--px-bg-card)',
        display: 'grid',
        placeItems: 'center',
        aspectRatio: '1/1',
        textDecoration: 'none',
        outline: 'none',
      }}
      onFocus={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.boxShadow = 'var(--px-focus-glow)';
      }}
      onBlur={(e) => {
        (e.currentTarget as HTMLAnchorElement).style.boxShadow = 'none';
      }}
    >
      <img
        src={`/companyLogos/${file}`}
        alt={alt}
        loading="lazy"
        style={{
          width: '78%',
          height: '78%',
          objectFit: 'contain',
          filter: 'brightness(0.9) contrast(1.05)',
          ...(scale ? { transform: `scale(${scale})` } : {}),
        }}
      />
    </a>
  );
}

export default function SponsorsSection() {
  const trackRef = useRef<HTMLDivElement>(null);
  useCarousel(trackRef);

  return (
    <section style={{ padding: '80px 24px 96px', maxWidth: 1200, margin: '0 auto' }}>
      <div
        style={{
          background: 'var(--px-bg-panel)',
          border: '2px solid var(--px-teal-border)',
          padding: '32px 24px',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          <h2 className="px-prompt-heading" style={{ margin: '0 0 12px 0' }}>
            SPONSORS
          </h2>
          <p
            className="px-body-sm"
            style={{
              color: 'var(--px-muted-strong)',
              maxWidth: '52ch',
              margin: '0 auto 16px',
            }}
          >
            The companies backing the next generation of builders.
          </p>
          <a
            href="/partners"
            className="px-btn-ghost"
            style={{ display: 'inline-block' }}
          >
            VIEW ALL PARTNERS →
          </a>
        </div>

        <div style={{ overflow: 'hidden', position: 'relative', width: '100%' }}>
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              bottom: 0,
              width: '80px',
              zIndex: 2,
              background: 'linear-gradient(to right, var(--px-bg-panel), transparent)',
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
              width: '80px',
              zIndex: 2,
              background: 'linear-gradient(to left, var(--px-bg-panel), transparent)',
              pointerEvents: 'none',
            }}
          />
          <div
            ref={trackRef}
            style={{ display: 'flex', flexWrap: 'nowrap', willChange: 'transform' }}
          >
            {TRACK.map((s, i) => (
              <SponsorLogo key={i} {...s} />
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
