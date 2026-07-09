import StatusBadge from '@/components/common/StatusBadge';
import StatusBanner from '@/components/teams/StatusBanner';
import type { Team } from '@/types/team';

/** Team name, status badges, contextual banners, and member count. */
export default function TeamStatusHeader({ team, memberCount }: { team: Team; memberCount: number }) {
  const status = (team.status ?? 'inactive') as
    | 'active'
    | 'inactive'
    | 'queued'
    | 'registered';
  const hasQueuePosition = team.queue_position != null;

  return (
    <div style={{ marginBottom: 24 }}>
      <h1 className="px-page-title" style={{ margin: '0 0 12px 0' }}>
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
        <StatusBadge variant={status} />
        {team.is_registered && <StatusBadge variant="registered" />}
        {hasQueuePosition && <StatusBadge variant="queued" />}
      </div>

      {team.status !== 'active' && (
        <StatusBanner tone="warning">
          &gt; Your team needs at least 3 members to be eligible for the hackathon.
        </StatusBanner>
      )}
      {team.is_registered && (
        <StatusBanner tone="success">
          &gt; Your team is registered for the hackathon.
        </StatusBanner>
      )}
      {!team.is_registered && hasQueuePosition && (
        <StatusBanner tone="warning">
          &gt; In the waiting queue at position #{team.queue_position}. You'll be registered
          automatically when a slot opens.
        </StatusBanner>
      )}

      <div className="px-body-sm" style={{ color: 'var(--px-muted-strong)' }}>
        {memberCount}/6 members
      </div>
    </div>
  );
}
