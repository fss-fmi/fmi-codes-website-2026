import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import api from '@/lib/api';
import type { FeatureFlag, FlagName } from './shared';

interface FlagText {
  title: string;
  hint: string;
  onState: string;
  offState: string;
  turnOn: string;
  turnOff: string;
}

const FLAG_TEXT: Record<FlagName, FlagText> = {
  registration_open: {
    title: 'PARTICIPANT REGISTRATION',
    hint: 'Sign-up at /registration and the REGISTER links.',
    onState: 'OPEN',
    offState: 'CLOSED',
    turnOn: 'OPEN',
    turnOff: 'CLOSE',
  },
  rankings_live: {
    title: 'LIVE RANKINGS',
    hint: 'The public leaderboard at /rankings and team scores in the API.',
    onState: 'LIVE',
    offState: 'HIDDEN',
    turnOn: 'PUBLISH',
    turnOff: 'HIDE',
  },
  mentors_stay_tuned: {
    title: 'MENTOR ROSTER',
    hint: 'While ON, /mentors shows "MENTORS COMING SOON" instead of the roster.',
    onState: 'COMING SOON',
    offState: 'PUBLIC',
    turnOn: 'HIDE ROSTER',
    turnOff: 'SHOW ROSTER',
  },
};

const FLAG_ORDER: FlagName[] = ['registration_open', 'rankings_live', 'mentors_stay_tuned'];

function formatLocal(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** `datetime-local` value (the admin's local time) → ISO 8601 with the local UTC offset. */
function localInputToIso(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:00` +
    `${sign}${pad(offset / 60)}:${pad(offset % 60)}`
  );
}

function FlagCard({
  flag,
  confirm,
  onChanged,
}: {
  flag: FeatureFlag;
  confirm: ReturnType<typeof useConfirmAction>['confirm'];
  onChanged: () => void;
}) {
  const text = FLAG_TEXT[flag.name];
  const [when, setWhen] = useState('');
  const next = !flag.enabled;
  const nextVerb = next ? text.turnOn : text.turnOff;
  const scheduleIso = when ? localInputToIso(when) : null;

  function askSwitch() {
    confirm({
      title: `${nextVerb} NOW`,
      description: `${text.title}: ${flag.enabled ? text.onState : text.offState} → ${
        next ? text.onState : text.offState
      }, right now. Open pages pick it up within 30 seconds and the event feed is notified.`,
      confirmLabel: nextVerb,
      dangerous: true,
      action: async () => {
        await api.put(`/api/admin/flags/${flag.name}`, { enabled: next });
      },
      successMessage: `${text.title}: ${next ? text.onState : text.offState}.`,
      onDone: onChanged,
    });
  }

  function askSchedule() {
    if (!scheduleIso) return;
    confirm({
      title: `SCHEDULE ${nextVerb}`,
      description: `${text.title} becomes ${next ? text.onState : text.offState} at ${formatLocal(
        scheduleIso,
      )} (your time), without anyone pressing a button.${
        flag.scheduled_at ? ' This replaces the pending schedule.' : ''
      }`,
      confirmLabel: 'SCHEDULE',
      action: async () => {
        await api.put(`/api/admin/flags/${flag.name}/schedule`, { value: next, at: scheduleIso });
        setWhen('');
      },
      successMessage: 'Change scheduled.',
      onDone: onChanged,
    });
  }

  function askCancel() {
    confirm({
      title: 'CANCEL SCHEDULE',
      description: `${text.title} stays ${flag.enabled ? text.onState : text.offState}.`,
      confirmLabel: 'CANCEL SCHEDULE',
      action: async () => {
        await api.delete(`/api/admin/flags/${flag.name}/schedule`);
      },
      successMessage: 'Schedule cancelled.',
      onDone: onChanged,
    });
  }

  return (
    <Panel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div
              className="px-label"
              style={{ marginBottom: 8 }}
            >
              {text.title}
            </div>
            <div
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '1rem',
                color: flag.enabled ? 'var(--px-teal)' : 'var(--px-salmon)',
              }}
            >
              {flag.enabled ? text.onState : text.offState}
            </div>
            <p
              className="px-body-sm"
              style={{ margin: '8px 0 0' }}
            >
              {text.hint} Last changed {formatLocal(flag.updated_at)}.
            </p>
          </div>
          <button
            type="button"
            className="px-btn-primary"
            onClick={askSwitch}
          >
            {nextVerb} NOW
          </button>
        </div>

        {flag.scheduled_at && flag.scheduled_value !== null ? (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              flexWrap: 'wrap',
              padding: '10px 14px',
              background: 'var(--px-bg-card)',
              border: '1px solid var(--px-teal-dim)',
              fontFamily: 'var(--px-mono)',
              fontSize: '0.85rem',
              color: 'var(--px-white)',
            }}
          >
            <span>
              Scheduled: {flag.scheduled_value ? text.onState : text.offState} at{' '}
              {formatLocal(flag.scheduled_at)}
            </span>
            <button
              type="button"
              className="px-btn-ghost"
              onClick={askCancel}
            >
              CANCEL SCHEDULE
            </button>
          </div>
        ) : null}

        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 6, flex: '1 1 220px' }}>
            <span className="px-label">SCHEDULE {nextVerb} AT (YOUR TIME)</span>
            <input
              type="datetime-local"
              className="px-input-field"
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          </label>
          <button
            type="button"
            className="px-btn-secondary"
            onClick={askSchedule}
            disabled={!scheduleIso}
          >
            SCHEDULE
          </button>
        </div>
      </div>
    </Panel>
  );
}

export default function SitePanel() {
  const qc = useQueryClient();
  const { confirm, dialogProps } = useConfirmAction();

  // Polled so a schedule that fires shows up here without a reload.
  const { data, isError } = useQuery<{ success: boolean; flags: FeatureFlag[] }>({
    queryKey: ['admin-flags'],
    queryFn: () => api.get('/api/admin/flags'),
    refetchInterval: 15_000,
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ['admin-flags'] });
    qc.invalidateQueries({ queryKey: ['config'] });
  }

  const byName = new Map((data?.flags ?? []).map((f) => [f.name, f]));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {isError ? (
        <p className="px-body-sm">Could not load the site switches. Reload to try again.</p>
      ) : null}
      {FLAG_ORDER.map((name) => {
        const flag = byName.get(name);
        return flag ? (
          <FlagCard
            key={name}
            flag={flag}
            confirm={confirm}
            onChanged={refresh}
          />
        ) : null;
      })}
      <ConfirmDialog {...dialogProps} />
    </div>
  );
}
