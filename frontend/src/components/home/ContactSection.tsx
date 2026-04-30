import GradientText from '@/components/common/GradientText';

const SOCIALS = [
  {
    href: 'https://www.instagram.com/fmicodes/',
    label: 'Instagram',
    cls: 'instagram',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <rect
          x="2"
          y="2"
          width="20"
          height="20"
          rx="5"
          ry="5"
        />
        <path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z" />
        <line
          x1="17.5"
          y1="6.5"
          x2="17.51"
          y2="6.5"
        />
      </svg>
    ),
    hoverStyle: {
      background: 'rgba(225,48,108,0.08)',
      borderColor: 'rgba(225,48,108,0.45)',
      boxShadow: '0 4px 24px rgba(225,48,108,0.18)',
      color: '#fff',
    },
  },
  {
    href: 'https://www.facebook.com/fmicodes',
    label: 'Facebook',
    cls: 'facebook',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z" />
      </svg>
    ),
    hoverStyle: {
      background: 'rgba(24,119,242,0.08)',
      borderColor: 'rgba(24,119,242,0.45)',
      boxShadow: '0 4px 24px rgba(24,119,242,0.18)',
      color: '#fff',
    },
  },
  {
    href: 'mailto:fss@fmi.uni-sofia.bg',
    label: 'Email',
    cls: 'email',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
        <polyline points="22,6 12,13 2,6" />
      </svg>
    ),
    hoverStyle: {
      background: 'rgba(96,165,250,0.08)',
      borderColor: 'rgba(96,165,250,0.45)',
      boxShadow: '0 4px 24px rgba(96,165,250,0.18)',
      color: '#fff',
    },
  },
  {
    href: 'tel:+359888888888',
    label: '+359 88 888 8888',
    cls: 'phone',
    icon: (
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.69 12a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3.59 1h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L8.09 8.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 22 16.92z" />
      </svg>
    ),
    hoverStyle: {
      background: 'rgba(34,197,94,0.08)',
      borderColor: 'rgba(34,197,94,0.45)',
      boxShadow: '0 4px 24px rgba(34,197,94,0.18)',
      color: '#fff',
    },
  },
];

