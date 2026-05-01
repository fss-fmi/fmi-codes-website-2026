import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import DragRankSlots from '@/components/common/DragRankSlots';
import MentorCard from '@/components/mentors/MentorCard';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import type { Mentor, Preference } from '@/types/mentor';

type Step = 'select' | 'rank' | 'done' | 'confirmed';

function ChooseMentorContent() {
  const { user } = useAuth();
  const teamId = user?.team_id;
  const isCaptain = user?.is_captain;
  const qc = useQueryClient();

  // UI-only step state (select ↔ rank). 'done'/'confirmed' are derived from server.
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

  // Derive step and submitted from server data (no useEffect needed)
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
      <main style={{ padding: '100px 24px', textAlign: 'center' }}>
        <GlassCard style={{ maxWidth: 400, margin: '0 auto', padding: 32 }}>
          <p style={{ color: 'var(--muted)', marginBottom: 20 }}>You must be on a team first.</p>
          <Link
            to="/team"
            className="btn btn-primary"
          >
            Go to Team Page
          </Link>
        </GlassCard>
      </main>
    );
  }

  if (!isCaptain) {
    return (
      <main style={{ padding: '100px 24px', textAlign: 'center' }}>
        <GlassCard style={{ maxWidth: 400, margin: '0 auto', padding: 32 }}>
          <p style={{ color: 'var(--muted)' }}>Only the team captain can select mentors.</p>
        </GlassCard>
      </main>
    );
  }

  const RANK_LABELS = ['1st', '2nd', '3rd'];

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
      <PageHeader
        eyebrow="Mentors"
        title="Choose Your Mentors"
        subtitle="Select and rank 3 mentors in order of preference."
      />

      {/* Step badge */}
      <div style={{ marginBottom: '24px' }}>
        <span
          style={{
            padding: '6px 16px',
            borderRadius: '999px',
            fontSize: '13px',
            fontWeight: 700,
            ...(step === 'select'
              ? {
                  background: 'rgba(96,165,250,0.15)',
                  color: '#60a5fa',
                  border: '1px solid rgba(96,165,250,0.3)',
                }
              : step === 'rank'
                ? {
                    background: 'rgba(167,139,250,0.15)',
                    color: '#a78bfa',
                    border: '1px solid rgba(167,139,250,0.3)',
                  }
                : {
                    background: 'rgba(52,211,153,0.15)',
                    color: '#34d399',
                    border: '1px solid rgba(52,211,153,0.3)',
                  }),
          }}
        >
          {step === 'select'
            ? `Step 1 — Select 3 mentors (${selected.length}/3)`
            : step === 'rank'
              ? 'Step 2 — Drag to rank'
              : step === 'confirmed'
                ? '✅ Assignments confirmed'
                : '✓ Preferences Submitted'}
        </span>
      </div>

      {error && (
        <div
          style={{
            background: 'rgba(239,68,68,0.15)',
            border: '1px solid rgba(239,68,68,0.3)',
            color: '#fca5a5',
            padding: '14px',
            borderRadius: '10px',
            marginBottom: '24px',
            fontSize: '14px',
          }}
        >
          {error}
        </div>
      )}

      {/* Confirmed state */}
      {step === 'confirmed' && (
        <GlassCard style={{ padding: 32, textAlign: 'center' }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>✅</div>
          <h2 style={{ fontWeight: 800, marginBottom: 8 }}>Matching Confirmed</h2>
          <p style={{ color: 'var(--muted)', marginBottom: 24 }}>
            The admin has confirmed the matching results.
          </p>
          <Link
            to="/team"
            className="btn btn-primary"
          >
            Go to Team Page
          </Link>
        </GlassCard>
      )}

      {/* Done state — submitted prefs */}
      {step === 'done' && (
        <GlassCard style={{ padding: 32 }}>
          <h3 style={{ fontWeight: 800, fontSize: 20, marginBottom: 20 }}>Your Preferences</h3>
          {submitted
            .sort((a, b) => a.rank - b.rank)
            .map((p, i) => (
              <div
                key={p.mentor_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  padding: '12px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <span
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 800,
                    color: '#0b1021',
                    fontSize: 14,
                  }}
                >
                  {RANK_LABELS[i]}
                </span>
                <span style={{ fontWeight: 700 }}>
                  {(p as Preference & { mentor_name?: string }).mentor_name ??
                    `Mentor #${p.mentor_id}`}
                </span>
              </div>
            ))}
          <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
            <button
              className="btn"
              onClick={() => {
                setEditing(true);
                setUiStep('select');
                setSelected([]);
              }}
            >
              Change Preferences
            </button>
            <Link
              to="/team"
              className="btn btn-primary"
              style={{ textDecoration: 'none' }}
            >
              Go to Team Page →
            </Link>
          </div>
        </GlassCard>
      )}

      {/* Select step */}
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
                return (
                  <div
                    key={m.mentor_id}
                    onClick={() => toggleMentor(m)}
                    style={{
                      cursor: 'pointer',
                      borderRadius: 16,
                      outline: isSelected ? '2px solid #60a5fa' : 'none',
                      opacity: !isSelected && selected.length >= 3 ? 0.4 : 1,
                      transition: 'all 0.2s',
                      position: 'relative',
                    }}
                  >
                    {isSelected && (
                      <div
                        style={{
                          position: 'absolute',
                          top: 12,
                          right: 12,
                          zIndex: 2,
                          width: 28,
                          height: 28,
                          borderRadius: '50%',
                          background: '#60a5fa',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 900,
                          color: '#0b1021',
                          fontSize: 16,
                        }}
                      >
                        ✓
                      </div>
                    )}
                    <MentorCard mentor={m} />
                  </div>
                );
              })}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <button
              className="btn btn-primary"
              disabled={selected.length !== 3}
              onClick={() => {
                setRanked(selected.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
                setUiStep('rank');
              }}
            >
              Next: Rank Mentors →
            </button>
          </div>
        </>
      )}

      {/* Rank step */}
      {step === 'rank' && (
        <GlassCard style={{ padding: 32 }}>
          <p style={{ color: 'var(--muted)', marginBottom: 24, fontSize: 14 }}>
            Drag to reorder your preferences. The top-ranked mentor is your first choice.
          </p>
          <DragRankSlots
            mentors={selected}
            initialPreferences={ranked}
            onChange={setRanked}
          />
          <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
            <button
              className="btn"
              onClick={() => setUiStep('select')}
            >
              ← Back
            </button>
            <button
              className="btn btn-primary"
              disabled={ranked.length < 3 || submitting}
              onClick={handleSubmit}
            >
              {submitting ? 'Submitting...' : 'Submit Preferences'}
            </button>
          </div>
        </GlassCard>
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
