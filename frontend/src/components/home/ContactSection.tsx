import Button from '@/components/common/Button';
import { CONTACT_CHANNELS } from './homeData';
import DiscordIcon from './DiscordIcon';

/**
 * ContactSection — the fourth act of the Briefing sequence.
 *
 * Extends the numbered spine (01/02/03 established in BriefingSection) with
 * `04 // WHERE_TO_TALK`, so the whole homepage reads as one editorial arc
 * rather than a stack of unrelated widgets. Asymmetric two-column layout:
 * left = terminal statement + prose, right = bordered channel card mirroring
 * the hero's about-card, followed by the secondary channels laid out as a
 * monospace `param // value` readout.
 */

export default function ContactSection() {
  return (
    <section
      aria-labelledby="contact-heading"
      style={{
        background: 'var(--px-bg)',
        padding: 'clamp(72px, 10vw, 120px) 24px',
        maxWidth: 1180,
        margin: '0 auto',
      }}
    >
      {/* Header row — matches BriefingSection + SponsorsSection */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'baseline',
          gap: '16px',
          marginBottom: 'clamp(40px, 5vw, 64px)',
          paddingBottom: '24px',
          borderBottom: '1px solid var(--px-teal-dim)',
        }}
      >
        <h2
          id="contact-heading"
          className="px-prompt-heading"
          style={{
            margin: 0,
            fontSize: 'clamp(0.85rem, 1.8vw, 1.15rem)',
            color: 'var(--px-white)',
          }}
        >
          WHERE_TO_TALK // FMI CODES 2026
        </h2>
        <p
          style={{
            fontFamily: 'var(--px-mono)',
            fontSize: '0.8rem',
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            color: 'var(--px-muted-strong)',
            margin: 0,
            maxWidth: '38ch',
            textAlign: 'right',
          }}
        >
          Announcements, questions, real-time updates.
        </p>
      </div>

      {/* Row — same rail-plus-content layout as Briefing rows */}
      <article
        style={{
          padding: 'clamp(24px, 4vw, 48px) 0',
        }}
        className="contact-row"
      >
        {/* Left rail: numbered continuation + eyebrow */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: 'clamp(2rem, 4.5vw, 3.4rem)',
              color: 'var(--px-teal)',
              lineHeight: 1,
              letterSpacing: '0.02em',
            }}
            aria-hidden="true"
          >
            04
          </div>
          <div
            style={{
              fontFamily: 'var(--px-font)',
              fontSize: '0.55rem',
              letterSpacing: '0.14em',
              color: 'var(--px-salmon)',
              textTransform: 'uppercase',
            }}
          >
            THE CHANNEL
          </div>
        </div>

        {/* Right: split into copy + card */}
        <div
          className="contact-body"
        >
          {/* Copy column */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <h3
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: 'clamp(0.85rem, 1.8vw, 1.2rem)',
                color: 'var(--px-white)',
                lineHeight: 1.45,
                letterSpacing: '0.02em',
                margin: 0,
                textWrap: 'balance',
              }}
            >
              &gt; DISCORD IS THE CHANNEL.
            </h3>
            <p
              style={{
                fontFamily: 'var(--px-mono)',
                fontSize: 'clamp(0.95rem, 1.4vw, 1.05rem)',
                lineHeight: 1.75,
                color: 'var(--px-muted-strong)',
                margin: 0,
                maxWidth: '52ch',
                textWrap: 'pretty',
              }}
            >
              Every announcement, every rule change, every mid-hackathon fire
              drill goes through the{' '}
              <span className="briefing-emph">FMI Codes Discord</span>. Team
              captains{' '}
              <span className="briefing-emph">must</span> be reachable there
              during the event. Everyone else — jump in early to ask questions,
              find teammates, and stalk the sponsors.
            </p>

            {/* Secondary channels as a readout, not chips */}
            <dl
              style={{
                display: 'grid',
                gridTemplateColumns: 'auto 1fr',
                columnGap: '20px',
                rowGap: 0,
                margin: '8px 0 0',
                fontFamily: 'var(--px-mono)',
              }}
            >
              {CONTACT_CHANNELS.map((c, i) => (
                <div
                  key={c.label}
                  style={{
                    display: 'contents',
                  }}
                >
                  <dt
                    style={{
                      fontFamily: 'var(--px-font)',
                      fontSize: '0.5rem',
                      letterSpacing: '0.14em',
                      color: 'var(--px-muted-strong)',
                      padding: '14px 0',
                      borderTop: i === 0 ? 'none' : '1px solid var(--px-teal-dim)',
                      textTransform: 'uppercase',
                      alignSelf: 'center',
                    }}
                  >
                    {c.label}
                  </dt>
                  <dd
                    style={{
                      margin: 0,
                      padding: '14px 0',
                      borderTop: i === 0 ? 'none' : '1px solid var(--px-teal-dim)',
                    }}
                  >
                    <a
                      href={c.href}
                      target={c.external ? '_blank' : undefined}
                      rel={c.external ? 'noopener noreferrer' : undefined}
                      className="contact-channel-link"
                      style={{
                        fontFamily: 'var(--px-mono)',
                        fontSize: '0.9rem',
                        color: 'var(--px-white)',
                        textDecoration: 'none',
                        transition: 'color 180ms var(--px-ease)',
                      }}
                    >
                      {c.value}
                    </a>
                  </dd>
                </div>
              ))}
            </dl>
          </div>

          {/* Discord card — bordered, mirrors the hero about-card motif */}
          <aside
            style={{
              border: '2px solid var(--px-salmon)',
              background: 'var(--px-bg-panel)',
              padding: 'clamp(20px, 3vw, 28px)',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              position: 'relative',
            }}
          >
            <div
              aria-hidden="true"
              style={{
                fontFamily: 'var(--px-font)',
                fontSize: '0.5rem',
                letterSpacing: '0.14em',
                color: 'var(--px-salmon)',
                textTransform: 'uppercase',
              }}
            >
              &gt; PRIMARY CHANNEL
            </div>

            {/* Big Discord glyph */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
              }}
            >
              <DiscordGlyph />
              <div>
                <div
                  style={{
                    fontFamily: 'var(--px-font)',
                    fontSize: 'clamp(0.85rem, 1.6vw, 1rem)',
                    color: 'var(--px-white)',
                    letterSpacing: '0.02em',
                    lineHeight: 1.3,
                  }}
                >
                  DISCORD
                </div>
                <div
                  style={{
                    fontFamily: 'var(--px-mono)',
                    fontSize: '0.75rem',
                    color: 'var(--px-muted)',
                    marginTop: '4px',
                  }}
                >
                  discord.gg/fmicodes
                </div>
              </div>
            </div>

            <Button
              variant="primary"
              href="https://discord.gg/fmicodes"
              target="_blank"
              rel="noopener noreferrer"
              style={{ width: '100%' }}
            >
              JOIN DISCORD →
            </Button>

            <div
              style={{
                fontFamily: 'var(--px-mono)',
                fontSize: '0.75rem',
                color: 'var(--px-muted)',
                lineHeight: 1.65,
                margin: 0,
              }}
            >
              Server opens weeks before the event. Announcements pinned in{' '}
              <span style={{ color: 'var(--px-teal)' }}>#announcements</span>.
            </div>
          </aside>
        </div>
      </article>
    </section>
  );
}

/** Inline pixel-ish Discord glyph — square-corner treatment consistent with the arcade system. */
function DiscordGlyph() {
  return (
    <div
      aria-hidden="true"
      style={{
        width: 48,
        height: 48,
        display: 'grid',
        placeItems: 'center',
        border: '2px solid var(--px-salmon)',
        background: 'var(--px-bg-elevated)',
        flexShrink: 0,
      }}
    >
      <DiscordIcon size={26} />
    </div>
  );
}
