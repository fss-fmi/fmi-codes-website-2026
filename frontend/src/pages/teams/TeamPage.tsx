import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Navbar from '@/components/layout/Navbar';
import RequireAuth from '@/components/layout/RequireAuth';
import GlassCard from '@/components/common/GlassCard';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import StatusBadge from '@/components/common/StatusBadge';
import MemberBar from '@/components/common/MemberBar';
import type { User } from '@/types/auth';
import api from '@/lib/api';
import type { Team, JoinRequest, Application } from '@/types/team';

interface MentorPref {
  mentor_id: number;
  rank: number;
  mentor_name?: string;
}

/* ─── Toast ──────────────────────────────── */
function useToast() {
  const [msg, setMsg] = useState('');
  const [type, setType] = useState<'success' | 'error'>('success');
  function show(m: string, t: 'success' | 'error' = 'success') {
    setMsg(m);
    setType(t);
    setTimeout(() => setMsg(''), 3500);
  }
  const el = msg ? (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        right: 24,
        zIndex: 9999,
        padding: '12px 20px',
        borderRadius: 12,
        background: type === 'success' ? 'rgba(52,211,153,0.15)' : 'rgba(239,68,68,0.15)',
        border: `1px solid ${type === 'success' ? 'rgba(52,211,153,0.3)' : 'rgba(239,68,68,0.3)'}`,
        color: type === 'success' ? '#34d399' : '#fca5a5',
        fontWeight: 600,
        fontSize: 14,
      }}
    >
      {msg}
    </div>
  ) : null;
  return { show, el };
}

/* ─── No-Team state ──────────────────────── */
function NoTeamView() {
  const { show, el } = useToast();

  const { data: appsData, refetch } = useQuery<{ applications: Application[] }>({
    queryKey: ['my-applications'],
    queryFn: () => api.get('/api/teams/my-applications'),
  });

  async function withdraw(requestId: number) {
    if (!confirm('Withdraw this application?')) return;
    const d = await api.post<{ success: boolean; error?: string }>(
      `/api/teams/requests/${requestId}/cancel`,
      {},
    );
    if (d.success) {
      show('Application withdrawn');
      refetch();
    } else show(d.error ?? 'Failed', 'error');
  }

  const apps = appsData?.applications ?? [];

  return (
    <div style={{ padding: '100px 24px', maxWidth: 600, margin: '0 auto' }}>
      <GlassCard style={{ padding: 48, textAlign: 'center', marginBottom: 24 }}>
        <div style={{ fontSize: 48, marginBottom: 20 }}>🚀</div>
        <h1 style={{ fontSize: '1.8rem', fontWeight: 900, marginBottom: 12 }}>
          Get Your Team Together
        </h1>
        <p style={{ color: 'var(--muted)', marginBottom: 32, lineHeight: 1.6 }}>
          Create a new team, join one with an invite code, or browse teams looking for members.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
          <Link
            to="/createTeam"
            className="btn btn-primary"
            style={{ textDecoration: 'none' }}
          >
            Create Team
          </Link>
          <Link
            to="/joinTeam"
            className="btn"
            style={{ textDecoration: 'none' }}
          >
            Join with Code
          </Link>
          <Link
            to="/browseTeams"
            className="btn"
            style={{ textDecoration: 'none' }}
          >
            Browse Teams
          </Link>
        </div>
      </GlassCard>

      {apps.length > 0 && (
        <GlassCard style={{ padding: 24 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>My Applications</h2>
          {apps.map((a) => (
            <div
              key={a.request_id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '12px 0',
                borderBottom: '1px solid rgba(255,255,255,0.06)',
              }}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700 }}>{a.team_name}</div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
                  <StatusBadge variant={a.status as 'pending' | 'accepted' | 'declined'} />
                  <span style={{ color: 'var(--muted)', fontSize: 12 }}>
                    {a.participant_count}/6 members
                  </span>
                </div>
              </div>
              {a.status === 'pending' && (
                <button
                  className="btn"
                  style={{ padding: '6px 14px', fontSize: 12 }}
                  onClick={() => withdraw(a.request_id)}
                >
                  Withdraw
                </button>
              )}
            </div>
          ))}
        </GlassCard>
      )}
      {el}
    </div>
  );
}

