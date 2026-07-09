import { Link } from 'react-router-dom';
import { useConfig } from '@/context/ConfigContext';

export default function HeroSection() {
  const { REGISTRATION_OPEN } = useConfig();

  return (
    <section
      style={{
        minHeight: '100vh',
        background: 'var(--px-bg)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '80px 24px 40px',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 420px',
          gap: '48px',
          alignItems: 'center',
          maxWidth: '1280px',
          width: '100%',
        }}
      >
        {/* LEFT: large castle frame with two knights — double border */}
        <div
          style={{
            border: '3px solid var(--px-teal-border)',
            padding: '6px',
            position: 'relative',
          }}
        >
          <div
            style={{
              border: '2px solid var(--px-teal-border)',
              position: 'relative',
              overflow: 'hidden',
              aspectRatio: '4/3',
            }}
          >
            <img
              src="/castle.jpg"
              alt="Castle"
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
            {/* Knight left */}
            <img
              src="/knight.svg"
              alt=""
              aria-hidden="true"
              style={{
                position: 'absolute',
                bottom: 0,
                left: '4%',
                height: '42%',
                width: 'auto',
              }}
            />
            {/* Knight right — mirrored */}
            <img
              src="/knight.svg"
              alt=""
              aria-hidden="true"
              style={{
                position: 'absolute',
                bottom: 0,
                right: '4%',
                height: '42%',
                width: 'auto',
                transform: 'scaleX(-1)',
              }}
            />
          </div>
        </div>

        {/* RIGHT: heading + CTA + about card + nav buttons */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
          {/* Main heading */}
          <h1
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: 'clamp(1.4rem, 3vw, 2.2rem)',
              color: 'var(--px-salmon)',
              lineHeight: 1.4,
              margin: 0,
            }}
          >
            CODE FOR
            <br />
            SAFETY
          </h1>

          {/* Subtitle */}
          <p
            style={{
              fontFamily: 'JetBrains Mono, monospace',
              fontSize: '0.8rem',
              color: 'var(--px-teal)',
              margin: 0,
              lineHeight: 1.7,
            }}
          >
            &gt; ENTER THE DIGITAL ARENA. BUILD THE FUTURE, PRESS START.
          </p>

          {/* Register button */}
          {REGISTRATION_OPEN && (
            <Link
              to="/registration"
              style={{ display: 'block' }}
            >
              <button
                className="px-btn-filled"
                style={{
                  width: '100%',
                  padding: '16px',
                  fontSize: '0.55rem',
                  letterSpacing: '0.1em',
                  cursor: 'pointer',
                }}
              >
                REGISTER NOW
              </button>
            </Link>
          )}

          {/* About card */}
          <div
            style={{
              border: '2px solid var(--px-salmon)',
              background: 'var(--px-bg-card)',
              display: 'flex',
              gap: '0',
              alignItems: 'stretch',
              overflow: 'hidden',
            }}
          >
            <img
              src="/castle.jpg"
              alt=""
              style={{
                width: '160px',
                minHeight: '120px',
                objectFit: 'cover',
                flexShrink: 0,
                display: 'block',
              }}
            />
            <div style={{ padding: '14px' }}>
              <div
                style={{
                  fontFamily: 'var(--px-font)',
                  fontSize: '0.42rem',
                  color: 'var(--px-salmon)',
                  marginBottom: '10px',
                }}
              >
                &gt; ABOUT THE EVENT:
              </div>
              <p
                style={{
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.72rem',
                  color: 'var(--px-muted)',
                  margin: 0,
                  lineHeight: 1.6,
                }}
              >
                Join top coders in a 48-hour retro-futuristic hackathon. Build innovative solutions
                with next-gen technologies and win digital glory.
              </p>
            </div>
          </div>

          {/* Nav buttons */}
          <div style={{ display: 'flex', gap: '8px' }}>
            <Link
              to="/regulations"
              style={{
                flex: 1,
                textAlign: 'center',
                fontFamily: 'var(--px-font)',
                fontSize: '0.38rem',
                padding: '12px 6px',
                textDecoration: 'none',
                border: '2px solid var(--px-teal-border)',
                color: 'var(--px-teal)',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              📜 REGULATIONS
            </Link>
            <Link
              to="/rankings"
              style={{
                flex: 1,
                textAlign: 'center',
                fontFamily: 'var(--px-font)',
                fontSize: '0.38rem',
                padding: '12px 6px',
                textDecoration: 'none',
                border: '2px solid var(--px-teal-border)',
                color: 'var(--px-teal)',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              🏆 RANKINGS
            </Link>
            <Link
              to="/mentors"
              style={{
                flex: 1,
                textAlign: 'center',
                fontFamily: 'var(--px-font)',
                fontSize: '0.38rem',
                padding: '12px 6px',
                textDecoration: 'none',
                border: '2px solid var(--px-teal-border)',
                color: 'var(--px-teal)',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
              }}
            >
              👤 MENTORS
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
