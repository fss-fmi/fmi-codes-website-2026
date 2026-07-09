import Panel from '@/components/common/Panel';
import type { JoinRequest } from '@/types/team';

/**
 * Captain's pending join-request queue. Buttons for a row disable while that
 * request is being processed so a double-click can't fire the action twice.
 */
export default function JoinRequestsPanel({
  requests,
  busyReqId,
  onRespond,
}: {
  requests: JoinRequest[];
  busyReqId: number | null;
  onRespond: (reqId: number, action: 'accept' | 'decline') => void;
}) {
  return (
    <Panel title={`JOIN REQUESTS (${requests.length})`}>
      {requests.map((r) => {
        const initials = ((r.first_name?.[0] ?? '?') + (r.last_name?.[0] ?? '?')).toUpperCase();
        const busy = busyReqId === r.request_id;
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
                onClick={() => onRespond(r.request_id, 'accept')}
                disabled={busy}
                aria-label={`Accept ${r.first_name} ${r.last_name}`}
                style={{ padding: '10px 16px', fontSize: '0.55rem' }}
              >
                ACCEPT
              </button>
              <button
                type="button"
                className="px-btn-danger"
                onClick={() => onRespond(r.request_id, 'decline')}
                disabled={busy}
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
  );
}
