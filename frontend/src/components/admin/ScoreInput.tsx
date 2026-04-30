import { useState } from 'react';

interface Props {
  teamId: number;
  teamName: string;
  currentScore: number | null;
  onSave: (teamId: number, score: number) => Promise<void>;
}

export default function ScoreInput({ teamId, teamName, currentScore, onSave }: Props) {
  const [value, setValue] = useState(String(currentScore ?? ''));
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  async function handleSave() {
    const num = parseFloat(value);
    if (isNaN(num)) return;
    setSaving(true);
    try {
      await onSave(teamId, num);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '10px 0',
        borderBottom: '1px solid rgba(148,163,184,0.08)',
      }}
    >
      <div style={{ flex: 1, fontSize: '0.9rem', fontWeight: 500 }}>{teamName}</div>
      <input
        type="number"
        min={0}
        max={100}
        step={0.5}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        style={{
          width: '80px',
          padding: '6px 10px',
          borderRadius: '8px',
          background: 'rgba(255,255,255,0.06)',
          border: '1px solid rgba(255,255,255,0.12)',
          color: 'var(--text)',
          fontSize: '0.9rem',
          textAlign: 'center',
          outline: 'none',
        }}
      />
      <button
        onClick={handleSave}
        disabled={saving}
        className="btn btn-primary"
        style={{ padding: '6px 14px', fontSize: '0.78rem' }}
      >
        {saving ? '…' : saved ? '✓' : 'Save'}
      </button>
    </div>
  );
}
