import Navbar from '@/components/layout/Navbar';
import GradientText from '@/components/common/GradientText';
import { Link } from 'react-router-dom';

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
        <div
          className="glass-card"
          style={{ maxWidth: '480px', width: '100%', padding: '48px 40px', textAlign: 'center' }}
        >
          <div style={{ fontSize: '48px', marginBottom: '20px' }}>🔒</div>
          <h1
            style={{
              fontSize: '2rem',
              fontWeight: 900,
              letterSpacing: '-0.02em',
              marginBottom: '12px',
            }}
          >
            <GradientText>Registration Closed</GradientText>
          </h1>
          <p
            style={{
              color: 'var(--muted)',
              fontSize: '15px',
              lineHeight: 1.6,
              marginBottom: '32px',
            }}
          >
            Registration for FMI&#123;Codes&#125; 2026 is currently closed. Stay tuned for updates!
          </p>
          <Link
            to="/"
            style={{
              display: 'inline-block',
              padding: '12px 28px',
              background: 'linear-gradient(135deg, #60a5fa, #22d3ee)',
              borderRadius: '12px',
              color: '#0b1021',
              fontWeight: 700,
              fontSize: '15px',
              textDecoration: 'none',
              boxShadow: '0 4px 20px rgba(96,165,250,0.3)',
            }}
          >
            Back to Home
          </Link>
        </div>
      </main>
    </>
  );
}
