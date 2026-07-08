import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Navbar from '@/components/layout/Navbar';
import { useScrollReveal } from '@/hooks/useVisuals';

const START = new Date(2026, 2, 13, 17, 0, 0);
const END = new Date(2026, 2, 15, 23, 59, 59);
const TOTAL = END.getTime() - START.getTime();

const NODE_TIMES = [
  { date: new Date(2026, 2, 13, 17, 0, 0), label: '13 March', pos: 0 },
  { date: new Date(2026, 2, 14, 0, 0, 0), label: '14 March', pos: 50 },
  { date: new Date(2026, 2, 15, 0, 0, 0), label: '15 March', pos: 84 },
];

const DAYS = [
  {
    title: 'Friday',
    subtitle: '13 March',
    icon: '🏰',
    events: [
      { time: '17:00', name: 'Registration' },
      { time: '18:00', name: 'Opening Ceremony' },
      { time: '19:30', name: 'Dinner' },
    ],
  },
  {
    title: 'Saturday',
    subtitle: '14 March',
    icon: '⚔️',
    events: [
      { time: '09:00', name: 'Breakfast' },
      { time: '10:00', name: 'MenTour' },
      { time: '12:00', name: 'Pick Mentors' },
      { time: '13:00', name: 'Lunch' },
      { time: '15:00', name: "Heralds' Gallery" },
      { time: '19:30', name: 'Dinner' },
    ],
  },
  {
    title: 'Sunday',
    subtitle: '15 March',
    icon: '🛡️',
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
      setProgress(Math.max(0, Math.min(1, elapsed / TOTAL)));
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

  const fillPct = 16 + progress * (84 - 16);
  const showCursor = progress > 0 && progress < 1;
  const now = START.getTime() + progress * TOTAL;

  return (
    <>
      <Navbar />
      <main
        style={{
          minHeight: '100vh',
          background: 'var(--px-bg)',
          padding: '40px 24px 80px',
        }}
      >
        {/* Grid bg */}
        <div
          aria-hidden="true"
          style={{
            position: 'fixed',
            inset: 0,
            backgroundImage:
              'linear-gradient(rgba(45,212,191,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(45,212,191,0.03) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />

        <div
          style={{
            position: 'relative',
            zIndex: 1,
            maxWidth: '1200px',
            margin: '0 auto',
          }}
        >
          {/* Page title */}
          <h1
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: 'clamp(0.75rem, 2vw, 1.1rem)',
              color: 'var(--px-salmon)',
              marginBottom: '32px',
              lineHeight: 1.6,
            }}
          >
            FMI <span style={{ color: 'var(--px-teal)' }}>&#123;Codes&#125;</span> 2026
            <br />
            Event Schedule
          </h1>

          {/* 2-column layout */}
          <div
            style={{
              display: 'flex',
              gap: '32px',
              flexWrap: 'wrap',
              alignItems: 'flex-start',
            }}
          >
            {/* Left: castle illustration */}
            <div
              style={{ flex: '1 1 320px', display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              <div
                style={{
                  border: '2px solid var(--px-teal-border)',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <img
                  src="/castle.jpg"
                  alt="Castle"
                  style={{ width: '100%', height: '340px', objectFit: 'cover', display: 'block' }}
                />
                <img
                  src="/knight.svg"
                  alt=""
                  aria-hidden="true"
                  style={{
                    position: 'absolute',
                    bottom: 0,
                    left: '10px',
                    height: '40%',
                    width: 'auto',
                  }}
                />
                <img
                  src="/knight.svg"
                  alt=""
                  aria-hidden="true"
                  style={{
                    position: 'absolute',
                    bottom: 0,
                    right: '10px',
                    height: '40%',
                    width: 'auto',
                    transform: 'scaleX(-1)',
                  }}
                />
              </div>

              {/* Bottom nav buttons */}
              <div className="px-action-row">
                <Link
                  to="/regulations"
                  className="px-btn"
                  style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
                >
                  RULES
                </Link>
                <Link
                  to="/mentors"
                  className="px-btn"
                  style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
                >
                  MENTORS
                </Link>
                <Link
                  to="/rankings"
                  className="px-btn"
                  style={{ flex: 1, textAlign: 'center', fontSize: '0.4rem' }}
                >
                  RANKINGS
                </Link>
              </div>
            </div>

            {/* Right: Quest Timeline */}
            <div
              style={{ flex: '2 1 400px', display: 'flex', flexDirection: 'column', gap: '16px' }}
            >
              <h2
                style={{
                  fontFamily: 'var(--px-font)',
                  fontSize: 'clamp(0.7rem, 1.8vw, 1rem)',
                  color: 'var(--px-teal)',
                  margin: 0,
                }}
              >
                &gt; Quest Timeline
              </h2>

              {/* Progress bar */}
              <div style={{ position: 'relative', height: '24px', marginBottom: '8px' }}>
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    top: '50%',
                    height: '3px',
                    background: 'var(--px-teal-dim)',
                    transform: 'translateY(-50%)',
                  }}
                />
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: '50%',
                    height: '3px',
                    width: `${fillPct}%`,
                    background: 'var(--px-teal)',
                    transform: 'translateY(-50%)',
                    transition: 'width 1s ease',
                  }}
                />
                {showCursor && (
                  <div
                    style={{
                      position: 'absolute',
                      top: '50%',
                      left: `${fillPct}%`,
                      width: '10px',
                      height: '10px',
                      background: 'var(--px-teal)',
                      transform: 'translate(-50%, -50%)',
                    }}
                  />
                )}
                {NODE_TIMES.map((node, i) => {
                  const reached = now >= node.date.getTime();
                  return (
                    <div
                      key={i}
                      style={{
                        position: 'absolute',
                        top: '50%',
                        left: `${node.pos}%`,
                        transform: 'translate(-50%, -50%)',
                      }}
                    >
                      <div
                        style={{
                          width: '10px',
                          height: '10px',
                          border: '2px solid var(--px-teal)',
                          background: reached ? 'var(--px-teal)' : 'var(--px-bg)',
                        }}
                      />
                    </div>
                  );
                })}
              </div>

              {/* Day event sections */}
              {DAYS.map((day, di) => (
                <div
                  key={day.title}
                  className="sched-card reveal"
                  style={{
                    border: '2px solid var(--px-teal-border)',
                    background: 'var(--px-bg-card)',
                    padding: '20px',
                    transitionDelay: `${di * 0.08}s`,
                  }}
                >
                  <h3
                    style={{
                      fontFamily: 'var(--px-font)',
                      fontSize: '0.55rem',
                      color: 'var(--px-teal)',
                      marginBottom: '16px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                    }}
                  >
                    <span>{day.icon}</span>
                    {day.title.toUpperCase()} — {day.subtitle}
                  </h3>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {day.events.map((ev) => (
                      <div
                        key={ev.time}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '12px',
                          padding: '8px 12px',
                          borderLeft: '2px solid var(--px-teal-border)',
                        }}
                      >
                        <span
                          style={{
                            fontFamily: 'var(--px-font)',
                            fontSize: '0.45rem',
                            color: 'var(--px-teal)',
                            flexShrink: 0,
                            minWidth: '52px',
                          }}
                        >
                          {ev.time}
                        </span>
                        <span
                          style={{
                            fontFamily: 'JetBrains Mono, monospace',
                            fontSize: '0.85rem',
                            color: 'var(--px-white)',
                          }}
                        >
                          {ev.name}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
