import { useEffect, useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import PageHeader from '@/components/layout/PageHeader';
import { useScrollReveal } from '@/hooks/useVisuals';

const START = new Date(2026, 2, 13, 17, 0, 0);
const END = new Date(2026, 2, 15, 23, 59, 59);
const TOTAL = END.getTime() - START.getTime();

const NODE_TIMES = [
  { date: new Date(2026, 2, 13, 17, 0, 0), label: '13 March', pos: 16 },
  { date: new Date(2026, 2, 14, 0, 0, 0), label: '14 March', pos: 50 },
  { date: new Date(2026, 2, 15, 0, 0, 0), label: '15 March', pos: 84 },
];

const DAYS = [
  {
    title: 'Friday',
    color: '#60a5fa',
    glow: 'rgba(96,165,250,0.15)',
    events: [
      { time: '17:00', name: 'Registration' },
      { time: '18:00', name: 'Opening Ceremony' },
      { time: '19:30', name: 'Dinner' },
    ],
  },
  {
    title: 'Saturday',
    color: '#22d3ee',
    glow: 'rgba(34,211,238,0.15)',
    events: [
      { time: '09:00', name: 'Breakfast' },
      { time: '10:00', name: 'MenTour' },
      { time: '12:00', name: 'Pick Mentors' },
      { time: '13:00', name: 'Lunch' },
      { time: '19:30', name: 'Dinner' },
    ],
  },
  {
    title: 'Sunday',
    color: '#a78bfa',
    glow: 'rgba(167,139,250,0.15)',
    events: [
      { time: '09:00', name: 'Breakfast' },
      { time: '13:30', name: 'Lunch' },
      { time: '14:00', name: 'Testing' },
      { time: '16:00', name: 'Presentations & Closing' },
    ],
  },
];

function useProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      const now = Date.now();
      const elapsed = now - START.getTime();
      const ratio = Math.max(0, Math.min(1, elapsed / TOTAL));
      setProgress(ratio);
    };
    update();
    const id = setInterval(update, 30_000);
    return () => clearInterval(id);
  }, []);

  return progress;
}

