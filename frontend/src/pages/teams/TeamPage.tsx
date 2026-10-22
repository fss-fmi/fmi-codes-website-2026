import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import Panel from '@/components/common/Panel';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import StatusBadge from '@/components/common/StatusBadge';
import Button from '@/components/common/Button';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useToast } from '@/components/common/useToast';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import TeamStatusHeader from '@/components/teams/TeamStatusHeader';
import JoinCodePanel from '@/components/teams/JoinCodePanel';
import MembersPanel from '@/components/teams/MembersPanel';
import MentorsPanel from '@/components/teams/MentorsPanel';
import JoinRequestsPanel from '@/components/teams/JoinRequestsPanel';
import DangerZone from '@/components/teams/DangerZone';
import VerifyEmailNotice from '@/components/common/VerifyEmailNotice';
import { useAuth } from '@/context/AuthContext';
import { useConfig } from '@/context/ConfigContext';
import type { User } from '@/types/auth';
import api from '@/lib/api';
import type { Team, JoinRequest, Application } from '@/types/team';

interface MentorPref {
  mentor_id: number;
  rank: number;
  mentor_name?: string;
}

function NoTeamView() {
  const { confirm, dialogProps } = useConfirmAction();
  const { user } = useAuth();
  const { REQUIRE_EMAIL_VERIFICATION } = useConfig();

  const { data: appsData, refetch } = useQuery<{ applications: Application[] }>({
    queryKey: ['my-applications'],
    queryFn: () => api.get('/api/teams/my-applications'),
  });

  function requestWithdraw(requestId: number) {
    confirm({
      title: 'WITHDRAW APPLICATION',
      description: 'Withdraw this application?',
      confirmLabel: 'WITHDRAW',
      dangerous: true,
      action: () => api.post(`/api/teams/requests/${requestId}/cancel`, {}),
      successMessage: 'Application withdrawn.',
      onDone: refetch,
    });
  }

  const apps = appsData?.applications ?? [];

  return (
    <div style={{ padding: '100px 24px', maxWidth: 640, margin: '0 auto' }}>
      {REQUIRE_EMAIL_VERIFICATION && (
        <VerifyEmailNotice
          email={user?.email}
          verified={user?.email_verified}
        />
      )}
      <Panel
        title="NO TEAM YET"
        style={{ marginBottom: '24px' }}
      >
        <p
          className="px-body"
          style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}
        >
          Assemble a team of up to 6 to compete in FMI Codes 2026. Create your own, join a team with
          an invite code, or browse open teams.
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Button
            variant="primary"
            href="/createTeam"
          >
            CREATE TEAM
          </Button>
          <Button
            variant="secondary"
            href="/joinTeam"
          >
            JOIN WITH CODE
          </Button>
          <Button
            variant="secondary"
            href="/browseTeams"
          >
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
                  <div
                    style={{
                      fontFamily: 'var(--px-mono)',
                      fontWeight: 700,
                      color: 'var(--px-white)',
                    }}
                  >
                    {a.team_name}
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                    <StatusBadge variant={a.status} />
                    <span
                      style={{
                        color: 'var(--px-muted-strong)',
                        fontFamily: 'var(--px-mono)',
                        fontSize: '0.8rem',
                      }}
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

      <ConfirmDialog {...dialogProps} />
    </div>
  );
}

function TeamDashboardView({
  team,
  teamId,
  userId,
  onRefresh,
}: {
  team: Team;
  teamId: number;
  userId: number;
  onRefresh: () => void;
}) {
  const { showToast } = useToast();
  const { confirm, dialogProps } = useConfirmAction();
  const isCaptain = String(team.captain_id) === String(userId);
  const [busyReqId, setBusyReqId] = useState<number | null>(null);

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
    enabled: team.status === 'active',
  });

  function askRemoveMember(mid: number) {
    confirm({
      title: 'REMOVE MEMBER',
      description: 'Remove this member from the team?',
      confirmLabel: 'REMOVE',
      dangerous: true,
      action: () => api.delete(`/api/teams/${teamId}/members/${mid}`),
      successMessage: 'Member removed.',
      onDone: onRefresh,
    });
  }

  function askLeave() {
    confirm({
      title: 'LEAVE TEAM',
      description: 'Are you sure you want to leave this team?',
      confirmLabel: 'LEAVE',
      dangerous: true,
      action: () => api.post(`/api/teams/${teamId}/leave`, {}),
      onDone: onRefresh,
    });
  }

  function askDisband() {
    confirm({
      title: 'DISBAND TEAM',
      description:
        'Are you absolutely sure? All members will be removed and the team will be permanently deleted. This cannot be undone.',
      confirmLabel: 'DISBAND',
      dangerous: true,
      action: () => api.delete(`/api/teams/${teamId}`),
      onDone: onRefresh,
    });
  }

  async function respondToRequest(reqId: number, action: 'accept' | 'decline') {
    if (busyReqId !== null) return;
    setBusyReqId(reqId);
    try {
      await api.post(`/api/teams/requests/${reqId}/${action}`, {});
      showToast({
        kind: action === 'accept' ? 'success' : 'info',
        message: action === 'accept' ? 'Accepted.' : 'Declined.',
      });
      refetchReqs();
      onRefresh();
    } catch (e) {
      showToast({ kind: 'danger', message: (e as Error).message || 'Failed.' });
    } finally {
      setBusyReqId(null);
    }
  }

  const requests = reqData?.requests ?? [];
  const prefs: MentorPref[] = [...(prefData?.preferences ?? [])].sort((a, b) => a.rank - b.rank);
  const memberCount = team.participant_count ?? team.members?.length ?? 0;

  return (
    <div style={{ padding: '80px 24px 80px', maxWidth: 820, margin: '0 auto' }}>
      <TeamStatusHeader
        team={team}
        memberCount={memberCount}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {isCaptain && team.join_code && <JoinCodePanel joinCode={team.join_code} />}

        <MembersPanel
          members={team.members ?? []}
          isCaptain={isCaptain}
          onRemove={askRemoveMember}
        />

        {team.status === 'active' && (
          <MentorsPanel
            confirmed={statusData?.confirmed}
            mentors={team.mentors ?? []}
            prefs={prefs}
            isCaptain={isCaptain}
          />
        )}

        {isCaptain && requests.length > 0 && (
          <JoinRequestsPanel
            requests={requests}
            busyReqId={busyReqId}
            onRespond={respondToRequest}
          />
        )}

        <DangerZone
          isCaptain={isCaptain}
          onLeave={askLeave}
          onDisband={askDisband}
        />
      </div>

      <ConfirmDialog {...dialogProps} />
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

  const {
    data: teamData,
    isError: teamIsError,
    refetch: refetchTeam,
  } = useQuery<{ team: Team }>({
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
  if (teamIsError)
    return (
      <div style={{ padding: '100px 24px', maxWidth: 640, margin: '0 auto' }}>
        <Panel title="COULD NOT LOAD TEAM">
          <p
            className="px-body"
            style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}
          >
            &gt; Failed to load your team. Check your connection and try again.
          </p>
          <Button
            variant="secondary"
            onClick={() => refetchTeam()}
          >
            RETRY
          </Button>
        </Panel>
      </div>
    );
  if (!teamData?.team) return <LoadingSpinner fullPage />;

  const team = teamData.team;
  const resolvedTeamId = team.id ?? team.team_id ?? teamId;

  return (
    <TeamDashboardView
      team={team}
      teamId={resolvedTeamId}
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
