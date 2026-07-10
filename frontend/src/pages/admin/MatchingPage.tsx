import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import KPICard from '@/components/admin/KPICard';
import Clock from '@/components/admin/Clock';
import api from '@/lib/api';
import type { RegStatus, PrefStatus, Tab } from './panels/shared';
import RegistrationPanel from './panels/RegistrationPanel';
import PreferencesPanel from './panels/PreferencesPanel';
import MatchingPanel from './panels/MatchingPanel';
import ScoresPanel from './panels/ScoresPanel';

function MatchingContent() {
  const [tab, setTab] = useState<Tab>('registration');

  const { data: regData } = useQuery<RegStatus>({
    queryKey: ['admin-reg-status'],
    queryFn: () => api.get('/api/admin/teams/registration-status'),
  });

  const { data: prefData } = useQuery<PrefStatus>({
    queryKey: ['admin-pref-status'],
    queryFn: () => api.get('/api/admin/preference-status'),
  });

  const { data: matchData } = useQuery<{ success: boolean; confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const matchingLabel = matchData ? (matchData.confirmed ? 'CONFIRMED' : 'PENDING') : undefined;

  const tabs: { key: Tab; label: string; badge?: string | number }[] = [
    {
      key: 'registration',
      label: 'REGISTRATION',
      badge: regData ? `${regData.registered_count}/${regData.max_registered}` : undefined,
    },
    {
      key: 'preferences',
      label: 'PREFERENCES',
      badge: prefData ? `${prefData.teams_submitted}` : undefined,
    },
    { key: 'matching', label: 'MATCHING', badge: matchingLabel },
    { key: 'scores', label: 'SCORES' },
  ];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '1100px', margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: 32,
          gap: 20,
          flexWrap: 'wrap',
        }}
      >
        <PageHeader title="MISSION CONTROL" />
        <Clock />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 16,
          marginBottom: 32,
        }}
      >
        <KPICard
          label="REGISTERED TEAMS"
          value={regData ? `${regData.registered_count}/${regData.max_registered}` : '—'}
          unit="slots"
        />
        <KPICard
          label="IN QUEUE"
          value={regData ? regData.queue_count : '—'}
          unit="waiting"
        />
        <KPICard
          label="TEAMS W/ PREFS"
          value={prefData ? `${prefData.teams_submitted}/${prefData.teams_total}` : '—'}
        />
        <KPICard
          label="MENTORS W/ PREFS"
          value={prefData ? `${prefData.mentors_submitted}/${prefData.mentors_total}` : '—'}
        />
        <KPICard label="MATCHING STATE" value={matchingLabel ?? '—'} />
      </div>

      <div
        style={{
          display: 'flex',
          gap: 8,
          marginBottom: 24,
          borderBottom: '2px solid var(--px-teal-border)',
          paddingBottom: 0,
          flexWrap: 'wrap',
        }}
      >
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            style={{
              padding: '12px 18px',
              border: 'none',
              cursor: 'pointer',
              fontFamily: 'var(--px-font)',
              fontSize: '0.6rem',
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              background: 'transparent',
              color: tab === t.key ? 'var(--px-teal)' : 'var(--px-muted-strong)',
              borderBottom:
                tab === t.key ? '2px solid var(--px-teal)' : '2px solid transparent',
              marginBottom: -2,
              transition: 'color 0.2s',
            }}
          >
            &gt; {t.label}
            {t.badge !== undefined && (
              <span
                style={{
                  marginLeft: 8,
                  padding: '2px 8px',
                  background: 'var(--px-bg-elevated)',
                  color: 'var(--px-teal)',
                  fontFamily: 'var(--px-mono)',
                  fontSize: '0.65rem',
                  fontWeight: 700,
                }}
              >
                {t.badge}
              </span>
            )}
          </button>
        ))}
      </div>

      {tab === 'registration' && <RegistrationPanel />}
      {tab === 'preferences' && <PreferencesPanel />}
      {tab === 'matching' && <MatchingPanel />}
      {tab === 'scores' && <ScoresPanel />}
    </main>
  );
}

export default function MatchingPage() {
  return (
    <RequireAuth roles={['admin']}>
      <Navbar />
      <MatchingContent />
    </RequireAuth>
  );
}
