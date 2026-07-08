import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';
import Button from '@/components/common/Button';

export default function RegistrationClosedPage() {
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
        <div style={{ maxWidth: '480px', width: '100%' }}>
          <Panel title="REGISTRATION CLOSED">
            <p className="px-body" style={{ margin: '0 0 24px 0', color: 'var(--px-muted-strong)' }}>
              &gt; The registration window has closed. Check the schedule for the next opportunity.
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
