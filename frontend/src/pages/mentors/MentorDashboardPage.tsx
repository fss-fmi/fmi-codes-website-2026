import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import api from '@/lib/api';

interface TeamItem {
  team_id: number;
  team_name: string;
  participant_count: number;
}

interface TeamPref {
  team_id: number;
  rank: number;
  team_name?: string;
}

type Step = 'select' | 'rank' | 'done' | 'assigned';

const RANK_LABELS = ['1st', '2nd', '3rd'];
const RANK_COLORS = ['#60a5fa', '#a78bfa', '#f472b6'];

function MentorDashboardContent() {
  // UI-only step state (select ↔ rank). 'done'/'assigned' derived from server.
  const [uiStep, setUiStep] = useState<'select' | 'rank'>('select');
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<TeamItem[]>([]);
  const [ranked, setRanked] = useState<TeamItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [dragOver, setDragOver] = useState<number | null>(null);

  const { data: matchingStatus, isLoading: statusLoading } = useQuery<{ confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: prefData } = useQuery<{ preferences: TeamPref[] }>({
    queryKey: ['mentor-team-preferences'],
    queryFn: () => api.get('/api/mentors/team-preferences'),
    enabled: !matchingStatus?.confirmed,
  });

  const { data: assignedData } = useQuery<{ teams: TeamItem[] }>({
    queryKey: ['mentor-assigned-teams'],
    queryFn: () => api.get('/api/mentors/assigned-teams'),
    enabled: matchingStatus?.confirmed ?? false,
  });

  // Derive step and submitted from server data (no useEffect needed)
  const serverPrefs = prefData?.preferences ?? [];
  const assigned = assignedData?.teams ?? [];
  const isConfirmed = matchingStatus?.confirmed ?? false;
  const step: Step = isConfirmed
    ? 'assigned'
    : serverPrefs.length > 0 && !editing
      ? 'done'
      : uiStep;
  const submitted = serverPrefs;

  const { data: teamsData, isLoading: teamsLoading } = useQuery<{ teams: TeamItem[] }>({
    queryKey: ['mentor-available-teams'],
    queryFn: () => api.get('/api/mentors/available-teams'),
    enabled: step === 'select' && !matchingStatus?.confirmed,
  });

  const teams = teamsData?.teams ?? [];

  function toggleTeam(t: TeamItem) {
    setSelected((prev) => {
      if (prev.find((x) => x.team_id === t.team_id))
        return prev.filter((x) => x.team_id !== t.team_id);
      if (prev.length >= 3) {
        setError('Select exactly 3 teams.');
        return prev;
      }
      return [...prev, t];
    });
    setError('');
  }

  async function handleSubmit() {
    const prefs = ranked.map((t, i) => ({ team_id: t.team_id, rank: i + 1 }));
    setSubmitting(true);
    setError('');
    try {
      const data = await api.post<{ success: boolean; error?: string }>(
        '/api/mentors/team-preferences',
        { preferences: prefs },
      );
      if (data.success) {
        setEditing(false);
      } else {
        setError(data.error ?? 'Failed to submit.');
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  // Drag-and-drop for ranked slots
  function handleDragStart(e: React.DragEvent, teamId: number) {
    e.dataTransfer.setData('text/plain', String(teamId));
    e.dataTransfer.effectAllowed = 'move';
  }

  function handleDrop(e: React.DragEvent, targetIndex: number) {
    e.preventDefault();
    setDragOver(null);
    const draggedId = parseInt(e.dataTransfer.getData('text/plain'));
    const sourceIndex = ranked.findIndex((t) => t.team_id === draggedId);
    if (sourceIndex === -1 || sourceIndex === targetIndex) return;
    const next = [...ranked];
    const [item] = next.splice(sourceIndex, 1);
    next.splice(targetIndex, 0, item);
    setRanked(next);
  }

  if (statusLoading) return <LoadingSpinner fullPage />;

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '900px', margin: '0 auto' }}>
      <PageHeader
        eyebrow="Mentor"
        title="Mentor Dashboard"
        subtitle="Select and rank the teams you'd prefer to mentor."
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
            ? `Step 1 — Select 3 teams (${selected.length}/3)`
            : step === 'rank'
              ? 'Step 2 — Drag to rank'
              : step === 'assigned'
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

      {/* Assigned teams state */}
      {step === 'assigned' && (
        <GlassCard style={{ padding: 32 }}>
          <h3 style={{ fontWeight: 800, fontSize: 20, marginBottom: 20 }}>Your Assigned Teams</h3>
          {assigned.length === 0 ? (
            <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '24px 0' }}>
              No teams assigned.
            </p>
          ) : (
            assigned.map((t) => (
              <div
                key={t.team_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  padding: '14px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.06)',
                }}
              >
                <span style={{ fontSize: 28 }}>🎯</span>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 16 }}>{t.team_name}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 13, fontWeight: 600 }}>
                    {t.participant_count} members
                  </div>
                </div>
              </div>
            ))
          )}
        </GlassCard>
      )}

      {/* Done state */}
      {step === 'done' && (
        <GlassCard style={{ padding: 32 }}>
          <h3 style={{ fontWeight: 800, fontSize: 20, marginBottom: 20 }}>Your Preferences</h3>
          {[...submitted]
            .sort((a, b) => a.rank - b.rank)
            .map((p, i) => (
              <div
                key={p.team_id}
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
                    background: `linear-gradient(135deg, ${RANK_COLORS[i]}, ${RANK_COLORS[(i + 1) % 3]})`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 800,
                    color: '#0b1021',
                    fontSize: 13,
                  }}
                >
                  {RANK_LABELS[i]}
                </span>
                <span style={{ fontWeight: 700 }}>{p.team_name ?? `Team #${p.team_id}`}</span>
              </div>
            ))}
          <button
            className="btn"
            style={{ marginTop: 24 }}
            onClick={() => {
              setEditing(true);
              setUiStep('select');
              setSelected([]);
            }}
          >
            Change Preferences
          </button>
        </GlassCard>
      )}

      {/* Select teams */}
      {step === 'select' && (
        <>
          {teamsLoading ? (
            <LoadingSpinner />
          ) : (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
                gap: 16,
                marginBottom: 24,
              }}
            >
              {teams.length === 0 && (
                <div
                  style={{
                    color: 'var(--muted)',
                    textAlign: 'center',
                    gridColumn: '1/-1',
                    padding: 40,
                  }}
                >
                  No active teams available.
                </div>
              )}
              {teams.map((t) => {
                const isSelected = !!selected.find((x) => x.team_id === t.team_id);
                return (
                  <div
                    key={t.team_id}
                    onClick={() => toggleTeam(t)}
                    style={{
                      cursor: 'pointer',
                      borderRadius: 14,
                      padding: '20px',
                      background: isSelected ? 'rgba(96,165,250,0.1)' : 'rgba(255,255,255,0.03)',
                      border: isSelected
                        ? '1px solid rgba(96,165,250,0.4)'
                        : '1px solid rgba(255,255,255,0.08)',
                      opacity: !isSelected && selected.length >= 3 ? 0.4 : 1,
                      transition: 'all 0.2s',
                      position: 'relative',
                    }}
                  >
                    {isSelected && (
                      <div
                        style={{
                          position: 'absolute',
                          top: 10,
                          right: 10,
                          width: 24,
                          height: 24,
                          borderRadius: '50%',
                          background: '#60a5fa',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 900,
                          color: '#0b1021',
                          fontSize: 14,
                        }}
                      >
                        ✓
                      </div>
                    )}
                    <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 6 }}>
                      {t.team_name}
                    </div>
                    <div style={{ color: 'var(--muted)', fontSize: 13 }}>
                      {t.participant_count}/6 members
                    </div>
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
                setRanked([...selected]);
                setUiStep('rank');
              }}
            >
              Next: Rank Teams →
            </button>
          </div>
        </>
      )}

      {/* Rank teams */}
      {step === 'rank' && (
        <GlassCard style={{ padding: 32 }}>
          <p style={{ color: 'var(--muted)', marginBottom: 24, fontSize: 14 }}>
            Drag teams between slots to reorder preferences.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {ranked.map((t, i) => (
              <div
                key={t.team_id}
                draggable
                onDragStart={(e) => handleDragStart(e, t.team_id)}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(i);
                }}
                onDragLeave={() => setDragOver(null)}
                onDrop={(e) => handleDrop(e, i)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 16,
                  padding: '14px 16px',
                  borderRadius: 10,
                  cursor: 'grab',
                  userSelect: 'none',
                  background: dragOver === i ? 'rgba(96,165,250,0.1)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${dragOver === i ? 'rgba(96,165,250,0.4)' : 'rgba(255,255,255,0.08)'}`,
                  transition: 'all 0.2s',
                }}
              >
                <span
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    background: `linear-gradient(135deg, ${RANK_COLORS[i]}, ${RANK_COLORS[(i + 1) % 3]})`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 800,
                    color: '#0b1021',
                    fontSize: 13,
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700 }}>{t.team_name}</div>
                  <div style={{ color: 'var(--muted)', fontSize: 13 }}>
                    {t.participant_count} members
                  </div>
                </div>
                <span style={{ color: 'var(--muted)', fontSize: 18 }}>⠿</span>
              </div>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 24 }}>
            <button
              className="btn"
              onClick={() => setUiStep('select')}
            >
              ← Back
            </button>
            <button
              className="btn btn-primary"
              disabled={submitting}
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

export default function MentorDashboardPage() {
  return (
    <RequireAuth allowedRole="mentor">
      <Navbar />
      <MentorDashboardContent />
    </RequireAuth>
  );
}
