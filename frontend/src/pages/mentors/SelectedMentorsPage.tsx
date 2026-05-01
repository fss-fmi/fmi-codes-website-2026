import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { Link } from 'react-router-dom';
import api from '@/lib/api';

interface SelectedMentor {
  id: number;
  name: string;
  surname: string;
  workplace?: string;
  picture_filename?: string;
  picture_data?: string;
}

function SelectedMentorsContent() {
  const { data, isLoading, error } = useQuery<{
    success: boolean;
    selected: SelectedMentor[];
    error?: string;
  }>({
    queryKey: ['selected-mentors'],
    queryFn: () => api.get('/api/mentors/available'),
  });

  const selected = data?.selected ?? [];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
      <PageHeader
        eyebrow="Mentors"
        title="Selected Mentors"
        subtitle="View the mentors your team has chosen. Update selections from the Choose Mentor page."
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && error && (
        <GlassCard style={{ padding: 48, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <p style={{ color: 'var(--muted)' }}>Failed to load mentor selection. Please try again.</p>
        </GlassCard>
      )}

      {!isLoading && !error && selected.length === 0 && (
        <GlassCard style={{ padding: 48, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>🔍</div>
          <p style={{ color: 'var(--muted)', marginBottom: 24 }}>
            No mentors selected yet. Go to the Mentor Dashboard to pick three mentors.
          </p>
          <Link
            to="/chooseMentor"
            className="btn btn-primary"
            style={{ textDecoration: 'none' }}
          >
            Choose Mentors
          </Link>
        </GlassCard>
      )}

      {!isLoading && selected.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
            gap: 20,
          }}
        >
          {selected.map((m) => {
            const imgSrc = m.picture_data
              ? `data:image/png;base64,${m.picture_data}`
              : m.picture_filename
                ? `/mentorPictures/${m.picture_filename}`
                : null;

            return (
              <GlassCard
                key={m.id}
                style={{ padding: 24 }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
                  {imgSrc ? (
                    <img
                      src={imgSrc}
                      alt={`${m.name} ${m.surname}`}
                      style={{
                        width: 52,
                        height: 52,
                        borderRadius: '50%',
                        objectFit: 'cover',
                        flexShrink: 0,
                      }}
                      onError={(e) => (e.currentTarget.style.display = 'none')}
                    />
                  ) : (
                    <div
                      style={{
                        width: 52,
                        height: 52,
                        borderRadius: '50%',
                        background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 22,
                        flexShrink: 0,
                      }}
                    >
                      👨‍💻
                    </div>
                  )}
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 16 }}>
                      {m.name} {m.surname}
                    </div>
                    {m.workplace && (
                      <div style={{ color: 'var(--muted)', fontSize: 13 }}>{m.workplace}</div>
                    )}
                  </div>
                </div>
                {m.workplace && (
                  <div
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '4px 12px',
                      borderRadius: '999px',
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      fontSize: 13,
                      color: 'var(--muted)',
                    }}
                  >
                    🏢 {m.workplace}
                  </div>
                )}
              </GlassCard>
            );
          })}
        </div>
      )}
    </main>
  );
}

export default function SelectedMentorsPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <SelectedMentorsContent />
    </RequireAuth>
  );
}
