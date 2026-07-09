interface Props {
  title: string;
  description?: string;
}

export default function PageHeader({ title, description }: Props) {
  return (
    <div
      style={{
        maxWidth: '1700px',
        margin: '0 auto',
        padding: '40px 24px 20px',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: '12px',
      }}
    >
      <h1 className="px-page-title">{title}</h1>
      {description ? (
        <p
          className="px-body-sm"
          style={{ color: 'var(--px-muted-strong)', maxWidth: '65ch', margin: 0 }}
        >
          {description}
        </p>
      ) : null}
    </div>
  );
}
