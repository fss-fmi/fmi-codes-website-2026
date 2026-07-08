import Navbar from '@/components/layout/Navbar';
import Panel from '@/components/common/Panel';

export default function MentorsStayTunedPage() {
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
        <div style={{ width: '100%', maxWidth: '560px' }}>
          <Panel title="MENTORS COMING SOON">
            <p className="px-body" style={{ color: 'var(--px-muted-strong)', margin: '0 0 20px 0' }}>
              &gt; The mentor roster is being finalized. Check back soon.
            </p>
            <p
              className="px-body"
              style={{
                color: 'var(--px-teal)',
                margin: 0,
                fontFamily: 'var(--px-font)',
                fontSize: '0.75rem',
              }}
            >
              &gt; <span className="px-cursor" aria-hidden="true" />
            </p>
          </Panel>
        </div>
      </main>
    </>
  );
}