export default function ContactSection() {
  return (
    <section
      style={{
        position: 'relative',
        padding: '120px 24px 140px',
        textAlign: 'center',
        overflow: 'hidden',
      }}
    >
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

      {/* Radial glow */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: 0,
          right: 0,
          height: '70%',
          background:
            'radial-gradient(ellipse 70% 55% at 50% 100%, rgba(88,101,242,0.09) 0%, transparent 70%)',
          pointerEvents: 'none',
          zIndex: 0,
        }}
      />

      {/* Big watermark text */}
      <div
        style={{
          position: 'absolute',
          bottom: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          fontSize: 'clamp(70px, 14vw, 150px)',
          fontWeight: 900,
          letterSpacing: '-0.04em',
          color: 'transparent',
          WebkitTextStroke: '1px rgba(255,255,255,0.04)',
          whiteSpace: 'nowrap',
          pointerEvents: 'none',
          userSelect: 'none',
          zIndex: 0,
          lineHeight: 1,
        }}
      >
        FMI&#123;Codes&#125;
      </div>

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          maxWidth: '660px',
          margin: '0 auto',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 0,
        }}
      >
        {/* Discord */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '22px',
            marginBottom: '72px',
          }}
        >
          <a
            href="https://discord.gg/fmicodes"
            target="_blank"
            rel="noopener noreferrer"
            style={{
              filter: 'drop-shadow(0 0 28px rgba(88,101,242,0.55))',
              transition: 'filter 0.3s',
              textDecoration: 'none',
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.filter = 'drop-shadow(0 0 44px rgba(88,101,242,0.85))')
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.filter = 'drop-shadow(0 0 28px rgba(88,101,242,0.55))')
            }
          >
            <svg
              width="64"
              height="64"
              viewBox="0 0 71 55"
              fill="none"
            >
              <path
                d="M60.1 4.9A58.55 58.55 0 0 0 45.58.1a40.88 40.88 0 0 0-1.85 3.78 54.26 54.26 0 0 0-16.45 0A40.47 40.47 0 0 0 25.42.1 58.33 58.33 0 0 0 10.9 4.91a61.52 61.52 0 0 0-10.84 40 58.82 58.82 0 0 0 18.1 9.1 44.24 44.24 0 0 0 3.8-6.18c-2.1-.79-4.1-1.76-6-2.89l1.46-1.15a41.93 41.93 0 0 0 35.85 0l1.47 1.15a40.28 40.28 0 0 1-6 2.9 44.19 44.19 0 0 0 3.79 6.17 58.57 58.57 0 0 0 18.1-9.08 61.52 61.52 0 0 0-10.82-40.03zM23.73 36.7c-3.55 0-6.46-3.23-6.46-7.2 0-3.97 2.85-7.2 6.46-7.2 3.6 0 6.53 3.24 6.46 7.2 0 3.97-2.86 7.2-6.46 7.2zm23.54 0c-3.55 0-6.46-3.23-6.46-7.2 0-3.97 2.85-7.2 6.46-7.2 3.6 0 6.53 3.24 6.46 7.2 0 3.97-2.85 7.2-6.46 7.2z"
                fill="#5865F2"
              />
            </svg>
          </a>

          <h2
            style={{
              fontSize: 'clamp(2.4rem, 5.5vw, 4rem)',
              fontWeight: 900,
              lineHeight: 1.15,
              letterSpacing: '-0.03em',
              color: '#fff',
              margin: 0,
            }}
          >
            Join Our <GradientText>Community</GradientText>
          </h2>
          <p
            style={{
              fontSize: '1.05rem',
              color: 'var(--muted)',
              lineHeight: 1.75,
              maxWidth: '460px',
              margin: 0,
            }}
          >
            Connect with participants, get real-time updates, and be the first to hear
            announcements.
          </p>
          <a
            href="https://discord.gg/fmicodes"
            target="_blank"
            rel="noopener noreferrer"
            className="btn"
            style={{
              padding: '16px 40px',
              borderRadius: '14px',
              fontSize: '1.05rem',
              textDecoration: 'none',
              background: 'linear-gradient(135deg, #5865f2 0%, #7289da 100%)',
              color: '#fff',
              boxShadow: '0 0 40px rgba(88,101,242,0.45), 0 4px 24px rgba(0,0,0,0.35)',
            }}
          >
            Join Discord
          </a>
        </div>

        {/* Divider */}
        <div
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            gap: '16px',
            marginBottom: '36px',
          }}
        >
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.06)' }} />
          <span
            style={{
              fontSize: '0.68rem',
              textTransform: 'uppercase',
              letterSpacing: '0.15em',
              color: 'var(--muted)',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            Other channels
          </span>
          <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.06)' }} />
        </div>

        {/* Social pills */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            justifyContent: 'center',
            gap: '10px',
          }}
        >
          {SOCIALS.map((s) => (
            <a
              key={s.label}
              href={s.href}
              target={s.href.startsWith('http') ? '_blank' : undefined}
              rel={s.href.startsWith('http') ? 'noopener noreferrer' : undefined}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 22px',
                borderRadius: '100px',
                textDecoration: 'none',
                color: 'var(--muted)',
                fontSize: '0.88rem',
                fontWeight: 600,
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.06)',
                transition: 'all 0.25s',
              }}
              onMouseEnter={(e) => Object.assign(e.currentTarget.style, s.hoverStyle)}
              onMouseLeave={(e) =>
                Object.assign(e.currentTarget.style, {
                  background: 'rgba(255,255,255,0.03)',
                  borderColor: 'rgba(255,255,255,0.06)',
                  boxShadow: 'none',
                  color: 'var(--muted)',
                })
              }
            >
              {s.icon}
              {s.label}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
