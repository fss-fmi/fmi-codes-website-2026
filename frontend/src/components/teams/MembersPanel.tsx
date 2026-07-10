import Panel from '@/components/common/Panel';
import MemberBar from '@/components/common/MemberBar';
import type { Member } from '@/types/team';

/** Team roster; captains can remove non-captain members. */
export default function MembersPanel({
  members,
  isCaptain,
  onRemove,
}: {
  members: Member[];
  isCaptain: boolean;
  onRemove: (memberId: number) => void;
}) {
  return (
    <Panel title="MEMBERS">
      {members.map((m) => (
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
              onClick={() => onRemove(m.id)}
              style={{ marginLeft: 'auto', padding: '10px 16px', fontSize: '0.55rem' }}
            >
              REMOVE
            </button>
          )}
        </div>
      ))}
    </Panel>
  );
}
