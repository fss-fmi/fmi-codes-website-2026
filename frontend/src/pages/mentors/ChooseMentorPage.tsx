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
import SubmissionAccepted from '@/components/common/SubmissionAccepted';
import { useAuth } from '@/context/AuthContext';
import api from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { Mentor, Preference } from '@/types/mentor';
import type { Team } from '@/types/team';

type Step = 'select' | 'rank' | 'done' | 'confirmed';

export function ChooseMentorContent() {
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
  const [justSaved, setJustSaved] = useState<'submitted' | 'updated' | null>(null);

  const { data: matchingStatus, isLoading: statusLoading } = useQuery<{ confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  const { data: prefData, isLoading: prefsLoading } = useQuery<{ preferences: Preference[] }>({
    queryKey: ['team-mentor-preferences', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/mentor-preferences`),
    enabled: !!teamId,
  });

  // Same key as the team page, so coming from there costs no request.
  const { data: teamData, isError: teamIsError } = useQuery<{ team: Team }>({
    queryKey: ['team', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}`),
    enabled: !!teamId,
  });
  const registered = teamData?.team.is_registered;

  const serverPrefs = prefData?.preferences ?? [];
  const isConfirmed = matchingStatus?.confirmed ?? false;
  const step: Step = isConfirmed
    ? 'confirmed'
    : serverPrefs.length > 0 && !editing
      ? 'done'
      : uiStep;
  const isUpdate = serverPrefs.length > 0;
  const submitted = [...serverPrefs].sort((a, b) => a.rank - b.rank);

  const { data: mentorsData, isLoading } = useQuery<{ mentors: Mentor[] }>({
    queryKey: ['available-mentors', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/available-mentors`),
    enabled:
      !!teamId &&
      !!isCaptain &&
      !statusLoading &&
      !prefsLoading &&
      step === 'select' &&
      (registered === true || teamIsError),
  });

  const mentors = mentorsData?.mentors ?? [];
  // A saved pick that is no longer offered (the mentor was deactivated) has no
  // card to untick, so it is dropped instead of blocking the third slot.
  const picked = mentorsData
    ? selected.flatMap((s) => mentors.filter((m) => m.mentor_id === s.mentor_id))
    : selected;

  function toggleMentor(m: Mentor) {
    if (picked.some((x) => x.mentor_id === m.mentor_id)) {
      setSelected(picked.filter((x) => x.mentor_id !== m.mentor_id));
    } else if (picked.length < 3) {
      setSelected([...picked, m]);
    }
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
        qc.setQueryData<{ preferences: Preference[] }>(['team-mentor-preferences', teamId], {
          preferences: ranked.map((p) => ({
            ...p,
            mentor_name: selected.find((m) => m.mentor_id === p.mentor_id)?.name,
          })),
        });
        setJustSaved(isUpdate ? 'updated' : 'submitted');
        setEditing(false);
      } else {
        setError(data.error ?? 'Failed to submit preferences.');
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (!teamId) {
    return (
      <main style={{ padding: '100px 24px', maxWidth: 480, margin: '0 auto' }}>
        <Panel title="NO TEAM">
          <p
            className="px-body"
            style={{ color: 'var(--px-muted-strong)', margin: '0 0 20px 0' }}
          >
            &gt; You must be on a team first.
          </p>
          <Button
            variant="primary"
            href="/team"
          >
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
          <p
            className="px-body"
            style={{ color: 'var(--px-muted-strong)', margin: 0 }}
          >
            &gt; Only the team captain can select mentors.
          </p>
        </Panel>
      </main>
    );
  }

  // If the team can't be loaded, carry on: the server still refuses a ranking
  // from a team that isn't registered, and the form shows its error.
  if ((!teamData && !teamIsError) || statusLoading || prefsLoading) {
    return <LoadingSpinner fullPage />;
  }

  if (registered === false) {
    return (
      <main style={{ padding: '100px 24px', maxWidth: 480, margin: '0 auto' }}>
        <Panel title="NOT REGISTERED">
          <p
            className="px-body"
            style={{ color: 'var(--px-muted-strong)', margin: '0 0 20px 0' }}
          >
            &gt; Only registered teams take part in mentor matching. Your team can rank mentors once
            it holds one of the event slots.
          </p>
          <Button
            variant="primary"
            href="/team"
          >
            GO TO TEAM PAGE
          </Button>
        </Panel>
      </main>
    );
  }

  const stepLabel =
    step === 'select'
      ? `STEP 1 — SELECT 3 MENTORS (${picked.length}/3)`
      : step === 'rank'
        ? 'STEP 2 — DRAG TO RANK'
        : step === 'confirmed'
          ? 'MATCHING CONFIRMED'
          : 'SUBMISSION ACCEPTED';

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
          <p
            className="px-body"
            style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}
          >
            &gt; The admin has confirmed the matching results.
          </p>
          <Button
            variant="primary"
            href="/team"
          >
            GO TO TEAM PAGE
          </Button>
        </Panel>
      )}

      {step === 'done' && (
        <SubmissionAccepted
          ranking={submitted.map((p) => ({
            id: p.mentor_id,
            name: p.mentor_name ?? `Mentor #${p.mentor_id}`,
          }))}
          justSaved={justSaved}
          onUpdate={() => {
            setEditing(true);
            setUiStep('select');
            setError('');
            setJustSaved(null);
            setSelected(
              submitted.map((p) => ({
                mentor_id: p.mentor_id,
                name: p.mentor_name ?? `Mentor #${p.mentor_id}`,
              })),
            );
          }}
        >
          <Button
            variant="primary"
            href="/team"
          >
            GO TO TEAM PAGE
          </Button>
        </SubmissionAccepted>
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
                const isSelected = picked.some((x) => x.mentor_id === m.mentor_id);
                const disabled = !isSelected && picked.length >= 3;
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
                setRanked(picked.map((m, i) => ({ mentor_id: m.mentor_id, rank: i + 1 })));
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
          <p
            className="px-body-sm"
            style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}
          >
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

export default function ChooseMentorPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <ChooseMentorContent />
    </RequireAuth>
  );
}
