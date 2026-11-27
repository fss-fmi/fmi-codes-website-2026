import StatusBanner from '@/components/teams/StatusBanner';
import { TEAMS_LOCKED } from '@/lib/teamsLock';

/** Shown wherever a team change is offered, once confirmed matching has frozen teams. */
export default function TeamsLockedNotice() {
  return <StatusBanner tone="warning">&gt; {TEAMS_LOCKED}</StatusBanner>;
}