export default function SchedulePage() {
  useScrollReveal('.sched-card');
  const progress = useProgress();

  const barStart = 16;
  const barEnd = 84;
  const fillPct = barStart + progress * (barEnd - barStart);
  const showCursor = progress > 0 && progress < 1;

  // Derive current time from progress state (avoids impure Date.now() in render)
  const now = START.getTime() + progress * TOTAL;

  return (
    <>
      <Navbar />
      <main
        style={{
          padding: '0 0 80px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <PageHeader
          eyebrow="Timeline"
          title="Schedule"
        />

        {/* Progress line */}
        <div style={{ width: '100%', maxWidth: '900px', padding: '0 24px', marginBottom: '40px' }}>
          <div style={{ position: 'relative', height: '110px' }}>
            {/* Track */}
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: '50px',
                height: '6px',
                background: 'rgba(255,255,255,0.05)',
                borderRadius: '999px',
              }}
            />
            {/* Fill */}
            <div
              style={{
                position: 'absolute',
                left: 0,
                top: '50px',
                height: '6px',
                width: `${fillPct}%`,
                borderRadius: '999px',
                background: 'linear-gradient(90deg, #60a5fa, #22d3ee)',
                boxShadow: '0 0 15px rgba(96,165,250,0.4)',
                transition: 'width 1s cubic-bezier(0.22,1,0.36,1)',
              }}
            />
            {/* Cursor */}
            {showCursor && (
              <div
                style={{
                  position: 'absolute',
                  top: 'calc(50px + 3px)',
                  left: `${fillPct}%`,
                  width: '16px',
                  height: '16px',
                  borderRadius: '50%',
                  background: '#fff',
                  transform: 'translate(-50%, -50%)',
                  boxShadow: '0 0 12px #22d3ee, 0 0 24px rgba(34,211,238,0.6)',
                }}
              />
            )}
            {/* Day nodes */}
            {NODE_TIMES.map((node, i) => {
              const reached = now >= node.date.getTime();
              return (
                <div
                  key={i}
                  style={{
                    position: 'absolute',
                    top: 'calc(50px + 3px - 14px)',
                    left: `${node.pos}%`,
                    transform: 'translateX(-50%)',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '16px',
                  }}
                >
                  <div
                    style={{
                      width: '28px',
                      height: '28px',
                      borderRadius: '50%',
                      zIndex: 2,
                      background: reached ? 'var(--bg)' : 'rgba(255,255,255,0.05)',
                      border: reached ? '2px solid #60a5fa' : '2px solid rgba(255,255,255,0.1)',
                      boxShadow: reached
                        ? '0 0 0 4px rgba(96,165,250,0.15), inset 0 0 10px rgba(96,165,250,0.5)'
                        : 'none',
                      transition: 'all 0.6s cubic-bezier(0.22,1,0.36,1)',
                    }}
                  />
                  <div
                    style={{
                      fontFamily: "'JetBrains Mono', monospace",
                      color: reached ? '#22d3ee' : 'rgba(255,255,255,0.3)',
                      fontSize: '14px',
                      fontWeight: 700,
                      whiteSpace: 'nowrap',
                      background: reached ? 'rgba(34,211,238,0.07)' : 'rgba(255,255,255,0.03)',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      border: reached
                        ? '1px solid rgba(34,211,238,0.2)'
                        : '1px solid rgba(255,255,255,0.05)',
                      transition: 'all 0.6s ease',
                    }}
                  >
                    {node.label}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Day cards */}
        <div
          style={{
            width: '100%',
            maxWidth: '1200px',
            padding: '0 24px',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: '24px',
          }}
        >
          {DAYS.map((day, i) => (
            <article
              key={day.title}
              className="glass-card sched-card reveal"
              style={{
                padding: '32px',
                position: 'relative',
                overflow: 'hidden',
                transitionDelay: `${i * 0.1}s`,
              }}
            >
              {/* stripe */}
              <div
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  right: 0,
                  height: '4px',
                  background: `linear-gradient(90deg, ${day.color}, transparent)`,
                }}
              />
              {/* glow */}
              <div
                style={{
                  position: 'absolute',
                  top: '-50px',
                  right: '-50px',
                  width: '150px',
                  height: '150px',
                  borderRadius: '50%',
                  background: day.color,
                  filter: 'blur(60px)',
                  opacity: 0.15,
                  pointerEvents: 'none',
                }}
              />

              <h3
                style={{
                  fontSize: '28px',
                  fontWeight: 800,
                  marginBottom: '24px',
                  color: day.color,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                }}
              >
                {day.title}
              </h3>

              <ul
                style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}
              >
                {day.events.map((ev) => (
                  <li
                    key={ev.time}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 16px',
                      gap: '14px',
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid rgba(255,255,255,0.05)',
                      borderRadius: '12px',
                      fontSize: '14px',
                      transition: 'background 0.2s, transform 0.2s',
                    }}
                  >
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        background: day.color,
                        boxShadow: `0 0 8px ${day.color}`,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        fontFamily: "'JetBrains Mono', monospace",
                        fontSize: '12px',
                        fontWeight: 700,
                        color: day.color,
                        padding: '6px 12px',
                        whiteSpace: 'nowrap',
                        background: `color-mix(in srgb, ${day.color} 10%, transparent)`,
                        border: `1px solid color-mix(in srgb, ${day.color} 20%, transparent)`,
                        borderRadius: '8px',
                      }}
                    >
                      {ev.time}
                    </span>
                    <span style={{ fontWeight: 600, flex: 1, color: 'var(--text)' }}>
                      {ev.name}
                    </span>
                  </li>
                ))}
              </ul>
            </article>
          ))}
        </div>

        {/* Photo booth card */}
        <div
          style={{
            width: '100%',
            maxWidth: '1200px',
            padding: '0 24px',
            marginTop: '24px',
            display: 'flex',
            justifyContent: 'center',
          }}
        >
          <article
            className="glass-card reveal"
            style={{
              width: '100%',
              maxWidth: '500px',
              textAlign: 'center',
              padding: '32px',
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                right: 0,
                height: '4px',
                background: 'linear-gradient(90deg, #f472b6, transparent)',
              }}
            />
            <h3
              style={{
                fontSize: '28px',
                fontWeight: 800,
                color: '#f472b6',
                marginBottom: '16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '12px',
              }}
            >
              📸 Photo Booth
            </h3>
            <div
              style={{ display: 'flex', justifyContent: 'center', gap: '12px', marginTop: '10px' }}
            >
              {['Saturday', '15:00 – 19:00'].map((t) => (
                <span
                  key={t}
                  style={{
                    fontFamily: "'JetBrains Mono', monospace",
                    fontSize: '12px',
                    fontWeight: 700,
                    color: '#f472b6',
                    padding: '6px 12px',
                    borderRadius: '8px',
                    whiteSpace: 'nowrap',
                    background: 'rgba(244,114,182,0.1)',
                    border: '1px solid rgba(244,114,182,0.2)',
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          </article>
        </div>
      </main>
    </>
  );
}
