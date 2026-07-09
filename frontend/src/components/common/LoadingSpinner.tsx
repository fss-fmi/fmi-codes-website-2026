export default function LoadingSpinner({ fullPage = false }: { fullPage?: boolean }) {
  const spinner = (
    <div
      style={{
        width: '40px',
        height: '40px',
        borderRadius: '50%',
        border: '3px solid var(--px-teal-dim)',
        borderTopColor: 'var(--px-teal)',
        animation: 'spin 0.8s linear infinite',
      }}
    />
  );

  if (!fullPage) return spinner;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      {spinner}
    </div>
  );
}