/* ─── Team Dashboard ─────────────────────── */
function TeamDashboardView({
  team,
  userId,
  onRefresh,
}: {
  team: Team;
  userId: number;
  onRefresh: () => void;
}) {
  const { show, el } = useToast();
  const isCaptain = String(team.captain_id) === String(userId);
  const teamId = team.id ?? team.team_id!;

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

  async function removeMember(mid: number) {
    if (!confirm('Remove this member from the team?')) return;
    const d = await api.delete<{ success: boolean; error?: string }>(
      `/api/teams/${teamId}/members/${mid}`,
    );
    if (d.success) {
      show('Member removed');
      onRefresh();
    } else show(d.error ?? 'Failed', 'error');
  }

  async function leaveTeam() {
    if (!confirm('Are you sure you want to leave this team?')) return;
    const d = await api.post<{ success: boolean; error?: string }>(
      `/api/teams/${teamId}/leave`,
      {},
    );
    if (d.success) onRefresh();
    else show(d.error ?? 'Failed', 'error');
  }

  async function disbandTeam() {
    if (!confirm('Disband this team? This cannot be undone!')) return;
    if (
      !confirm(
        'Are you absolutely sure? All members will be removed and the team will be permanently deleted.',
      )
    )
      return;
    const d = await api.delete<{ success: boolean; error?: string }>(`/api/teams/${teamId}`);
    if (d.success) onRefresh();
    else show(d.error ?? 'Failed', 'error');
  }

  async function handleRequest(reqId: number, action: 'accept' | 'decline') {
    const d = await api.post<{ success: boolean; error?: string }>(
      `/api/teams/requests/${reqId}/${action}`,
      {},
    );
    if (d.success) {
      show(action === 'accept' ? 'Accepted!' : 'Declined');
      refetchReqs();
      onRefresh();
    } else show(d.error ?? 'Failed', 'error');
  }

  const requests = reqData?.requests ?? [];
  const confirmed = statusData?.confirmed;
  const prefs = prefData?.preferences ?? [];
  const count = team.participant_count ?? team.members?.length ?? 0;

  return (
    <div style={{ padding: '80px 24px 80px', maxWidth: 760, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            flexWrap: 'wrap',
            marginBottom: 8,
          }}
        >
          <h1 style={{ fontSize: '2rem', fontWeight: 900 }}>{team.team_name}</h1>
          <StatusBadge variant={(team.status ?? 'inactive') as 'active' | 'inactive' | 'queued' | 'registered'} />
          {team.is_registered && <StatusBadge variant="registered" />}
          {team.queue_position && <StatusBadge variant="queued" />}
        </div>
        {team.status !== 'active' && (
          <div
            style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.2)',
              color: '#fca5a5',
              padding: '10px 16px',
              borderRadius: 10,
              fontSize: 14,
              marginBottom: 12,
            }}
          >
            Your team needs at least 3 members to be eligible for the hackathon.
          </div>
        )}
        {team.is_registered && (
          <div
            style={{
              background: 'rgba(52,211,153,0.1)',
              border: '1px solid rgba(52,211,153,0.2)',
              color: '#34d399',
              padding: '10px 16px',
              borderRadius: 10,
              fontSize: 14,
              marginBottom: 12,
            }}
          >
            Your team is registered for the hackathon!
          </div>
        )}
        {!team.is_registered && team.queue_position && (
          <div
            style={{
              background: 'rgba(251,191,36,0.1)',
              border: '1px solid rgba(251,191,36,0.2)',
              color: '#fbbf24',
              padding: '10px 16px',
              borderRadius: 10,
              fontSize: 14,
              marginBottom: 12,
            }}
          >
            Your team is in the waiting queue at position #{team.queue_position}. You'll be
            registered automatically when a slot opens.
          </div>
        )}
        <div style={{ color: 'var(--muted)', fontSize: 14 }}>{count}/6 members</div>
      </div>

      {/* Join code (captain only) */}
      {isCaptain && team.join_code && (
        <GlassCard
          style={{
            padding: '16px 24px',
            marginBottom: 20,
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span style={{ color: 'var(--muted)', fontSize: 13, fontWeight: 600 }}>Join Code:</span>
          <code
            style={{
              fontSize: 18,
              fontWeight: 800,
              color: 'var(--accent)',
              letterSpacing: '0.1em',
            }}
          >
            {team.join_code}
          </code>
        </GlassCard>
      )}

      {/* Members */}
      <GlassCard style={{ padding: 24, marginBottom: 20 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>Members</h2>
        {(team.members ?? []).map((m) => (
          <div
            key={m.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 0',
              borderBottom: '1px solid rgba(255,255,255,0.05)',
            }}
          >
            <MemberBar name={`${m.first_name} ${m.last_name}`} isCaptain={m.is_captain} />
            {isCaptain && !m.is_captain && (
              <button
                className="btn"
                style={{
                  padding: '6px 12px',
                  fontSize: 12,
                  marginLeft: 'auto',
                  color: '#fca5a5',
                  border: '1px solid rgba(239,68,68,0.3)',
                  background: 'rgba(239,68,68,0.1)',
                }}
                onClick={() => removeMember(m.id)}
              >
                Remove
              </button>
            )}
          </div>
        ))}
      </GlassCard>

      {/* Mentor section */}
      {team.status === 'active' && (
        <GlassCard style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Mentors</h2>
          {confirmed && (team.mentors ?? []).length > 0 ? (
            (team.mentors ?? []).map((m) => (
              <div
                key={m.mentor_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                }}
              >
                <img
                  src={`/api/mentors/${m.mentor_id}/picture`}
                  alt=""
                  style={{ width: 36, height: 36, borderRadius: '50%', objectFit: 'cover' }}
                  onError={(e) => (e.currentTarget.style.display = 'none')}
                />
                <div>
                  <div style={{ fontWeight: 700 }}>{m.mentor_name}</div>
                  <div style={{ fontSize: 13, color: 'var(--muted)' }}>{m.company_name}</div>
                </div>
              </div>
            ))
          ) : prefs.length > 0 ? (
            <div>
              <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 12 }}>
                Preferences submitted. Waiting for matching.
              </p>
              {prefs
                .sort((a: MentorPref, b: MentorPref) => a.rank - b.rank)
                .map((p: MentorPref, i: number) => (
                  <div
                    key={p.mentor_id}
                    style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0' }}
                  >
                    <span style={{ color: 'var(--accent)', fontWeight: 800, minWidth: 20 }}>
                      {i + 1}.
                    </span>
                    <span style={{ fontWeight: 600 }}>
                      {p.mentor_name ?? `Mentor #${p.mentor_id}`}
                    </span>
                  </div>
                ))}
            </div>
          ) : (
            <div>
              {isCaptain ? (
                <>
                  <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 16 }}>
                    Your team is active! As captain, you can now rank your preferred mentors so the
                    matching algorithm can find the best fit.
                  </p>
                  <Link
                    to="/chooseMentor"
                    className="btn btn-primary"
                    style={{ textDecoration: 'none' }}
                  >
                    Choose Mentors
                  </Link>
                </>
              ) : (
                <p style={{ color: 'var(--muted)', fontSize: 14 }}>
                  Waiting for the captain to select mentor preferences.
                </p>
              )}
            </div>
          )}
        </GlassCard>
      )}

      {/* Join requests */}
      {isCaptain && requests.length > 0 && (
        <GlassCard style={{ padding: 24, marginBottom: 20 }}>
          <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16 }}>
            Join Requests{' '}
            <span
              style={{
                background: 'rgba(96,165,250,0.15)',
                color: '#60a5fa',
                padding: '2px 8px',
                borderRadius: '999px',
                fontSize: 12,
                marginLeft: 8,
              }}
            >
              {requests.length}
            </span>
          </h2>
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
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                }}
              >
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: '50%',
                    background: 'linear-gradient(135deg, #60a5fa, #a78bfa)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    color: '#0b1021',
                    fontSize: 14,
                    flexShrink: 0,
                  }}
                >
                  {initials}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700 }}>
                    {r.first_name} {r.last_name}
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--muted)' }}>{r.email}</div>
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    className="btn btn-primary"
                    style={{ padding: '6px 14px', fontSize: 12 }}
                    onClick={() => handleRequest(r.request_id, 'accept')}
                  >
                    Accept
                  </button>
                  <button
                    className="btn"
                    style={{
                      padding: '6px 14px',
                      fontSize: 12,
                      color: '#fca5a5',
                      border: '1px solid rgba(239,68,68,0.3)',
                      background: 'rgba(239,68,68,0.1)',
                    }}
                    onClick={() => handleRequest(r.request_id, 'decline')}
                  >
                    Decline
                  </button>
                </div>
              </div>
            );
          })}
        </GlassCard>
      )}

      {/* Danger zone */}
      <GlassCard
        accentColor="rgba(239,68,68,0.15)"
        style={{ padding: 24 }}
      >
        <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 16, color: '#fca5a5' }}>
          Danger Zone
        </h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {!isCaptain && (
            <button
              className="btn"
              style={{
                color: '#fca5a5',
                border: '1px solid rgba(239,68,68,0.3)',
                background: 'rgba(239,68,68,0.1)',
              }}
              onClick={leaveTeam}
            >
              Leave Team
            </button>
          )}
          {isCaptain && (
            <button
              className="btn"
              style={{
                color: '#fca5a5',
                border: '1px solid rgba(239,68,68,0.3)',
                background: 'rgba(239,68,68,0.1)',
              }}
              onClick={disbandTeam}
            >
              Disband Team
            </button>
          )}
        </div>
      </GlassCard>
      {el}
    </div>
  );
}

/* ─── Main page ──────────────────────────── */
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
