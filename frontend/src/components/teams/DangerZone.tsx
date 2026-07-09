import Panel from '@/components/common/Panel';

/** Leave (member) or Disband (captain) actions. */
export default function DangerZone({
  isCaptain,
  onLeave,
  onDisband,
}: {
  isCaptain: boolean;
  onLeave: () => void;
  onDisband: () => void;
}) {
  return (
    <Panel title="DANGER ZONE">
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        {isCaptain ? (
          <button type="button" className="px-btn-danger" onClick={onDisband}>
            DISBAND TEAM
          </button>
        ) : (
          <button type="button" className="px-btn-danger" onClick={onLeave}>
            LEAVE TEAM
          </button>
        )}
      </div>
    </Panel>
  );
}
