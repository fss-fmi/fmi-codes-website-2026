import { useState, useEffect } from 'react';

export default function Clock() {
  const [clock, setClock] = useState(() =>
    new Date().toLocaleTimeString('en-GB', { hour12: false }),
  );

  useEffect(() => {
    const id = setInterval(
      () => setClock(new Date().toLocaleTimeString('en-GB', { hour12: false })),
      1000,
    );
    return () => clearInterval(id);
  }, []);

  return (
    <div
      style={{
        fontFamily: 'var(--px-font)',
        fontSize: '1.2rem',
        color: 'var(--px-teal)',
        letterSpacing: '0.08em',
        paddingTop: 48,
      }}
      aria-label="Current time"
    >
      {clock}
    </div>
  );
}
