import { useNavigate } from 'react-router-dom';

interface Props {
  to?: string;
  label?: string;
}

export default function BackButton({ to, label = 'Back' }: Props) {
  const navigate = useNavigate();

  function handleClick() {
    if (to) navigate(to);
    else navigate(-1);
  }

  return (
    <button
      onClick={handleClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '8px',
        background: 'none',
        border: 'none',
        cursor: 'pointer',
        color: 'var(--muted)',
        fontSize: '0.9rem',
        fontWeight: 500,
        padding: '6px 0',
        transition: 'color 0.2s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--accent)')}
      onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M19 12H5M12 19l-7-7 7-7" />
      </svg>
      {label}
    </button>
  );
}
