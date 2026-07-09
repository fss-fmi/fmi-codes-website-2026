import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import DragRankSlots from '@/components/common/DragRankSlots';
import MentorCard from '@/components/mentors/MentorCard';
import Button from '@/components/common/Button';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import type { Mentor, Preference } from '@/types/mentor';

type Step = 'select' | 'rank' | 'done' | 'confirmed';

function ChooseMentorContent() {
  const { user } = useAuth();
  const teamId = user?.team_id;
  const isCaptain = user?.is_captain;
  const qc = useQueryClient();

  const [uiStep, setUiStep] = useState<'select' | 'rank'>('select');
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<Mentor[]>([]);
  const [ranked, setRanked] = useState<Preference[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const { data: matchingStatus } = useQuery<{ confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: prefData } = useQuery<{ preferences: Preference[] }>({
    queryKey: ['team-mentor-preferences', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/mentor-preferences`),
    enabled: !!teamId,
  });

  const serverPrefs = prefData?.preferences ?? [];
  const isConfirmed = matchingStatus?.confirmed ?? false;
  const step: Step = isConfirmed
    ? 'confirmed'
    : serverPrefs.length > 0 && !editing
      ? 'done'
      : uiStep;
  const submitted = serverPrefs;

  const { data: mentorsData, isLoading } = useQuery<{ mentors: Mentor[] }>({
    queryKey: ['available-mentors', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/available-mentors`),
    enabled: !!teamId && !!isCaptain && step === 'select',
  });

  const mentors = mentorsData?.mentors ?? [];

  function toggleMentor(m: Mentor) {
    setSelected((prev) => {
      if (prev.find((x) => x.mentor_id === m.mentor_id)) {
        return prev.filter((x) => x.mentor_id !== m.mentor_id);
      }
      if (prev.length >= 3) return prev;
      return [...prev, m];
    });
  }

  async function handleSubmit() {
    if (ranked.length < 3) return;
    setSubmitting(true);
    setError('');
    try {
      const data = await api.post<{ success: boolean; error?: string }>(
        `/api/teams/${teamId}/mentor-preferences`,
        { preferences: ranked },
      );
      if (data.success) {
        qc.setQueryData(['team-mentor-preferences', teamId], { preferences: ranked });
        setEditing(false);
      } else {
        setError(data.error ?? 'Failed to submit preferences.');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  if (!teamId) {
    return (
      <main style={{ padding: '100px 24px', maxWidth: 480, margin: '0 auto' }}>
        <Panel title="NO TEAM">
          <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: '0 0 20px 0' }}>
            &gt; You must be on a team first.
          </p>
          <Button variant="primary" href="/team">
            GO TO TEAM PAGE
          </Button>
        </Panel>
      </main>
    );
  }

  if (!isCaptain) {
    return (
      <main style={{ padding: '100px 24px', maxWidth: 480, margin: '0 auto' }}>
        <Panel title="ACCESS DENIED">
          <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
            &gt; Only the team captain can select mentors.
          </p>
        </Panel>
      </main>
    );
  }

  const RANK_LABELS = ['#1', '#2', '#3'];
  const stepLabel =
    step === 'select'
      ? `STEP 1 — SELECT 3 MENTORS (${selected.length}/3)`
      : step === 'rank'
        ? 'STEP 2 — DRAG TO RANK'
        : step === 'confirmed'
          ? 'MATCHING CONFIRMED'
          : 'PREFERENCES SUBMITTED';

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '960px', margin: '0 auto' }}>
      <PageHeader
        title="CHOOSE YOUR MENTORS"
        description="Select and rank 3 mentors in order of preference."
      />

      <div style={{ marginBottom: '24px' }}>
        <span className="px-status-chip">{stepLabel}</span>
      </div>

      {error && (
        <div
          role="alert"
          style={{
            background: 'var(--px-bg-panel)',
            border: '1px solid var(--px-danger)',
            borderLeft: '2px solid var(--px-danger)',
            color: 'var(--px-danger)',
            fontFamily: 'var(--px-mono)',
            fontSize: '0.85rem',
            padding: '12px 14px',
            marginBottom: '24px',
          }}
        >
          {error}
        </div>
      )}

      {step === 'confirmed' && (
        <Panel title="> MATCHING CONFIRMED">
          <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}>
            &gt; The admin has confirmed the matching results.
          </p>
          <Button variant="primary" href="/team">
            GO TO TEAM PAGE
          </Button>
        </Panel>
      )}

      {step === 'done' && (
        <Panel title="YOUR PREFERENCES">
          {[...submitted].sort((a, b) => a.rank - b.rank).map((p, i) => (
            <div
              key={p.mentor_id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 16,
                padding: '12px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
              }}
            >
              <span
                className="px-label"
                style={{
                  color: 'var(--px-teal)',
                  minWidth: 36,
                  textAlign: 'center',
                  fontSize: '0.6rem',
                }}
              >
                {RANK_LABELS[i]}
              </span>
              <span
                style={{
                  fontFamily: 'var(--px-mono)',
                  fontWeight: 700,
                  color: 'var(--px-white)',
                }}
              >
                {p.mentor_name ?? `Mentor #${p.mentor_id}`}
              </span>
            </div>
          ))}
          <div style={{ marginTop: 24, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="px-btn-secondary"
              onClick={() => {
                setEditing(true);
                setUiStep('select');
                setSelected(
                  [...submitted]
                    .sort((a, b) => a.rank - b.rank)
                    .map(
                      (p) =>
                        mentors.find((m) => m.mentor_id === p.mentor_id) ?? {
                          mentor_id: p.mentor_id,
                          name: p.mentor_name ?? `Mentor #${p.mentor_id}`,
                        },
                    ),
                );
              }}
            >
              CHANGE PREFERENCES
            </button>
            <Button variant="primary" href="/team">
              GO TO TEAM PAGE
            </Button>
          </div>
        </Panel>
      )}

      {step === 'select' && (
        <>
          {isLoading ? (
            <LoadingSpinner />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 20,
                marginBottom: 32,
              }}
            >
              {mentors.map((m) => {
                const isSelected = !!selected.find((x) => x.mentor_id === m.mentor_id);
                const disabled = !isSelected && selected.length >= 3;
                return (
                  <button
                    key={m.mentor_id}
                    type="button"
                    onClick={() => !disabled && toggleMentor(m)}
                    aria-pressed={isSelected}
                    disabled={disabled}
                    style={{
                      cursor: disabled ? 'not-allowed' : 'pointer',
                      border: isSelected
                        ? '2px solid var(--px-teal-strong)'
                        : '2px solid transparent',
                      background: 'transparent',
                      padding: 0,
                      textAlign: 'left',
                      opacity: disabled ? 0.4 : 1,
                      position: 'relative',
                      width: '100%',
                      display: 'block',
                    }}
                  >
                    {isSelected && (
                      <div
                        aria-hidden="true"
                        style={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
                          zIndex: 2,
                          width: 28,
                          height: 28,
                          background: 'var(--px-teal)',
                          color: 'var(--px-bg)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: 'var(--px-font)',
                          fontSize: '0.7rem',
                        }}
                      >
                        ✓
                      </div>
                    )}
                    <MentorCard mentor={m} />
                  </button>
                );
              })}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="primary"
              disabled={selected.length !== 3}
              onClick={() => {
                setRanked(selected.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
                setUiStep('rank');
              }}
            >
              NEXT: RANK MENTORS
            </Button>
          </div>
        </>
      )}

      {step === 'rank' && (
        <Panel title="RANK YOUR MENTORS">
          <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}>
            &gt; Drag or use Space + arrow keys to reorder. Top-ranked is your first choice.
          </p>
          <DragRankSlots
            mentors={selected}
            initialPreferences={ranked}
            onChange={setRanked}
          />
          <div style={{ display: 'flex', gap: 12, marginTop: 24, flexWrap: 'wrap' }}>
            <button
              type="button"
              className="px-btn-secondary"
              onClick={() => setUiStep('select')}
            >
              BACK
            </button>
            <Button
              variant="primary"
              disabled={ranked.length < 3 || submitting}
              onClick={handleSubmit}
            >
              {submitting ? 'SUBMITTING…' : 'SUBMIT PREFERENCES'}
            </Button>
          </div>
        </Panel>
      )}
    </main>
  );
}

export default function ChooseMentorPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <ChooseMentorContent />
    </RequireAuth>
  );
}
