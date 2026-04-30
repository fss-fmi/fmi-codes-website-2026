import Navbar from '@/components/layout/Navbar';
import GlassCard from '@/components/common/GlassCard';
import GradientText from '@/components/common/GradientText';

export default function RankingsTBDPage() {
  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '80vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 24px',
        }}
      >
        <GlassCard style={{ padding: '60px 48px', textAlign: 'center', maxWidth: 520 }}>
          <div style={{ fontSize: 72, marginBottom: 24 }}>🏆</div>
          <h1
            style={{
              fontSize: '2.5rem',
              fontWeight: 900,
              letterSpacing: '-0.02em',
              marginBottom: 12,
            }}
          >
            <GradientText>Rankings</GradientText>
          </h1>
          <p style={{ color: 'var(--muted)', fontSize: 16, lineHeight: 1.6 }}>
            Rankings will be published once the hackathon is underway. Check back soon!
          </p>
        </GlassCard>
      </main>
    </>
  );
}
