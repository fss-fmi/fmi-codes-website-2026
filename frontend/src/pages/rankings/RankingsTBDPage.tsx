import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';

export default function RankingsTBDPage() {
  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '80vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '60px 24px',
        }}
      >
        <div style={{ maxWidth: 520, width: '100%' }}>
          <Panel title="RANKINGS">
            <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: 0 }}>
              &gt; Rankings will go live when the event starts.
            </p>
          </Panel>
        </div>
      </main>
    </>
  );
}
