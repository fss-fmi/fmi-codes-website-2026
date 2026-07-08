import Button from '@/components/common/Button';

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

const SECONDARY_CHANNELS: Array<{
  label: string;
  value: string;
  href: string;
  external: boolean;
}> = [
  {
    label: 'INSTAGRAM',
    value: '@fmicodes',
    href: 'https://www.instagram.com/fmicodes/',
    external: true,
  },
  {
    label: 'FACEBOOK',
    value: 'fmicodes',
    href: 'https://www.facebook.com/fmicodes',
    external: true,
  },
  {
    label: 'EMAIL',
    value: 'fss@fmi.uni-sofia.bg',
    href: 'mailto:fss@fmi.uni-sofia.bg',
    external: false,
  },
  {
    label: 'PHONE',
    value: '+359 888 888 888',
    href: 'tel:+359888888888',
    external: false,
  },
];

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
          display: 'grid',
          gridTemplateColumns: 'minmax(120px, 200px) 1fr',
          gap: 'clamp(24px, 4vw, 72px)',
          alignItems: 'start',
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
          style={{
            display: 'grid',
            gridTemplateColumns: '1fr minmax(280px, 380px)',
            gap: 'clamp(28px, 4vw, 56px)',
            alignItems: 'start',
          }}
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
              {SECONDARY_CHANNELS.map((c, i) => (
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
      <svg
        viewBox="0 0 24 24"
        width="26"
        height="26"
        fill="var(--px-salmon)"
        aria-hidden="true"
      >
        <path d="M20.317 4.369A19.79 19.79 0 0 0 16.558 3a13.5 13.5 0 0 0-.63 1.28 18.35 18.35 0 0 0-5.856 0A13.6 13.6 0 0 0 9.442 3a19.74 19.74 0 0 0-3.76 1.369C2.257 9.09 1.334 13.7 1.796 18.24a19.9 19.9 0 0 0 5.994 3.03 14.44 14.44 0 0 0 1.284-2.083 12.85 12.85 0 0 1-2.02-.976c.169-.124.335-.253.495-.386a14.15 14.15 0 0 0 12.902 0c.161.133.327.262.495.386-.646.386-1.324.71-2.021.977a14.5 14.5 0 0 0 1.284 2.082 19.85 19.85 0 0 0 5.995-3.03c.542-5.28-.926-9.85-3.887-13.87ZM8.02 15.478c-1.184 0-2.157-1.085-2.157-2.42 0-1.334.952-2.42 2.157-2.42s2.178 1.086 2.157 2.42c0 1.335-.952 2.42-2.157 2.42Zm7.96 0c-1.183 0-2.156-1.085-2.156-2.42 0-1.334.951-2.42 2.156-2.42s2.178 1.086 2.157 2.42c0 1.335-.952 2.42-2.157 2.42Z" />
      </svg>
    </div>
  );
}
