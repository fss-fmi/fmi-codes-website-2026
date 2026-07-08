import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useScrollReveal } from '@/hooks/useVisuals';
import api from '@/lib/api';

interface Regulation {
  question: string;
  answer: string;
}

export default function RegulationsPage() {
  const { data, isLoading, error } = useQuery<Regulation[]>({
    queryKey: ['regulations'],
    queryFn: () =>
      api
        .get<{ success: boolean; regulations: Regulation[] }>('/api/regulations')
        .then((r) => r.regulations),
    staleTime: 5 * 60_000,
  });

  useScrollReveal('.reg-card', data?.length);

  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '100vh',
          background: 'var(--px-bg)',
          padding: '40px 24px 80px',
        }}
      >
        {/* Grid bg */}
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundImage:
              'linear-gradient(rgba(45,212,191,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(45,212,191,0.03) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />

        <div
          style={{
            position: 'relative',
            zIndex: 1,
            maxWidth: '1200px',
            margin: '0 auto',
            display: 'flex',
            gap: '32px',
            flexWrap: 'wrap',
            alignItems: 'flex-start',
          }}
        >
          {/* ── Left panel: regulations ── */}
          <div
            style={{
              flex: '2 1 500px',
              border: '2px solid var(--px-teal-border)',
              background: 'var(--px-bg-card)',
              padding: '32px',
            }}
          >
            <h1
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: 'clamp(0.8rem, 2vw, 1.1rem)',
                color: 'var(--px-teal)',
                marginBottom: '32px',
                lineHeight: 1.5,
              }}
            >
              &gt; REGULATIONS
            </h1>

            {isLoading && (
              <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
                <LoadingSpinner />
              </div>
            )}

            {error && (
              <p
                style={{
                  color: 'var(--px-salmon)',
                  fontFamily: 'var(--px-font)',
                  fontSize: '0.55rem',
                  lineHeight: 1.8,
                }}
              >
                &gt; ERROR: Failed to load regulations.
              </p>
            )}

            {data && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
                {data.map((reg, i) => (
                  <div
                    key={i}
                    className="reg-card reveal"
                    style={{
                      transitionDelay: `${(i % 5) * 0.06}s`,
                      borderBottom: '1px solid var(--px-teal-dim)',
                      padding: '20px 0',
                    }}
                  >
                    <h3
                      style={{
                        fontFamily: 'var(--px-font)',
                        fontSize: '0.55rem',
                        color: 'var(--px-teal)',
                        marginBottom: '12px',
                        lineHeight: 1.6,
                        textTransform: 'uppercase' as const,
                      }}
                    >
                      {reg.question}
                    </h3>
                    <p
                      style={{
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: '0.85rem',
                        color: 'var(--px-white)',
                        lineHeight: 1.8,
                        opacity: 0.85,
                      }}
                    >
                      {reg.answer}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* ── Right panel: info + CTA ── */}
          <div
            style={{
              flex: '1 1 280px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
            }}
          >
            {/* Big heading */}
            <h2
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: 'clamp(1rem, 3vw, 1.6rem)',
                color: 'var(--px-salmon)',
                lineHeight: 1.5,
                margin: 0,
              }}
            >
              CODE
              <br />
              FOR
              <br />
              SAFETY
            </h2>

            <p
              style={{
                fontFamily: 'JetBrains Mono, monospace',
                fontSize: '0.8rem',
                color: 'var(--px-muted)',
                lineHeight: 1.8,
                margin: 0,
              }}
            >
              &gt; ENTER THE DIGITAL ARENA.
              <br />
              &gt; BUILD THE FUTURE.
              <br />
              &gt; PRESS START.
            </p>

            <Link
              to="/registration"
              className="px-btn px-btn-filled"
              style={{ textAlign: 'center' }}
            >
              REGISTER NOW
            </Link>

            {/* Castle image */}
            <div style={{ border: '2px solid var(--px-teal-border)', overflow: 'hidden' }}>
              <img
                src="/castle.jpg"
                alt="FMI Codes Castle"
                style={{ width: '100%', height: '180px', objectFit: 'cover', display: 'block' }}
              />
            </div>

            {/* About text */}
            <div
              style={{
                border: '1px solid var(--px-teal-border)',
                padding: '16px',
                background: 'var(--px-bg-card)',
              }}
            >
              <p
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.75rem',
                  color: 'var(--px-muted)',
                  lineHeight: 1.8,
                  margin: 0,
                }}
              >
                &gt; ABOUT THE EVENT:
                <br />
                Sofia University's biggest hackathon. 48 hours. Real projects. Real glory.
              </p>
            </div>

            {/* Nav buttons */}
            <div className="px-action-row">
              <Link
                to="/mentors"
                className="px-btn"
                style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
              >
                MENTORS
              </Link>
              <Link
                to="/schedule"
                className="px-btn"
                style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
              >
                SCHEDULE
              </Link>
              <Link
                to="/rankings"
                className="px-btn"
                style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
              >
                RANKINGS
              </Link>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
