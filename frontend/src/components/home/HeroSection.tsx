import { Link } from 'react-router-dom';
import { useConfig } from '@/context/ConfigContext';
import GradientText from '@/components/common/GradientText';
import { useEffect, useState } from 'react';

// Countdown to March 14, 2026
const TARGET = new Date('2026-03-14T09:00:00');

function formatCountdown(ms: number) {
  if (ms <= 0) return '00:00:00:00';
  const d = Math.floor(ms / 86400000);
  const h = Math.floor((ms % 86400000) / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${String(d).padStart(2, '0')}d ${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function HeroSection() {
  const { REGISTRATION_OPEN } = useConfig();
  const [countdown, setCountdown] = useState(() => formatCountdown(TARGET.getTime() - Date.now()));

  useEffect(() => {
    const id = setInterval(() => {
      setCountdown(formatCountdown(TARGET.getTime() - Date.now()));
    }, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <section
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px 60px',
        textAlign: 'center',
        position: 'relative',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '32px',
          maxWidth: '900px',
        }}
      >
        {/* Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 16px 6px 8px',
            borderRadius: '100px',
            background: 'rgba(96,165,250,0.08)',
            border: '1px solid rgba(96,165,250,0.2)',
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--accent)',
            animation: 'fadeSlideUp 0.8s ease both',
          }}
        >
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: 'var(--accent)',
              animation: 'pulse 2s ease-in-out infinite',
              flexShrink: 0,
            }}
          />
          Good luck to all participating teams!
        </div>

        {/* Logo */}
        <div
          style={{
            width: 'min(480px, 75vw)',
            animation: 'fadeSlideUp 0.8s 0.15s ease both',
            opacity: 0,
            animationFillMode: 'both',
          }}
        >
          <img
            src="/images/codes_logo3.svg"
            alt="FMI Codes 2026"
            style={{
              width: '100%',
              height: 'auto',
              display: 'block',
              filter: 'drop-shadow(0 0 60px rgba(96,165,250,0.2))',
            }}
          />
        </div>

        {/* Title */}
        <h1
          style={{
            fontSize: 'clamp(2.5rem, 6vw, 4.5rem)',
            fontWeight: 900,
            letterSpacing: '-0.03em',
            lineHeight: 1.15,
            color: '#fff',
            animation: 'fadeSlideUp 0.8s 0.3s ease both',
            animationFillMode: 'both',
          }}
        >
          Build. <GradientText>Compete.</GradientText> Innovate.
        </h1>

        {/* Subtitle */}
        <p
          style={{
            fontSize: 'clamp(1.05rem, 2vw, 1.3rem)',
            color: 'var(--muted)',
            lineHeight: 1.7,
            maxWidth: '600px',
            animation: 'fadeSlideUp 0.8s 0.45s ease both',
            animationFillMode: 'both',
          }}
        >
          Sofia University's biggest hackathon is back. 2 days to turn your boldest ideas into real,
          working projects.
        </p>

        {/* Countdown */}
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 'clamp(1.2rem, 3vw, 1.8rem)',
            fontWeight: 700,
            color: 'var(--accent)',
            letterSpacing: '0.04em',
            animation: 'fadeSlideUp 0.8s 0.55s ease both',
            animationFillMode: 'both',
          }}
        >
          {countdown}
        </div>

        {/* Actions */}
        <div
          style={{
            display: 'flex',
            gap: '16px',
            marginTop: '8px',
            flexWrap: 'wrap',
            justifyContent: 'center',
            animation: 'fadeSlideUp 0.8s 0.6s ease both',
            animationFillMode: 'both',
          }}
        >
          {REGISTRATION_OPEN && (
            <Link
              to="/registration"
              className="btn btn-primary"
              style={{
                padding: '16px 40px',
                borderRadius: '14px',
                textDecoration: 'none',
                fontSize: '1.05rem',
              }}
            >
              Register Now
              <svg
                width="18"
                height="18"
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
            </Link>
          )}
          <Link
            to="/regulations"
            className="btn btn-ghost"
            style={{
              padding: '16px 40px',
              borderRadius: '14px',
              textDecoration: 'none',
              fontSize: '1.05rem',
            }}
          >
            Learn More
          </Link>
        </div>
      </div>

      {/* bottom separator */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: '10%',
          right: '10%',
          height: '1px',
          background:
            'linear-gradient(90deg, transparent, var(--accent), var(--purple), transparent)',
          opacity: 0.4,
        }}
      />
    </section>
  );
}
