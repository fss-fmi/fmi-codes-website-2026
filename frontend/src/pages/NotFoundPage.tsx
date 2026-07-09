import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';

export default function NotFoundPage() {
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
          <Panel title="404 — PAGE NOT FOUND">
            <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: '0 0 24px 0' }}>
              &gt; You've wandered off the map. Return to base.
            </p>
            <Button variant="primary" href="/">
              BACK TO HOME
            </Button>
          </Panel>
        </div>
      </main>
    </>
  );
}
