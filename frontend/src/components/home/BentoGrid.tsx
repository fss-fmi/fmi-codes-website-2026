import { useScrollReveal } from '@/hooks/useVisuals';

interface BentoItem {
  icon: string;
  iconClass: string;
  label: string;
  value: string;
  delay: number;
}

const ITEMS: BentoItem[] = [
  { icon: '📅', iconClass: 'icon-blue', label: 'Date', value: 'March 2026', delay: 0 },
  { icon: '📍', iconClass: 'icon-cyan', label: 'Location', value: 'FMI, Sofia', delay: 0.1 },
  { icon: '👥', iconClass: 'icon-purple', label: 'Teams', value: 'Up to 18', delay: 0.2 },
  { icon: '⏳', iconClass: 'icon-amber', label: 'Duration', value: '48 Hours', delay: 0.3 },
];

export default function BentoGrid() {
  useScrollReveal('.bento-card');

  return (
    <section style={{ padding: '0 24px 100px', maxWidth: '1100px', margin: '0 auto' }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '16px',
        }}
      >
        {ITEMS.map((item) => (
          <div
            key={item.label}
            className="glass-card bento-card reveal"
            style={{ textAlign: 'center', transitionDelay: `${item.delay}s`, padding: '32px 24px' }}
          >
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '24px',
                margin: '0 auto 16px',
                background:
                  item.iconClass === 'icon-blue'
                    ? 'rgba(96,165,250,0.15)'
                    : item.iconClass === 'icon-cyan'
                      ? 'rgba(34,211,238,0.15)'
                      : item.iconClass === 'icon-purple'
                        ? 'rgba(167,139,250,0.15)'
                        : 'rgba(245,158,11,0.15)',
              }}
            >
              {item.icon}
            </div>
            <div
              style={{
                fontSize: '0.7rem',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
                color: 'var(--muted)',
                fontWeight: 700,
                marginBottom: '6px',
              }}
            >
              {item.label}
            </div>
            <div
              style={{
                fontSize: '1.4rem',
                fontWeight: 800,
                color: '#fff',
                fontFamily: "'JetBrains Mono', monospace",
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
