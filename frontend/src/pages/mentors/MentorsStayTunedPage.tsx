import { useRef } from 'react';

const WORDS = ['Stay', 'Tuned'];

const PARTICLES = Array.from({ length: 18 }, (_, i) => ({
  id: i,
  left: `${5 + ((i * 5.3) % 90)}%`,
  width: `${3 + ((i * 2.7) % 6)}px`,
  height: `${3 + ((i * 2.7) % 6)}px`,
  background: ['#60a5fa', '#22d3ee', '#a78bfa', '#f472b6'][i % 4],
  delay: `${(i * 0.7) % 8}s`,
  duration: `${6 + ((i * 1.3) % 8)}s`,
  top: `${20 + ((i * 3.7) % 60)}%`,
}));

export default function MentorsStayTunedPage() {
  const containerRef = useRef<HTMLDivElement>(null);

  return (
    <div
      ref={containerRef}
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Rings */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}
      >
        {[
          {
            size: 280,
            color: 'rgba(96,165,250,0.25)',
            delay: '0s',
            shadow: '0 0 40px rgba(96,165,250,0.08)',
          },
          {
            size: 480,
            color: 'rgba(34,211,238,0.15)',
            delay: '0.8s',
            shadow: '0 0 60px rgba(34,211,238,0.06)',
          },
          {
            size: 680,
            color: 'rgba(167,139,250,0.1)',
            delay: '1.6s',
            shadow: '0 0 80px rgba(167,139,250,0.04)',
          },
        ].map((r, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              borderRadius: '50%',
              width: r.size,
              height: r.size,
              border: `1px solid ${r.color}`,
              boxShadow: r.shadow,
              animation: `stRingPulse 4s ease-in-out ${r.delay} infinite`,
            }}
          />
        ))}
      </div>

      {/* Particles */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' }}>
        {PARTICLES.map((p) => (
          <div
            key={p.id}
            style={{
              position: 'absolute',
              borderRadius: '50%',
              width: p.width,
              height: p.height,
              background: p.background,
              left: p.left,
              top: p.top,
              animation: `stParticleRise ${p.duration} ${p.delay} linear infinite`,
            }}
          />
        ))}
      </div>

      {/* Content */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '28px',
          animation: 'fadeSlideUp 0.9s ease both',
        }}
      >
        {/* Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '7px 16px',
            borderRadius: '999px',
            background: 'rgba(34,211,238,0.08)',
            border: '1px solid rgba(34,211,238,0.28)',
            color: '#67e8f9',
            fontSize: '12px',
            fontWeight: 700,
            letterSpacing: '2px',
            textTransform: 'uppercase',
          }}
        >
          <span
            style={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: '#22d3ee',
              boxShadow: '0 0 8px #22d3ee',
              display: 'inline-block',
              animation: 'stDotPulse 1.6s ease-in-out infinite',
            }}
          />
          Coming Soon
        </div>

        {/* Title */}
        <div
          style={{
            fontSize: 'clamp(54px, 12vw, 110px)',
            fontWeight: 900,
            lineHeight: 1.05,
            letterSpacing: '-2px',
            display: 'flex',
            gap: '0.35em',
            flexWrap: 'wrap',
            justifyContent: 'center',
            paddingBottom: '0.15em',
          }}
        >
          {WORDS.map((w, i) => (
            <span
              key={w}
              style={{
                display: 'inline-block',
                background:
                  i === 0
                    ? 'linear-gradient(135deg, #60a5fa, #a78bfa)'
                    : 'linear-gradient(135deg, #a78bfa, #f472b6)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                animation: `stWordBounce 6s ${i * 0.3}s ease-in-out infinite`,
              }}
            >
              {w}
            </span>
          ))}
        </div>

        <p
          style={{
            color: 'var(--muted)',
            fontSize: 'clamp(15px, 2vw, 18px)',
            maxWidth: '500px',
            lineHeight: 1.6,
            opacity: 0.9,
          }}
        >
          Our incredible mentors are preparing to join the hackathon. Check back soon!
        </p>

        {/* Social chips */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', justifyContent: 'center' }}>
          {[
            { label: 'Discord', href: 'https://discord.gg/fmicodes', color: '#7289da' },
            { label: 'Instagram', href: 'https://www.instagram.com/fmicodes/', color: '#e1306c' },
          ].map((s) => (
            <a
              key={s.label}
              href={s.href}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '10px 20px',
                borderRadius: '999px',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: 'var(--text)',
                fontSize: '14px',
                fontWeight: 600,
                textDecoration: 'none',
                transition: 'all 0.2s',
              }}
            >
              {s.label}
            </a>
          ))}
        </div>
      </div>

      <style>{`
        @keyframes stRingPulse {
          0%, 100% { transform: scale(1); opacity: 0.7; }
          50% { transform: scale(1.06); opacity: 1; }
        }
        @keyframes stParticleRise {
          0% { transform: translateY(0) scale(1); opacity: 0; }
          10% { opacity: 0.9; }
          80% { opacity: 0.5; }
          100% { transform: translateY(-90vh) scale(0.4); opacity: 0; }
        }
        @keyframes stDotPulse {
          0%, 100% { box-shadow: 0 0 6px #22d3ee; }
          50% { box-shadow: 0 0 16px #22d3ee, 0 0 32px rgba(34,211,238,0.4); }
        }
        @keyframes stWordBounce {
          0%, 100% { transform: translateY(0); }
          25% { transform: translateY(-8px); }
          75% { transform: translateY(4px); }
        }
      `}</style>
    </div>
  );
}
