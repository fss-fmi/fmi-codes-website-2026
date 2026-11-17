import Panel from '@/components/common/Panel';

/** Shown on a ranking page when /api/config has never loaded, so it's unknown whether submissions are open. */
export default function PreferencesUnknown() {
  return (
    <main style={{ padding: '100px 24px', maxWidth: 480, margin: '0 auto' }}>
      <Panel title="CAN'T CHECK SUBMISSIONS">
        <p
          className="px-body"
          role="alert"
          style={{ color: 'var(--px-muted-strong)', margin: 0 }}
        >
          &gt; Could not check whether preference submission is open. The page tries again every 30
          seconds.
        </p>
      </Panel>
    </main>
  );
}
