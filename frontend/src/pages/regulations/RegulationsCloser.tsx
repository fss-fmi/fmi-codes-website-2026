import { Link } from 'react-router-dom';
import { useConfig } from '@/context/ConfigContext';

/**
 * Closing act shared by Variants A + B — a full-width salmon-bordered card
 * mirroring the hero About motif: castle image left, terminal statement +
 * REGISTER CTA right. Only renders when registration is open.
 */
export default function RegulationsCloser() {
  const { REGISTRATION_OPEN } = useConfig();
  if (!REGISTRATION_OPEN) return null;

  return (
    <div
      style={{
        marginTop: 'clamp(64px, 8vw, 96px)',
        border: '2px solid var(--px-salmon)',
        background: 'var(--px-bg-panel)',
        display: 'grid',
        gridTemplateColumns: 'minmax(220px, 320px) 1fr',
        alignItems: 'stretch',
        overflow: 'hidden',
      }}
      className="regulations-closer"
    >
      <img
        src="/castle.jpg"
        alt=""
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          display: 'block',
          minHeight: '200px',
        }}
      />
      <div
        style={{
          padding: 'clamp(24px, 4vw, 40px)',
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: '0.5rem',
            letterSpacing: '0.14em',
            color: 'var(--px-salmon)',
            textTransform: 'uppercase',
          }}
        >
          &gt; READY TO ENTER?
        </div>
        <h2
          style={{
            fontFamily: 'var(--px-font)',
            fontSize: 'clamp(0.95rem, 2vw, 1.4rem)',
            color: 'var(--px-white)',
            lineHeight: 1.4,
            letterSpacing: '0.02em',
            margin: 0,
            textWrap: 'balance',
          }}
        >
          THIRTEEN RULES.
          <br />
          ONE SIGN-UP FORM.
        </h2>
        <p
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.9rem',
            color: 'var(--px-muted-strong)',
            lineHeight: 1.75,
            margin: '4px 0 12px',
            maxWidth: '52ch',
          }}
        >
          Read the rules, know the timeline, then lock your team in before
          the 18-team cap fills up.
        </p>
        <Link
          to="/registration"
          className="px-btn-primary"
          style={{
            alignSelf: 'flex-start',
            padding: '14px 28px',
            textDecoration: 'none',
          }}
        >
          REGISTER NOW →
        </Link>
      </div>
    </div>
  );
}
