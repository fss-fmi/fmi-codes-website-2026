import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import Panel from '@/components/common/Panel';
import Field from '@/components/common/Field';
import Input from '@/components/common/Input';
import Select from '@/components/common/Select';
import Button from '@/components/common/Button';
import MemberBar from '@/components/common/MemberBar';
import ConfirmDialog from '@/components/common/ConfirmDialog';
import LoadingSpinner from '@/components/common/LoadingSpinner';
import { useToast } from '@/components/common/useToast';
import { useConfirmAction } from '@/hooks/useConfirmAction';
import api from '@/lib/api';
import { errorMessage } from '@/lib/errors';
import type { Member, Team } from '@/types/team';
import type { AdminTeam, RegStatus } from './shared';

interface MentorOption {
  mentor_id: number;
  name: string;
  company_name?: string;
}

interface Assignment {
  team_id: number;
  mentor_id: number;
}

const rowStyle = {
  display: 'flex',
  alignItems: 'center',
  gap: 12,
  padding: '8px 0',
  borderBottom: '1px solid var(--px-teal-dim)',
  flexWrap: 'wrap' as const,
};

const smallButton = { padding: '10px 16px', fontSize: '0.55rem' };

function plural(n: number, word: string) {
  return `${n} ${word}${n === 1 ? '' : 's'}`;
}

function fullName(m: Member) {
  return `${m.first_name} ${m.last_name}`;
}

function teamChoices(reg: RegStatus): { team: AdminTeam; label: string }[] {
  return [
    ...reg.registered_teams.map((team) => ({ team, label: 'REGISTERED' })),
    ...reg.queued_teams.map((team) => ({ team, label: `QUEUED #${team.queue_position}` })),
    ...reg.unregistered_teams.map((team) => ({ team, label: 'NO SLOT' })),
    ...(reg.pending_teams ?? []).map((team) => ({ team, label: 'PENDING' })),
  ];
}

/**
 * Mission Control's escape hatch once matching has frozen teams: the admin moves
 * members and mentors by hand, one team at a time. Works the same in every phase; the
 * server decides what a change does to the team's slot.
 */
