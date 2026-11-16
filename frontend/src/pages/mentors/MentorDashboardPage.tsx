import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import PageHeader from '@/components/layout/PageHeader';
import Panel from '@/components/common/Panel';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import Button from '@/components/common/Button';
import SubmissionAccepted from '@/components/common/SubmissionAccepted';
import api from '@/lib/api';
import { errorMessage } from '@/lib/errors';

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

function SortableTeamRow({ team, rank }: { team: TeamItem; rank: number }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: String(team.team_id),
  });
  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '14px 16px',
        background: isDragging ? 'var(--px-bg-elevated)' : 'var(--px-bg-card)',
        border: isDragging ? '2px solid var(--px-teal-strong)' : '1px solid var(--px-teal-dim)',
        cursor: 'grab',
        userSelect: 'none',
      }}
      {...attributes}
      {...listeners}
    >
      <span
        className="px-label"
        style={{
          color: 'var(--px-teal)',
          minWidth: 32,
          textAlign: 'center',
          fontSize: '0.65rem',
        }}
      >
        #{rank}
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
          {team.team_name}
        </div>
        <div
          className="px-body-sm"
          style={{ color: 'var(--px-muted-strong)' }}
        >
          {team.participant_count} members
        </div>
      </div>
      <span
        aria-hidden="true"
        style={{
          color: 'var(--px-muted-strong)',
          fontFamily: 'var(--px-font)',
          fontSize: '0.65rem',
        }}
      >
        ⠿
      </span>
    </div>
  );
}

