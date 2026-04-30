import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useScrollReveal } from '@/hooks/useVisuals';
import api from '@/lib/api';

interface Regulation {
  question: string;
  answer: string;
}

const ACCENT_COLORS = ['#60a5fa', '#a78bfa', '#22d3ee', '#f472b6', '#34d399', '#f59e0b'];

export default function RegulationsPage() {
  useScrollReveal();

  const { data, isLoading, error } = useQuery<Regulation[]>({
    queryKey: ['regulations'],
    queryFn: () =>
      api
        .get<{ success: boolean; regulations: Regulation[] }>('/api/regulations')
        .then((r) => r.regulations),
    staleTime: 5 * 60_000,
  });

  return (
    <>
      <Navbar />
      <main style={{ padding: '0 0 80px' }}>
        <PageHeader
          eyebrow="Rules"
          title="Regulations"
          subtitle="Everything you need to know to participate in FMI{Codes} 2026."
        />

        <div style={{ maxWidth: '900px', margin: '0 auto', padding: '0 24px' }}>
          {isLoading && <LoadingSpinner />}
          {error && (
            <p style={{ color: '#ef4444', textAlign: 'center', padding: '40px 0' }}>
              Failed to load regulations. Please try again.
            </p>
          )}
          {data && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {data.map((reg, i) => (
                <div
                  key={i}
                  className="reveal"
                  style={{ transitionDelay: `${(i % 6) * 0.06}s` }}
                >
                  <GlassCard
                    accentColor={ACCENT_COLORS[i % ACCENT_COLORS.length]}
                    style={{ padding: '28px 32px' }}
                  >
                    <h3
                      style={{
                        fontSize: '1rem',
                        fontWeight: 700,
                        color: 'var(--text)',
                        marginBottom: '12px',
                        lineHeight: 1.4,
                      }}
                    >
                      {reg.question}
                    </h3>
                    <p style={{ fontSize: '0.9rem', color: 'var(--muted)', lineHeight: 1.8 }}>
                      {reg.answer}
                    </p>
                  </GlassCard>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </>
  );
}
