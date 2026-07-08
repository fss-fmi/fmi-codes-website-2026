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
    if (isNaN(num) || num < 0 || num > 100) return;
    setSaving(true);
    try {
      await onSave(teamId, num);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } finally {
      setSaving(false);
    }
  }

  const inputId = `score-input-${teamId}`;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '12px',
        padding: '10px 0',
        borderBottom: '1px solid var(--px-teal-dim)',
      }}
    >
      <label
        htmlFor={inputId}
        style={{
          flex: 1,
          fontFamily: 'var(--px-mono)',
          fontSize: '0.9rem',
          fontWeight: 500,
          color: 'var(--px-white)',
        }}
      >
        {teamName}
      </label>
      <input
        id={inputId}
        type="number"
        min={0}
        max={100}
        step={0.5}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label={`Score for ${teamName}`}
        className="px-input-field"
        style={{
          width: '90px',
          padding: '8px 10px',
          textAlign: 'center',
        }}
      />
      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="px-btn-secondary"
        aria-label={`Save score for ${teamName}`}
        style={{ padding: '10px 14px', fontSize: '0.55rem' }}
      >
        {saving ? '…' : saved ? '✓' : 'SAVE'}
      </button>
    </div>
  );
}
