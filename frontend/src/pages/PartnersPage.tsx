import { useScrollReveal } from '@/hooks/useVisuals';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import { PREMIUM_SPONSORS, SUPPORTING_SPONSORS, type Sponsor } from '@/components/home/homeData';

interface Partner extends Sponsor {
  tier: 'premium' | 'standard';
}

const PARTNERS: Partner[] = [
  ...PREMIUM_SPONSORS.map((s) => ({ ...s, tier: 'premium' as const })),
  ...SUPPORTING_SPONSORS.map((s) => ({ ...s, tier: 'standard' as const })),
];

const PREMIUM = PARTNERS.filter((p) => p.tier === 'premium');
const STANDARD = PARTNERS.filter((p) => p.tier === 'standard');

function PartnerTile({ partner, index }: { partner: Partner; index: number }) {
  const scale = partner.scale ?? 1;
  return (
    <figure
      className="reveal partner-tile"
      aria-label={partner.alt}
      style={{
        margin: 0,
        display: 'grid',
        placeItems: 'center',
        aspectRatio: '4/3',
        background: 'var(--px-bg-card)',
        border: '1px solid var(--px-teal-dim)',
        padding: '20px',
        transitionDelay: `${(index % 6) * 0.06}s`,
      }}
    >
      <img
        src={`/companyLogos/${partner.file}`}
        alt={partner.alt}
        loading="lazy"
        className="partner-tile__logo"
        style={{
          maxWidth: '100%',
          maxHeight: '100%',
          width: '70%',
          height: '70%',
          objectFit: 'contain',
          ...(scale !== 1 ? { transform: `scale(${scale * 0.9})` } : {}),
        }}
      />
    </figure>
  );
}

export default function PartnersPage() {
  useScrollReveal('.reveal', PARTNERS.length);

  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '100vh',
          background: 'var(--px-bg)',
          paddingBottom: '80px',
        }}
      >
        <div style={{ maxWidth: 1100, margin: '0 auto' }}>
          <PageHeader
            title="PARTNERS"
            description="The sponsors backing FMI Codes 2026."
          />

          <section style={{ padding: '24px 24px 0' }}>
            <Panel title="PREMIUM PARTNERS">
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: '20px',
                }}
              >
                {PREMIUM.map((p, i) => (
                  <div key={p.alt} style={{ position: 'relative' }}>
                    <span
                      className="px-status-chip"
                      style={{
                        position: 'absolute',
                        top: 8,
                        left: 8,
                        zIndex: 2,
                        fontSize: '0.5rem',
                        padding: '3px 8px',
                      }}
                    >
                      &gt; PREMIUM
                    </span>
                    <PartnerTile partner={p} index={i} />
                  </div>
                ))}
              </div>
            </Panel>
          </section>

          <section style={{ padding: '24px 24px 0' }}>
            <Panel title="PARTNERS">
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
                  gap: '16px',
                }}
              >
                {STANDARD.map((p, i) => (
                  <PartnerTile key={p.alt} partner={p} index={i} />
                ))}
              </div>
            </Panel>
          </section>
        </div>
      </main>
    </>
  );
}
