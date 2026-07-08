import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import Panel from '@/components/common/Panel';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import StatusBadge from '@/components/common/StatusBadge';
import MemberBar from '@/components/common/MemberBar';
import Button from '@/components/common/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useToast } from '@/components/common/useToast';
import type { User } from '@/types/auth';
import api from '@/lib/api';
import type { Team, JoinRequest, Application } from '@/types/team';

interface MentorPref {
  mentor_id: number;
  rank: number;
  mentor_name?: string;
}

interface DialogState {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  dangerous?: boolean;
  onConfirm: () => void;
}

const CLOSED_DIALOG: DialogState = {
  open: false,
  title: '',
  onConfirm: () => {},
};

function NoTeamView() {
  const { showToast } = useToast();
  const [dialog, setDialog] = useState<DialogState>(CLOSED_DIALOG);

  const { data: appsData, refetch } = useQuery<{ applications: Application[] }>({
    queryKey: ['my-applications'],
    queryFn: () => api.get('/api/teams/my-applications'),
  });

  function requestWithdraw(requestId: number) {
    setDialog({
      open: true,
      title: 'WITHDRAW APPLICATION',
      description: 'Withdraw this application?',
      confirmLabel: 'WITHDRAW',
      dangerous: true,
      onConfirm: async () => {
        setDialog(CLOSED_DIALOG);
        const d = await api.post<{ success: boolean; error?: string }>(
          `/api/teams/requests/${requestId}/cancel`,
          {},
        );
        if (d.success) {
          showToast({ kind: 'success', message: 'Application withdrawn.' });
          refetch();
        } else {
          showToast({ kind: 'danger', message: d.error ?? 'Failed.' });
        }
      },
    });
  }

  const apps = appsData?.applications ?? [];

  return (
    <div style={{ padding: '100px 24px', maxWidth: 640, margin: '0 auto' }}>
      <Panel title="NO TEAM YET" style={{ marginBottom: '24px' }}>
        <p className="px-body" style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}>
          Assemble a team of up to 6 to compete in FMI Codes 2026. Create your own, join a team with an invite code, or browse open teams.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Button variant="primary" href="/createTeam">
            CREATE TEAM
          </Button>
          <Button variant="secondary" href="/joinTeam">
            JOIN WITH CODE
          </Button>
          <Button variant="secondary" href="/browseTeams">
            BROWSE TEAMS
          </Button>
        </div>
      </Panel>

      {apps.length > 0 && (
        <Panel title="MY APPLICATIONS">
          <div>
            {apps.map((a) => (
              <div
                key={a.request_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '12px 0',
                  borderBottom: '1px solid var(--px-teal-dim)',
                  flexWrap: 'wrap',
                }}
              >
                <div style={{ flex: 1, minWidth: '200px' }}>
                  <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
                    {a.team_name}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                    <StatusBadge variant={a.status as 'pending' | 'accepted' | 'declined'} />
                    <span
                      role="status"
                      style={{ color: 'var(--px-muted-strong)', fontFamily: 'var(--px-mono)', fontSize: '0.8rem' }}
                    >
                      {a.participant_count}/6 members
                    </span>
                  </div>
                </div>
                {a.status === 'pending' && (
                  <button
                    type="button"
                    className="px-btn-danger"
                    onClick={() => requestWithdraw(a.request_id)}
                    style={{ padding: '10px 16px', fontSize: '0.55rem' }}
                  >
                    WITHDRAW
                  </button>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      <ConfirmDialog
        open={dialog.open}
        title={dialog.title}
        description={dialog.description}
        confirmLabel={dialog.confirmLabel}
        dangerous={dialog.dangerous}
        onConfirm={dialog.onConfirm}
        onCancel={() => setDialog(CLOSED_DIALOG)}
      />
    </div>
  );
}

function TeamDashboardView({
  team,
  userId,
  onRefresh,
}: {
  team: Team;
  userId: number;
  onRefresh: () => void;
}) {
  const { showToast } = useToast();
  const isCaptain = String(team.captain_id) === String(userId);
  const teamId = team.id ?? team.team_id!;
  const [dialog, setDialog] = useState<DialogState>(CLOSED_DIALOG);

  const { data: reqData, refetch: refetchReqs } = useQuery<{ requests: JoinRequest[] }>({
    queryKey: ['join-requests', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/requests`),
    enabled: isCaptain,
  });

  const { data: prefData } = useQuery<{ preferences: MentorPref[] }>({
    queryKey: ['team-mentor-preferences', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}/mentor-preferences`),
    enabled: team.status === 'active',
  });

  const { data: statusData } = useQuery<{ confirmed: boolean }>({
    queryKey: ['matching-status'],
    queryFn: () => api.get('/api/matching-status'),
  });

  function askRemoveMember(mid: number) {
    setDialog({
      open: true,
      title: 'REMOVE MEMBER',
      description: 'Remove this member from the team?',
      confirmLabel: 'REMOVE',
      dangerous: true,
      onConfirm: async () => {
        setDialog(CLOSED_DIALOG);
        const d = await api.delete<{ success: boolean; error?: string }>(
          `/api/teams/${teamId}/members/${mid}`,
        );
        if (d.success) {
          showToast({ kind: 'success', message: 'Member removed.' });
          onRefresh();
        } else {
          showToast({ kind: 'danger', message: d.error ?? 'Failed.' });
        }
      },
    });
  }

  function askLeave() {
    setDialog({
      open: true,
      title: 'LEAVE TEAM',
      description: 'Are you sure you want to leave this team?',
      confirmLabel: 'LEAVE',
      dangerous: true,
      onConfirm: async () => {
        setDialog(CLOSED_DIALOG);
        const d = await api.post<{ success: boolean; error?: string }>(
          `/api/teams/${teamId}/leave`,
          {},
        );
        if (d.success) onRefresh();
        else showToast({ kind: 'danger', message: d.error ?? 'Failed.' });
      },
    });
  }

  function askDisband() {
    setDialog({
      open: true,
      title: 'DISBAND TEAM',
      description:
        'Are you absolutely sure? All members will be removed and the team will be permanently deleted. This cannot be undone.',
      confirmLabel: 'DISBAND',
      dangerous: true,
      onConfirm: async () => {
        setDialog(CLOSED_DIALOG);
        const d = await api.delete<{ success: boolean; error?: string }>(
          `/api/teams/${teamId}`,
        );
        if (d.success) onRefresh();
        else showToast({ kind: 'danger', message: d.error ?? 'Failed.' });
      },
    });
  }

  async function handleRequest(reqId: number, action: 'accept' | 'decline') {
    const d = await api.post<{ success: boolean; error?: string }>(
      `/api/teams/requests/${reqId}/${action}`,
      {},
    );
    if (d.success) {
      showToast({
        kind: action === 'accept' ? 'success' : 'info',
        message: action === 'accept' ? 'Accepted.' : 'Declined.',
      });
      refetchReqs();
      onRefresh();
    } else {
      showToast({ kind: 'danger', message: d.error ?? 'Failed.' });
    }
  }

  const requests = reqData?.requests ?? [];
  const confirmed = statusData?.confirmed;
  const rawPrefs = prefData?.preferences ?? [];
  const prefs: MentorPref[] = [...rawPrefs].sort((a, b) => a.rank - b.rank);
  const count = team.participant_count ?? team.members?.length ?? 0;

  return (
    <div style={{ padding: '80px 24px 80px', maxWidth: 820, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1
          className="px-page-title"
          style={{ margin: '0 0 12px 0' }}
        >
          {team.team_name}
        </h1>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            flexWrap: 'wrap',
            marginBottom: 12,
          }}
        >
          <StatusBadge variant={(team.status ?? 'inactive') as 'active' | 'inactive' | 'queued' | 'registered'} />
          {team.is_registered && <StatusBadge variant="registered" />}
          {team.queue_position && <StatusBadge variant="queued" />}
        </div>
        {team.status !== 'active' && (
          <div
            role="status"
            style={{
              background: 'var(--px-bg-panel)',
              border: '1px solid var(--px-amber)',
              borderLeft: '2px solid var(--px-amber)',
              color: 'var(--px-amber)',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.85rem',
              padding: '10px 14px',
              marginBottom: 12,
            }}
          >
            &gt; Your team needs at least 3 members to be eligible for the hackathon.
          </div>
        )}
        {team.is_registered && (
          <div
            role="status"
            style={{
              background: 'var(--px-bg-panel)',
              border: '1px solid var(--px-green)',
              borderLeft: '2px solid var(--px-green)',
              color: 'var(--px-green)',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.85rem',
              padding: '10px 14px',
              marginBottom: 12,
            }}
          >
            &gt; Your team is registered for the hackathon.
          </div>
        )}
        {!team.is_registered && team.queue_position && (
          <div
            role="status"
            style={{
              background: 'var(--px-bg-panel)',
              border: '1px solid var(--px-amber)',
              borderLeft: '2px solid var(--px-amber)',
              color: 'var(--px-amber)',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.85rem',
              padding: '10px 14px',
              marginBottom: 12,
            }}
          >
            &gt; In the waiting queue at position #{team.queue_position}. You'll be registered
            automatically when a slot opens.
          </div>
        )}
        <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
          {count}/6 members
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {isCaptain && team.join_code && (
          <Panel title="JOIN CODE">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
              <span className="px-label">CODE</span>
              <code
                style={{
                  fontFamily: 'var(--px-font)',
                  fontSize: '0.85rem',
                  color: 'var(--px-teal)',
                  letterSpacing: '0.15em',
                  background: 'var(--px-bg-elevated)',
                  padding: '8px 14px',
                  border: '1px solid var(--px-teal-dim)',
                }}
              >
                {team.join_code}
              </code>
            </div>
          </Panel>
        )}

        <Panel title="MEMBERS">
          {(team.members ?? []).map((m) => (
            <div
              key={m.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 0',
                borderBottom: '1px solid var(--px-teal-dim)',
                flexWrap: 'wrap',
              }}
            >
              <MemberBar name={`${m.first_name} ${m.last_name}`} isCaptain={m.is_captain} />
              {isCaptain && !m.is_captain && (
                <button
                  type="button"
                  className="px-btn-danger"
                  onClick={() => askRemoveMember(m.id)}
                  style={{ marginLeft: 'auto', padding: '10px 16px', fontSize: '0.55rem' }}
                >
                  REMOVE
                </button>
              )}
            </div>
          ))}
        </Panel>

        {team.status === 'active' && (
          <Panel title="MENTORS">
            {confirmed && (team.mentors ?? []).length > 0 ? (
              (team.mentors ?? []).map((m) => (
                <div
                  key={m.mentor_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '10px 0',
                    borderBottom: '1px solid var(--px-teal-dim)',
                  }}
                >
                  <img
                    src={`/api/mentors/${m.mentor_id}/picture`}
                    alt={m.mentor_name ?? 'Mentor'}
                    loading="lazy"
                    onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
                    style={{
                      width: 36,
                      height: 36,
                      objectFit: 'cover',
                      border: '1px solid var(--px-teal-dim)',
                    }}
                  />
                  <div>
                    <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
                      {m.mentor_name}
                    </div>
                    <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
                      {m.company_name}
                    </div>
                  </div>
                </div>
              ))
            ) : prefs.length > 0 ? (
              <div>
                <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', marginBottom: 12 }}>
                  &gt; Preferences submitted. Waiting for matching.
                </p>
                {prefs.map((p, i) => (
                  <div
                    key={p.mentor_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '8px 0',
                    }}
                  >
                    <span className="px-label" style={{ color: 'var(--px-teal)', minWidth: 30 }}>
                      #{i + 1}
                    </span>
                    <span style={{ fontFamily: 'var(--px-mono)', color: 'var(--px-white)' }}>
                      {p.mentor_name ?? `Mentor #${p.mentor_id}`}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div>
                {isCaptain ? (
                  <>
                    <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)', marginBottom: 16 }}>
                      &gt; Your team is active. As captain, rank your preferred mentors so the matching
                      algorithm can find the best fit.
                    </p>
                    <Button variant="primary" href="/chooseMentor">
                      CHOOSE MENTORS
                    </Button>
                  </>
                ) : (
                  <p className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
                    &gt; Waiting for the captain to select mentor preferences.
                  </p>
                )}
              </div>
            )}
          </Panel>
        )}

        {isCaptain && requests.length > 0 && (
          <Panel title={`JOIN REQUESTS (${requests.length})`}>
            {requests.map((r) => {
              const initials = ((r.first_name?.[0] ?? '?') + (r.last_name?.[0] ?? '?')).toUpperCase();
              return (
                <div
                  key={r.request_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '12px 0',
                    borderBottom: '1px solid var(--px-teal-dim)',
                    flexWrap: 'wrap',
                  }}
                >
                  <div
                    aria-hidden="true"
                    style={{
                      width: 40,
                      height: 40,
                      background: 'var(--px-bg-elevated)',
                      border: '1px solid var(--px-teal-dim)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontFamily: 'var(--px-font)',
                      fontSize: '0.6rem',
                      color: 'var(--px-teal)',
                      flexShrink: 0,
                    }}
                  >
                    {initials}
                  </div>
                  <div style={{ flex: 1, minWidth: '160px' }}>
                    <div style={{ fontFamily: 'var(--px-mono)', fontWeight: 700, color: 'var(--px-white)' }}>
                      {r.first_name} {r.last_name}
                    </div>
                    <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
                      {r.email}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      type="button"
                      className="px-btn-primary"
                      onClick={() => handleRequest(r.request_id, 'accept')}
                      aria-label={`Accept ${r.first_name} ${r.last_name}`}
                      style={{ padding: '10px 16px', fontSize: '0.55rem' }}
                    >
                      ACCEPT
                    </button>
                    <button
                      type="button"
                      className="px-btn-danger"
                      onClick={() => handleRequest(r.request_id, 'decline')}
                      aria-label={`Decline ${r.first_name} ${r.last_name}`}
                      style={{ padding: '10px 16px', fontSize: '0.55rem' }}
                    >
                      DECLINE
                    </button>
                  </div>
                </div>
              );
            })}
          </Panel>
        )}

        <Panel title="DANGER ZONE">
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            {!isCaptain && (
              <button type="button" className="px-btn-danger" onClick={askLeave}>
                LEAVE TEAM
              </button>
            )}
            {isCaptain && (
              <button type="button" className="px-btn-danger" onClick={askDisband}>
                DISBAND TEAM
              </button>
            )}
          </div>
        </Panel>
      </div>

      <ConfirmDialog
        open={dialog.open}
        title={dialog.title}
        description={dialog.description}
        confirmLabel={dialog.confirmLabel}
        dangerous={dialog.dangerous}
        onConfirm={dialog.onConfirm}
        onCancel={() => setDialog(CLOSED_DIALOG)}
      />
    </div>
  );
}

function TeamPageContent() {
  const {
    data: meData,
    isLoading,
    refetch,
  } = useQuery<{ success: boolean; user: User }>({
    queryKey: ['me'],
    queryFn: () => api.get('/api/auth/me'),
  });

  const teamId = meData?.user?.team_id;

  const { data: teamData, refetch: refetchTeam } = useQuery<{ team: Team }>({
    queryKey: ['team', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}`),
    enabled: !!teamId,
  });

  function onRefresh() {
    refetch();
    refetchTeam();
  }

  if (isLoading) return <LoadingSpinner fullPage />;

  if (!teamId) return <NoTeamView />;
  if (!teamData?.team) return <LoadingSpinner fullPage />;

  return (
    <TeamDashboardView
      team={teamData.team}
      userId={meData?.user?.id ?? 0}
      onRefresh={onRefresh}
    />
  );
}

export default function TeamPage() {
  return (
    <RequireAuth roles={['participant']}>
      <Navbar />
      <TeamPageContent />
    </RequireAuth>
  );
}
