import { useEffect, useRef } from 'react';
import GradientText from '@/components/common/GradientText';

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
          background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)',
        }}
      />

      {/* Header */}
      <div
        className="reveal"
        style={{ textAlign: 'center', marginBottom: '56px' }}
      >
        <div
          style={{
            display: 'inline-block',
            fontSize: '0.7rem',
            textTransform: 'uppercase',
            letterSpacing: '0.15em',
            color: 'var(--accent)',
            fontWeight: 700,
            marginBottom: '12px',
            padding: '4px 14px',
            borderRadius: '100px',
            background: 'rgba(96,165,250,0.08)',
            border: '1px solid rgba(96,165,250,0.15)',
          }}
        >
          Partners
        </div>
        <h2
          style={{
            fontSize: 'clamp(1.8rem, 3.5vw, 2.8rem)',
            fontWeight: 800,
            color: '#fff',
            marginBottom: '14px',
            lineHeight: 1.2,
          }}
        >
          Backed by <GradientText>Industry Leaders</GradientText>
        </h2>
        <p
          style={{
            fontSize: '1rem',
            color: 'var(--muted)',
            maxWidth: '520px',
            margin: '0 auto',
            lineHeight: 1.7,
          }}
        >
          The companies shaping tomorrow's tech — supporting the next generation of builders.
        </p>
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