export default function TeamsPanel() {
  const [teamId, setTeamId] = useState<number | null>(null);
  const { data, isLoading, isError } = useQuery<RegStatus>({
    queryKey: ['admin-reg-status'],
    queryFn: () => api.get('/api/admin/teams/registration-status'),
  });

  if (isLoading) return <LoadingSpinner />;
  if (isError || !data)
    return (
      <Panel title="TEAMS">
        <p
          className="px-body-sm"
          style={{ color: 'var(--px-danger)', margin: 0 }}
        >
          &gt; Failed to load the teams.
        </p>
      </Panel>
    );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Panel title="TEAM">
        <Field
          id="admin-team-select"
          label="TEAM"
        >
          <Select
            value={teamId ?? ''}
            onChange={(e) => setTeamId(e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Pick a team</option>
            {teamChoices(data).map(({ team, label }) => (
              <option
                key={team.id}
                value={team.id}
              >
                {team.team_name} ({label}, {team.participant_count ?? 0}/6)
              </option>
            ))}
          </Select>
        </Field>
      </Panel>
      {teamId !== null && (
        <TeamEditor
          key={teamId}
          teamId={teamId}
        />
      )}
    </div>
  );
}

function TeamEditor({ teamId }: { teamId: number }) {
  const qc = useQueryClient();
  const { confirm, dialogProps } = useConfirmAction();
  const { data, isLoading, isError } = useQuery<{ team: Team }>({
    queryKey: ['team', teamId],
    queryFn: () => api.get(`/api/teams/${teamId}`),
  });

  function refresh() {
    return Promise.all(
      [['admin-reg-status'], ['admin-pref-status'], ['matching-results'], ['team', teamId]].map(
        (queryKey) => qc.invalidateQueries({ queryKey }),
      ),
    );
  }

  if (isLoading) return <LoadingSpinner />;
  if (isError || !data)
    return (
      <Panel title="TEAM">
        <p
          className="px-body-sm"
          style={{ color: 'var(--px-danger)', margin: 0 }}
        >
          &gt; Failed to load the team.
        </p>
      </Panel>
    );

  return (
    <>
      <MembersSection
        team={data.team}
        teamId={teamId}
        confirm={confirm}
        onChanged={refresh}
      />
      <MentorsSection
        team={data.team}
        teamId={teamId}
        onSaved={refresh}
      />
      <ConfirmDialog {...dialogProps} />
    </>
  );
}

function MembersSection({
  team,
  teamId,
  confirm,
  onChanged,
}: {
  team: Team;
  teamId: number;
  confirm: ReturnType<typeof useConfirmAction>['confirm'];
  onChanged: () => Promise<unknown>;
}) {
  const { showToast } = useToast();
  const [successor, setSuccessor] = useState('');
  const [email, setEmail] = useState('');
  const [adding, setAdding] = useState(false);
  const members = team.members ?? [];
  const others = members.filter((m) => !m.is_captain);

  function askRemove(member: Member) {
    const heir = member.is_captain ? others.find((m) => String(m.id) === successor) : undefined;
    confirm({
      title: 'REMOVE MEMBER',
      description: heir
        ? `Remove ${fullName(member)} from ${team.team_name}? ${fullName(heir)} becomes the captain.`
        : `Remove ${fullName(member)} from ${team.team_name}?`,
      confirmLabel: 'REMOVE',
      dangerous: true,
      action: () =>
        api.delete(
          `/api/admin/teams/${teamId}/members/${member.id}` +
            (heir ? `?new_captain_id=${heir.id}` : ''),
        ),
      successMessage: 'Member removed.',
      onDone: () => {
        setSuccessor('');
        void onChanged();
      },
    });
  }

  async function addMember(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setAdding(true);
    try {
      await api.post(`/api/admin/teams/${teamId}/members`, { email: email.trim() });
      setEmail('');
      showToast({ kind: 'success', message: 'Member added.' });
      void onChanged();
    } catch (err: unknown) {
      showToast({ kind: 'danger', message: errorMessage(err) });
    } finally {
      setAdding(false);
    }
  }

  return (
    <Panel title={`MEMBERS (${members.length}/6)`}>
      {members.map((m) => (
        <div
          key={m.id}
          style={rowStyle}
        >
          <MemberBar
            name={fullName(m)}
            isCaptain={m.is_captain}
          />
          <span
            className="px-body-sm"
            style={{ color: 'var(--px-muted-strong)' }}
          >
            {m.email}
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
            {m.is_captain && others.length > 0 && (
              <Select
                aria-label="New captain"
                value={successor}
                onChange={(e) => setSuccessor(e.target.value)}
              >
                <option value="">New captain…</option>
                {others.map((o) => (
                  <option
                    key={o.id}
                    value={o.id}
                  >
                    {fullName(o)}
                  </option>
                ))}
              </Select>
            )}
            <button
              type="button"
              className="px-btn-danger"
              onClick={() => askRemove(m)}
              disabled={members.length <= 1 || (m.is_captain && !successor)}
              aria-label={`Remove ${fullName(m)}`}
              style={smallButton}
            >
              REMOVE
            </button>
          </div>
        </div>
      ))}
      <form
        onSubmit={addMember}
        noValidate
        style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap', alignItems: 'center' }}
      >
        <Input
          type="email"
          aria-label="Participant email"
          placeholder="Participant email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        />
        <Button
          type="submit"
          variant="secondary"
          disabled={adding || members.length >= 6}
        >
          {adding ? 'ADDING…' : 'ADD MEMBER'}
        </Button>
      </form>
    </Panel>
  );
}

function MentorsSection({
  team,
  teamId,
  onSaved,
}: {
  team: Team;
  teamId: number;
  onSaved: () => Promise<unknown>;
}) {
  const { showToast } = useToast();
  const [draft, setDraft] = useState<number[] | null>(null);
  const [pick, setPick] = useState('');
  const [saving, setSaving] = useState(false);
  const { data: mentorsData } = useQuery<{ mentors: MentorOption[] }>({
    queryKey: ['admin-mentors'],
    queryFn: () => api.get('/api/mentors'),
  });
  const { data: results } = useQuery<{ results: Assignment[] }>({
    queryKey: ['matching-results'],
    queryFn: () => api.get('/api/admin/matching-results'),
  });

  if (!team.is_registered)
    return (
      <Panel title="MENTORS">
        <p
          className="px-body-sm"
          style={{ color: 'var(--px-muted-strong)', margin: 0 }}
        >
          &gt; Only registered teams can be assigned mentors.
        </p>
      </Panel>
    );

  const saved = (team.mentors ?? []).map((m) => m.mentor_id);
  const current = draft ?? saved;
  const all = mentorsData?.mentors ?? [];
  const nameOf = (id: number) =>
    all.find((m) => m.mentor_id === id)?.name ??
    team.mentors?.find((m) => m.mentor_id === id)?.mentor_name ??
    `Mentor #${id}`;
  const load = new Map<number, number>();
  for (const r of results?.results ?? []) load.set(r.mentor_id, (load.get(r.mentor_id) ?? 0) + 1);
  const addable = all.filter((m) => !current.includes(m.mentor_id));

  async function save() {
    setSaving(true);
    try {
      const d = await api.put<{ warnings: string[] }>(`/api/admin/teams/${teamId}/mentors`, {
        mentor_ids: current,
      });
      await onSaved();
      setDraft(null);
      if (d.warnings.length) {
        showToast({ kind: 'warning', message: `Mentors saved. ${d.warnings.join('; ')}` });
      } else {
        showToast({ kind: 'success', message: 'Mentors saved.' });
      }
    } catch (err: unknown) {
      showToast({ kind: 'danger', message: errorMessage(err) });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Panel title={`MENTORS (${current.length})`}>
      {current.length === 0 && (
        <p
          className="px-body-sm"
          style={{ color: 'var(--px-muted-strong)', margin: 0 }}
        >
          &gt; No mentors assigned.
        </p>
      )}
      {current.map((id) => (
        <div
          key={id}
          style={rowStyle}
        >
          <span style={{ fontFamily: 'var(--px-mono)', color: 'var(--px-white)' }}>
            {nameOf(id)}
          </span>
          <button
            type="button"
            className="px-btn-danger"
            onClick={() => setDraft(current.filter((x) => x !== id))}
            aria-label={`Remove mentor ${nameOf(id)}`}
            style={{ ...smallButton, marginLeft: 'auto' }}
          >
            REMOVE
          </button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 12, marginTop: 16, flexWrap: 'wrap' }}>
        <Select
          aria-label="Add mentor"
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          style={{ flex: 1, minWidth: 220 }}
        >
          <option value="">Add a mentor…</option>
          {addable.map((m) => (
            <option
              key={m.mentor_id}
              value={m.mentor_id}
            >
              {m.name} ({plural(load.get(m.mentor_id) ?? 0, 'team')})
            </option>
          ))}
        </Select>
        <Button
          variant="secondary"
          disabled={!pick}
          onClick={() => {
            setDraft([...current, Number(pick)]);
            setPick('');
          }}
        >
          ADD
        </Button>
        <Button
          variant="primary"
          disabled={saving || draft === null}
          onClick={save}
        >
          {saving ? 'SAVING…' : 'SAVE MENTORS'}
        </Button>
      </div>
    </Panel>
  );
}
