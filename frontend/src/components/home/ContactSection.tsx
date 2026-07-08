import Button from '@/components/common/Button';

const SECONDARY_LINKS = [
  { href: 'https://www.instagram.com/fmicodes/', label: 'INSTAGRAM' },
  { href: 'https://www.facebook.com/fmicodes', label: 'FACEBOOK' },
  { href: 'mailto:fss@fmi.uni-sofia.bg', label: 'EMAIL' },
  { href: 'tel:+359888888888', label: 'PHONE' },
];

export default function ContactSection() {
  return (
    <section
      style={{
        padding: '96px 24px 96px',
        maxWidth: 1100,
        margin: '0 auto',
      }}
    >
      <div
        style={{
          background: 'var(--px-bg-panel)',
          border: '2px solid var(--px-teal-border)',
          padding: '48px 40px',
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '20px',
        }}
      >
        <h2 className="px-prompt-heading" style={{ margin: 0, fontSize: 'clamp(0.85rem, 1.8vw, 1.1rem)' }}>
          JOIN THE COMMUNITY
        </h2>
        <p
          className="px-body"
          style={{
            color: 'var(--px-muted-strong)',
            maxWidth: '52ch',
            margin: 0,
          }}
        >
          Discord is the primary channel for real-time updates, questions, and announcements during
          the hackathon.
        </p>
        <Button
          variant="primary"
          href="https://discord.gg/fmicodes"
          target="_blank"
          rel="noopener noreferrer"
        >
          JOIN DISCORD
        </Button>
        <div
          style={{
            marginTop: '16px',
            display: 'flex',
            gap: '10px',
            flexWrap: 'wrap',
            justifyContent: 'center',
          }}
          role="list"
          aria-label="Other channels"
        >
          {SECONDARY_LINKS.map((s) => (
            <a
              key={s.label}
              href={s.href}
              target={s.href.startsWith('http') ? '_blank' : undefined}
              rel={s.href.startsWith('http') ? 'noopener noreferrer' : undefined}
              className="px-btn-secondary"
              style={{ padding: '10px 18px', fontSize: '0.55rem' }}
              role="listitem"
            >
              {s.label}
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
