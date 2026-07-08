import { useScrollReveal } from '@/hooks/useVisuals';
import Navbar from '@/components/layout/Navbar';

interface Partner {
  file: string;
  alt: string;
  tier: 'premium' | 'standard';
  scaleOverride?: number;
}

const PARTNERS: Partner[] = [
  { file: 'avenga.svg', alt: 'Avenga', tier: 'premium' },
  { file: 'gameloft.png', alt: 'Gameloft', tier: 'premium' },
  { file: 'EnduroSat.png', alt: 'EnduroSat', tier: 'premium' },
  { file: 'waracle.png', alt: 'Waracle', tier: 'premium', scaleOverride: 1.2 },
  { file: 'SAP.png', alt: 'SAP', tier: 'premium' },
  { file: 'Milestone.png', alt: 'Milestone', tier: 'premium', scaleOverride: 1.5 },
  { file: 'astea.svg', alt: 'Astea', tier: 'standard', scaleOverride: 1.2 },
  { file: 'chaos.jpg', alt: 'Chaos', tier: 'standard' },
  { file: 'Dreamix.png', alt: 'Dreamix', tier: 'standard', scaleOverride: 1.4 },
  { file: 'engineerAcces.png', alt: 'Engineer Access', tier: 'standard', scaleOverride: 1.15 },
  { file: 'raven.svg', alt: 'Raven', tier: 'standard', scaleOverride: 1.25 },
  { file: 'Experian.jpg', alt: 'Experian', tier: 'standard', scaleOverride: 1.2 },
];

const PREMIUM = PARTNERS.filter((p) => p.tier === 'premium');
const STANDARD = PARTNERS.filter((p) => p.tier === 'standard');

/* ── Battlements divider SVG ─────────────────────────────────────────── */
function BattlementsDivider({ flip = false }: { flip?: boolean }) {
  return (
    <svg
      viewBox="0 0 120 16"
      preserveAspectRatio="none"
      aria-hidden="true"
      style={{
        width: '100%',
        height: '16px',
        display: 'block',
        transform: flip ? 'scaleY(-1)' : undefined,
        opacity: 0.18,
      }}
    >
      <path
        d="M0,16 L0,8 L10,8 L10,0 L20,0 L20,8 L30,8 L30,0 L40,0 L40,8 L50,8 L50,0 L60,0 L60,8 L70,8 L70,0 L80,0 L80,8 L90,8 L90,0 L100,0 L100,8 L110,8 L110,0 L120,0 L120,8 L120,16 Z"
        fill="var(--torch-gold)"
      />
    </svg>
  );
}

/* ── Wax-seal tier badge ─────────────────────────────────────────────── */
function TierBadge({ label }: { label: string }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        padding: '5px 18px',
        borderRadius: '100px',
        background: 'rgba(212,168,67,0.08)',
        border: '1px solid rgba(212,168,67,0.25)',
        fontSize: '0.68rem',
        fontFamily: 'var(--font-heading)',
        fontWeight: 700,
        letterSpacing: '0.18em',
        textTransform: 'uppercase' as const,
        color: 'var(--torch-gold)',
        marginBottom: '12px',
      }}
    >
      <span style={{ fontSize: '0.85rem' }}>⚜️</span>
      {label}
    </div>
  );
}

/* ── Individual partner tile ─────────────────────────────────────────── */
function PartnerTile({ partner, index }: { partner: Partner; index: number }) {
  const isPremium = partner.tier === 'premium';
  return (
    <div
      className="castle-card reveal"
      style={{
        padding: isPremium ? '32px 28px' : '24px 20px',
        display: 'grid',
        placeItems: 'center',
        aspectRatio: '4/3',
        transitionDelay: `${(index % 6) * 0.06}s`,
        cursor: 'default',
      }}
    >
      {/* inner top-edge highlight */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: '1px',
          background: isPremium
            ? 'linear-gradient(90deg, transparent, rgba(212,168,67,0.35), transparent)'
            : 'linear-gradient(90deg, transparent, rgba(176,190,197,0.15), transparent)',
        }}
      />
      <img
        src={`/companyLogos/${partner.file}`}
        alt={partner.alt}
        style={{
          maxWidth: '100%',
          maxHeight: '100%',
          width: '70%',
          height: '70%',
          objectFit: 'contain',
          filter: 'brightness(0.9) saturate(0.85)',
          transition: 'filter 0.3s, transform 0.3s',
          ...(partner.scaleOverride ? { transform: `scale(${partner.scaleOverride * 0.9})` } : {}),
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLImageElement).style.filter = 'brightness(1.1) saturate(1)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLImageElement).style.filter = 'brightness(0.9) saturate(0.85)';
        }}
      />
    </div>
  );
}