export function MentorDashboardContent() {
  const qc = useQueryClient();
  const [uiStep, setUiStep] = useState<'select' | 'rank'>('select');
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<TeamItem[]>([]);
  const [ranked, setRanked] = useState<TeamItem[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [justSaved, setJustSaved] = useState<'submitted' | 'updated' | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const { data: matchingStatus, isLoading: statusLoading } = useQuery<{ confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: prefData, isLoading: prefsLoading } = useQuery<{ preferences: TeamPref[] }>({
    queryKey: ['mentor-team-preferences'],
    queryFn: () => api.get('/api/mentors/team-preferences'),
    enabled: !matchingStatus?.confirmed,
  });

  const { data: assignedData } = useQuery<{ teams: TeamItem[] }>({
    queryKey: ['mentor-assigned-teams'],
    queryFn: () => api.get('/api/mentors/assigned-teams'),
    enabled: matchingStatus?.confirmed ?? false,
  });

  const serverPrefs = prefData?.preferences ?? [];
  const assigned = assignedData?.teams ?? [];
  const isConfirmed = matchingStatus?.confirmed ?? false;
  const step: Step = isConfirmed
    ? 'assigned'
    : serverPrefs.length > 0 && !editing
      ? 'done'
      : uiStep;
  const isUpdate = serverPrefs.length > 0;
  const submitted = [...serverPrefs].sort((a, b) => a.rank - b.rank);

  const { data: teamsData, isLoading: teamsLoading } = useQuery<{ teams: TeamItem[] }>({
    queryKey: ['mentor-available-teams'],
    queryFn: () => api.get('/api/mentors/available-teams'),
    enabled: !statusLoading && !prefsLoading && step === 'select' && !isConfirmed,
  });

  const teams = teamsData?.teams ?? [];
  // A saved pick that is no longer offered (its team was unregistered) has no
  // card to untick, so it is dropped instead of blocking the third slot.
  const picked = teamsData
    ? selected.flatMap((s) => teams.filter((t) => t.team_id === s.team_id))
    : selected;

  function toggleTeam(t: TeamItem) {
    setError('');
    if (picked.some((x) => x.team_id === t.team_id)) {
      setSelected(picked.filter((x) => x.team_id !== t.team_id));
    } else if (picked.length < 3) {
      setSelected([...picked, t]);
    }
  }

  async function handleSubmit() {
    if (ranked.length !== 3) return;
    const prefs = ranked.map((t, i) => ({ team_id: t.team_id, rank: i + 1 }));
    setSubmitting(true);
    setError('');
    try {
      const data = await api.post<{ success: boolean; error?: string }>(
        '/api/mentors/team-preferences',
        { preferences: prefs },
      );
      if (data.success) {
        qc.setQueryData<{ preferences: TeamPref[] }>(['mentor-team-preferences'], {
          preferences: ranked.map((t, i) => ({
            team_id: t.team_id,
            rank: i + 1,
            team_name: t.team_name,
          })),
        });
        setJustSaved(isUpdate ? 'updated' : 'submitted');
        setEditing(false);
      } else {
        setError(data.error ?? 'Failed to submit.');
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setRanked((prev) => {
      const oldIndex = prev.findIndex((t) => String(t.team_id) === active.id);
      const newIndex = prev.findIndex((t) => String(t.team_id) === over.id);
      return arrayMove(prev, oldIndex, newIndex);
    });
  }

  if (statusLoading || prefsLoading) return <LoadingSpinner fullPage />;

  const stepLabel =
    step === 'select'
      ? `STEP 1 — SELECT 3 TEAMS (${picked.length}/3)`
      : step === 'rank'
        ? 'STEP 2 — DRAG TO RANK'
        : step === 'assigned'
          ? 'ASSIGNMENTS CONFIRMED'
          : 'SUBMISSION ACCEPTED';

  return (
    <main style={{ padding: '80px 24px 80px', maxWidth: '960px', margin: '0 auto' }}>
      <PageHeader
        title="MENTOR DASHBOARD"
        description="Select and rank the teams you'd prefer to mentor."
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

      {step === 'assigned' && (
        <Panel title="ASSIGNED TEAMS">
          {assigned.length === 0 ? (
            <p
              className="px-body"
              style={{ color: 'var(--px-muted-strong)', margin: 0 }}
            >
              &gt; No teams assigned.
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
                  borderBottom: '1px solid var(--px-teal-dim)',
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 8,
                    height: 8,
                    background: 'var(--px-teal)',
                    flexShrink: 0,
                  }}
                />
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--px-mono)',
                      fontWeight: 700,
                      color: 'var(--px-white)',
                    }}
                  >
                    {t.team_name}
                  </div>
                  <div
                    className="px-body-sm"
                    style={{ color: 'var(--px-muted-strong)' }}
                  >
                    {t.participant_count} members
                  </div>
                </div>
              </div>
            ))
          )}
        </Panel>
      )}

      {step === 'done' && (
        <SubmissionAccepted
          ranking={submitted.map((p) => ({
            id: p.team_id,
            name: p.team_name ?? `Team #${p.team_id}`,
          }))}
          justSaved={justSaved}
          onUpdate={() => {
            setEditing(true);
            setUiStep('select');
            setError('');
            setJustSaved(null);
            setSelected(
              submitted.map((p) => ({
                team_id: p.team_id,
                team_name: p.team_name ?? `Team #${p.team_id}`,
                participant_count: 0,
              })),
            );
          }}
        />
      )}

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
                    gridColumn: '1 / -1',
                    padding: 40,
                  }}
                >
                  <p
                    className="px-body"
                    style={{ color: 'var(--px-muted-strong)', textAlign: 'center', margin: 0 }}
                  >
                    &gt; No active teams available.
                  </p>
                </div>
              )}
              {teams.map((t) => {
                const isSelected = picked.some((x) => x.team_id === t.team_id);
                const disabled = !isSelected && picked.length >= 3;
                return (
                  <button
                    key={t.team_id}
                    type="button"
                    onClick={() => !disabled && toggleTeam(t)}
                    aria-pressed={isSelected}
                    disabled={disabled}
                    style={{
                      cursor: disabled ? 'not-allowed' : 'pointer',
                      padding: '20px',
                      background: isSelected ? 'var(--px-bg-elevated)' : 'var(--px-bg-card)',
                      border: isSelected
                        ? '2px solid var(--px-teal-strong)'
                        : '1px solid var(--px-teal-dim)',
                      opacity: disabled ? 0.4 : 1,
                      textAlign: 'left',
                      color: 'var(--px-white)',
                      position: 'relative',
                    }}
                  >
                    {isSelected && (
                      <div
                        aria-hidden="true"
                        style={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
                          width: 24,
                          height: 24,
                          background: 'var(--px-teal)',
                          color: 'var(--px-bg)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontFamily: 'var(--px-font)',
                          fontSize: '0.65rem',
                        }}
                      >
                        ✓
                      </div>
                    )}
                    <div
                      style={{
                        fontFamily: 'var(--px-mono)',
                        fontWeight: 700,
                        fontSize: '0.95rem',
                        marginBottom: 6,
                      }}
                    >
                      {t.team_name}
                    </div>
                    <div
                      className="px-body-sm"
                      style={{ color: 'var(--px-muted-strong)' }}
                    >
                      {t.participant_count}/6 members
                    </div>
                  </button>
                );
              })}
            </div>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
            {editing && (
              <button
                type="button"
                className="px-btn-secondary"
                onClick={() => {
                  setEditing(false);
                  setError('');
                }}
              >
                CANCEL
              </button>
            )}
            <Button
              variant="primary"
              disabled={picked.length !== 3}
              onClick={() => {
                setSelected(picked);
                setRanked(picked);
                setUiStep('rank');
              }}
            >
              NEXT: RANK TEAMS
            </Button>
          </div>
        </>
      )}

      {step === 'rank' && (
        <Panel title="RANK YOUR TEAMS">
          <p
            className="px-body-sm"
            style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}
          >
            &gt; Drag or use Space + arrow keys to reorder your team preferences.
          </p>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={ranked.map((t) => String(t.team_id))}
              strategy={verticalListSortingStrategy}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {ranked.map((t, i) => (
                  <SortableTeamRow
                    key={t.team_id}
                    team={t}
                    rank={i + 1}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
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
              disabled={ranked.length !== 3 || submitting}
              onClick={handleSubmit}
            >
              {submitting
                ? isUpdate
                  ? 'UPDATING…'
                  : 'SUBMITTING…'
                : isUpdate
                  ? 'UPDATE PREFERENCES'
                  : 'SUBMIT PREFERENCES'}
            </Button>
          </div>
        </Panel>
      )}
    </main>
  );
}

export default function MentorDashboardPage() {
  return (
    <RequireAuth roles={['mentor']}>
      <Navbar />
      <MentorDashboardContent />
    </RequireAuth>
  );
}
