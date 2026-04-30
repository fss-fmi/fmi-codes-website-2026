import { Link } from 'react-router-dom';
import GradientText from '@/components/common/GradientText';

export default function NotFoundPage() {
  return (
    <main
      style={{
        minHeight: '80vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '40px 24px',
      }}
    >
      <div
        className="glass-card"
        style={{
          maxWidth: '480px',
          width: '100%',
          padding: '48px 40px',
          textAlign: 'center',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '20px',
        }}
      >
        <div
          style={{ fontSize: 'clamp(4rem, 12vw, 7rem)', fontWeight: 900, letterSpacing: '-0.04em' }}
        >
          <GradientText>404</GradientText>
        </div>
        <h1 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text)' }}>
          Page not found
        </h1>
        <p style={{ fontSize: '0.95rem', color: 'var(--muted)', lineHeight: 1.7 }}>
          This page doesn't exist or has moved.
        </p>
        <Link
          to="/"
          className="btn btn-primary"
          style={{
            marginTop: '8px',
            padding: '12px 32px',
            borderRadius: '12px',
            textDecoration: 'none',
            fontSize: '0.95rem',
          }}
        >
          ← Back to Home
        </Link>
      </div>
    </main>
  );
}
