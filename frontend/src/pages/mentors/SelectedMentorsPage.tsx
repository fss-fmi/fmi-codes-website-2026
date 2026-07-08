import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import NestedCard from '@/components/common/NestedCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import Button from '@/components/common/Button';
import api from '@/lib/api';

interface SelectedMentor {
  id: number;
  name: string;
  surname: string;
  workplace?: string;
  picture_filename?: string;
  picture_data?: string;
}

function MentorTile({ m }: { m: SelectedMentor }) {
  const initialSrc = m.picture_data
    ? `data:image/png;base64,${m.picture_data}`
    : m.picture_filename
      ? `/mentorPictures/${m.picture_filename}`
      : null;
  const [imgFailed, setImgFailed] = useState(false);
  const showImage = initialSrc && !imgFailed;
  const initial = (m.name?.[0] ?? '?').toUpperCase();

  return (
    <NestedCard>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
        {showImage ? (
          <img
            src={initialSrc}
            alt={`${m.name} ${m.surname}`}
            loading="lazy"
            style={{
              width: 52,
              height: 52,
              objectFit: 'cover',
              border: '1px solid var(--px-teal-dim)',
              flexShrink: 0,
            }}
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div
            aria-hidden="true"
            style={{
              width: 52,
              height: 52,
              background: 'var(--px-bg-elevated)',
              border: '1px solid var(--px-teal-dim)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: 'var(--px-font)',
              fontSize: '0.85rem',
              color: 'var(--px-teal)',
              flexShrink: 0,
            }}
          >
            {initial}
          </div>
        )}
        <div>
          <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
            {m.name} {m.surname}
          </div>
          {m.workplace && (
            <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
              {m.workplace}
            </div>
          )}
        </div>
      </div>
      {m.workplace && (
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '4px 10px',
            background: 'var(--px-bg-elevated)',
            border: '1px solid var(--px-teal-dim)',
            fontFamily: 'var(--px-mono)',
            fontSize: '0.75rem',
            color: 'var(--px-muted-strong)',
          }}
        >
          <span aria-hidden="true" style={{ width: 6, height: 6, background: 'var(--px-teal)' }} />
          {m.workplace}
        </div>
      )}
    </NestedCard>
  );
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
    <main style={{ padding: '80px 24px 80px', maxWidth: '960px', margin: '0 auto' }}>
      <PageHeader
        title="YOUR MENTOR TEAM"
        description="Mentors your team has chosen. Update selections from the Choose Mentor page."
      />

      {isLoading && <LoadingSpinner />}

      {!isLoading && error && (
        <Panel title="ERROR">
          <p className="px-body" style={{ color: 'var(--px-danger)', margin: 0 }}>
            &gt; Failed to load mentor selection. Please try again.
          </p>
        </Panel>
      )}

      {!isLoading && !error && selected.length === 0 && (
        <Panel title="> NO MENTORS ASSIGNED YET">
          <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}>
            &gt; No mentors selected yet. Head to the Mentor Dashboard to pick three mentors.
          </p>
          <Button variant="primary" href="/chooseMentor">
            CHOOSE MENTORS
          </Button>
        </Panel>
      )}

      {!isLoading && selected.length > 0 && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
            gap: 20,
          }}
        >
          {selected.map((m) => (
            <MentorTile key={m.id} m={m} />
          ))}
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
