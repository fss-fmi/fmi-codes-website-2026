import { useScrollReveal } from '@/hooks/useVisuals';

interface BentoItem {
  icon: string;
  label: string;
  value: string;
  delay: number;
}

const ITEMS: BentoItem[] = [
  { icon: '⚔', label: 'DATE', value: 'March 2026', delay: 0 },
  { icon: '🏰', label: 'LOCATION', value: 'FMI, Sofia', delay: 0.08 },
  { icon: '🛡', label: 'TEAMS', value: 'Up to 18', delay: 0.16 },
  { icon: '⏳', label: 'DURATION', value: '48 Hours', delay: 0.24 },
];

export default function BentoGrid() {
  useScrollReveal('.bento-card');

  return (
    <section
      style={{
        padding: '40px 24px 80px',
        maxWidth: '1100px',
        margin: '0 auto',
        background: 'var(--px-bg)',
      }}
    >
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: '16px',
        }}
      >
        {ITEMS.map((item) => (
          <div
            key={item.label}
            className="px-card bento-card reveal"
            style={{
              textAlign: 'center',
              transitionDelay: `${item.delay}s`,
              padding: '32px 20px',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <div style={{ fontSize: '2rem', lineHeight: 1 }}>{item.icon}</div>
            <div
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '0.45rem',
                color: 'var(--px-teal)',
                letterSpacing: '0.1em',
              }}
            >
              {item.label}
            </div>
            <div
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: 'clamp(0.7rem, 1.8vw, 1rem)',
                color: 'var(--px-white)',
              }}
            >
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