/* ── Section heading ─────────────────────────────────────────────────── */
function SectionHeading({
  tier,
  title,
  subtitle,
}: {
  tier: Partner['tier'];
  title: string;
  subtitle: string;
}) {
  return (
    <div
      className="reveal"
      style={{ textAlign: 'center', marginBottom: '40px' }}
    >
      <TierBadge label={tier === 'premium' ? 'Premium Partners' : 'Partners'} />
      <h2
        style={{
          fontFamily: 'var(--font-heading)',
          fontSize: 'clamp(1.6rem, 3vw, 2.4rem)',
          fontWeight: 700,
          color: 'var(--parchment)',
          marginBottom: '10px',
          letterSpacing: '0.04em',
        }}
      >
        {title}
      </h2>
      <p style={{ color: 'var(--parchment-dim)', fontSize: '0.95rem', lineHeight: 1.7 }}>
        {subtitle}
      </p>
    </div>
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
          background: `radial-gradient(ellipse at 50% 0%, #1a1f2e 0%, #08090f 70%)`,
          paddingBottom: '100px',
        }}
      >
        {/* ── Page header ── */}
        <div
          style={{
            maxWidth: '900px',
            margin: '0 auto',
            padding: '60px 24px 0',
            textAlign: 'center',
          }}
        >
          <div
            className="reveal"
            style={{ marginBottom: '8px' }}
          >
            <TierBadge label="Patrons of the Realm" />
          </div>

          <h1
            className="castle-gradient-text reveal"
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'clamp(2rem, 5vw, 3.8rem)',
              fontWeight: 900,
              lineHeight: 1.15,
              marginBottom: '20px',
            }}
          >
            Our Partners
          </h1>

          <p
            className="reveal"
            style={{
              color: 'var(--parchment-dim)',
              fontSize: '1.05rem',
              lineHeight: 1.8,
              maxWidth: '600px',
              margin: '0 auto 48px',
            }}
          >
            The companies shaping tomorrow's technology — standing alongside the champions of the
            realm and supporting the next generation of builders.
          </p>

          <BattlementsDivider />
        </div>

        {/* ── Premium Partners ── */}
        <section style={{ maxWidth: '1100px', margin: '60px auto 0', padding: '0 24px' }}>
          <SectionHeading
            tier="premium"
            title="Premium Partners"
            subtitle="The great houses that make this tournament possible."
          />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: '20px',
            }}
          >
            {PREMIUM.map((p, i) => (
              <PartnerTile
                key={p.alt}
                partner={p}
                index={i}
              />
            ))}
          </div>
        </section>

        {/* ── Divider ── */}
        <div style={{ maxWidth: '700px', margin: '64px auto 0', padding: '0 24px' }}>
          <div
            style={{
              height: '1px',
              background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.2), transparent)',
            }}
          />
          <BattlementsDivider flip />
        </div>

        {/* ── Standard Partners ── */}
        <section style={{ maxWidth: '1100px', margin: '48px auto 0', padding: '0 24px' }}>
          <SectionHeading
            tier="standard"
            title="Partners"
            subtitle="Allies of the realm whose contributions enrich our community."
          />
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: '16px',
            }}
          >
            {STANDARD.map((p, i) => (
              <PartnerTile
                key={p.alt}
                partner={p}
                index={i}
              />
            ))}
          </div>
        </section>

        {/* ── Bottom battlements ── */}
        <div style={{ maxWidth: '700px', margin: '64px auto 0', padding: '0 24px' }}>
          <div
            style={{
              height: '1px',
              background: 'linear-gradient(90deg, transparent, rgba(212,168,67,0.2), transparent)',
              marginBottom: '0',
            }}
          />
          <BattlementsDivider />
        </div>
      </main>
    </>
  );
}
