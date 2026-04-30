interface Props {
  eyebrow?: string;
  title: string;
  titleGradient?: boolean;
  subtitle?: string;
}

export default function PageHeader({ eyebrow, title, titleGradient = true, subtitle }: Props) {
  return (
    <div
      style={{
        maxWidth: '1700px',
        margin: '0 auto',
        padding: '40px 24px 20px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
      }}
    >
      {eyebrow && (
        <p
          style={{
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--accent)',
            marginBottom: '12px',
          }}
        >
          {eyebrow}
        </p>
      )}
      <h1
        style={{
          fontSize: 'clamp(1.8rem, 3.5vw, 2.8rem)',
          fontWeight: 900,
          letterSpacing: '-0.02em',
          lineHeight: 1.2,
        }}
        className={titleGradient ? 'gradient-text' : ''}
      >
        {title}
      </h1>
      {subtitle && (
        <p style={{ fontSize: '1rem', color: 'var(--muted)', marginTop: '8px', lineHeight: 1.7 }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
