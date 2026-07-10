import { Link } from 'react-router-dom';
import { useConfig } from '@/context/ConfigContext';
import { PREMIUM_SPONSORS, SUPPORTING_SPONSORS, CONTACT_CHANNELS } from '@/components/home/homeData';
import DiscordIcon from '@/components/home/DiscordIcon';

/**
 * Mobile-first home page. Composed as a single-column stack tuned for
 * phones (≤768px per useIsMobile). Same information architecture as
 * the desktop tree — hero → briefing → sponsors → contact — but every
 * section is re-shaped so it never asks the reader to fight the
 * viewport:
 *
 * - Every tap target ≥48px tall
 * - Cyrillic body copy set at ≥1rem with line-height 1.85 for readability
 * - No sticky side rails (they get in the way of scroll on mobile)
 * - No marquee — a static grid of sponsor tiles instead
 * - Hero image is full-width portrait, no side-by-side crop
 */
export default function MobileHomePage() {
  const { REGISTRATION_OPEN } = useConfig();

  return (
    <main className="mhome">
      <MobileHero registrationOpen={REGISTRATION_OPEN} />
      <MobileBriefing />
      <MobileSponsors />
      <MobileContact />
    </main>
  );
}

/* ────────────────────────────────────────────────────────────
   HERO
   ─────────────────────────────────────────────────────────── */

function MobileHero({ registrationOpen }: { registrationOpen: boolean }) {
  return (
    <section className="mhome-hero" aria-label="FMI Codes 2026 hero">
      {/* Wordmark logo, sized for narrow viewports */}
      <div className="mhome-hero__wordmark">
        <img
          src="/images/codes_logo2.svg"
          alt="FMI Codes 2026"
          style={{
            width: '100%',
            height: 'auto',
            display: 'block',
          }}
        />
      </div>

      {/* Portrait-oriented castle frame */}
      <div className="mhome-hero__frame">
        <div className="mhome-hero__inner">
          <img src="/castle.jpg" alt="" className="mhome-hero__castle" />
          <img
            src="/knight.svg"
            alt=""
            aria-hidden="true"
            className="mhome-hero__knight mhome-hero__knight--left"
          />
          <img
            src="/knight.svg"
            alt=""
            aria-hidden="true"
            className="mhome-hero__knight mhome-hero__knight--right"
          />
        </div>
      </div>

      <div className="mhome-hero__title-block">
        <h1 className="mhome-hero__title">
          CODE FOR
          <br />
          SAFETY
        </h1>
        <p className="mhome-hero__subtitle">
          &gt; ENTER THE DIGITAL ARENA.
          <br />
          &gt; BUILD THE FUTURE. PRESS START.
        </p>
      </div>

      {registrationOpen && (
        <Link to="/registration" className="mhome-hero__cta">
          REGISTER NOW →
        </Link>
      )}

      {/* About card */}
      <aside className="mhome-hero__about">
        <div className="mhome-hero__about-label">&gt; ABOUT THE EVENT</div>
        <p className="mhome-hero__about-body">
          A 48-hour retro-futuristic hackathon at Sofia University FMI. Real
          teams, real mentors, real prize money — the arcade opens in March.
        </p>
      </aside>

      {/* Quick nav — three stacked full-width tiles */}
      <nav className="mhome-hero__nav" aria-label="Quick links">
        <Link to="/regulations" className="mhome-hero__nav-link">
          <span className="mhome-hero__nav-icon" aria-hidden="true">📜</span>
          <span>
            <span className="mhome-hero__nav-title">REGULATIONS</span>
            <span className="mhome-hero__nav-sub">Rules, eligibility & prizes</span>
          </span>
          <span className="mhome-hero__nav-arrow" aria-hidden="true">→</span>
        </Link>
        <Link to="/rankings" className="mhome-hero__nav-link">
          <span className="mhome-hero__nav-icon" aria-hidden="true">🏆</span>
          <span>
            <span className="mhome-hero__nav-title">RANKINGS</span>
            <span className="mhome-hero__nav-sub">The live leaderboard</span>
          </span>
          <span className="mhome-hero__nav-arrow" aria-hidden="true">→</span>
        </Link>
        <Link to="/mentors" className="mhome-hero__nav-link">
          <span className="mhome-hero__nav-icon" aria-hidden="true">👤</span>
          <span>
            <span className="mhome-hero__nav-title">MENTORS</span>
            <span className="mhome-hero__nav-sub">20 engineers · 12 companies</span>
          </span>
          <span className="mhome-hero__nav-arrow" aria-hidden="true">→</span>
        </Link>
      </nav>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   BRIEFING
   ─────────────────────────────────────────────────────────── */

interface BriefingEntry {
  num: string;
  eyebrow: string;
  headline: string;
  body: React.ReactNode;
}

const BRIEFING_ENTRIES: BriefingEntry[] = [
  {
    num: '01',
    eyebrow: 'WHEN',
    headline: 'March 2026 · 48 hours on the clock',
    body: (
      <>
        The gate opens on Friday afternoon and closes Sunday afternoon —{' '}
        <em className="mhome-emph">48 straight hours</em> of coding, sleeping
        under the desks, and shipping in front of a live leaderboard.
      </>
    ),
  },
  {
    num: '02',
    eyebrow: 'WHERE',
    headline: 'Sofia University, FMI',
    body: (
      <>
        The building on <em className="mhome-emph">James Bourchier</em>{' '}
        becomes the arena — lecture halls turned into team pods, corridors
        turned into the mentor circuit, one hall for the live rankings
        projector.
      </>
    ),
  },
  {
    num: '03',
    eyebrow: 'WHO',
    headline: 'Up to 18 teams · ~90 coders · 20 mentors',
    body: (
      <>
        Teams of <em className="mhome-emph">3 to 5</em> square off for real
        prizes from <em className="mhome-emph">12+ industry sponsors</em>.
        Bring your own laptop, your own caffeine, and one idea that matters.
      </>
    ),
  },
];

function MobileBriefing() {
  return (
    <section className="mhome-section" aria-labelledby="mhome-briefing">
      <header className="mhome-section__header">
        <h2 id="mhome-briefing" className="mhome-section__title">
          <span className="mhome-prompt">&gt;</span> BRIEFING
        </h2>
        <p className="mhome-section__sub">A 48-hour quest. Three acts.</p>
      </header>
      <ol className="mhome-briefing__list">
        {BRIEFING_ENTRIES.map((entry) => (
          <li key={entry.num} className="mhome-briefing__item">
            <div className="mhome-briefing__badge">
              <span className="mhome-briefing__num">{entry.num}</span>
              <span className="mhome-briefing__eyebrow">{entry.eyebrow}</span>
            </div>
            <h3 className="mhome-briefing__headline">{entry.headline}</h3>
            <p className="mhome-briefing__body">{entry.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   SPONSORS
   ─────────────────────────────────────────────────────────── */

const PREMIUM = PREMIUM_SPONSORS;

const SUPPORTING = SUPPORTING_SPONSORS.map((s) => s.alt);

function MobileSponsors() {
  return (
    <section className="mhome-section" aria-labelledby="mhome-sponsors">
      <header className="mhome-section__header">
        <h2 id="mhome-sponsors" className="mhome-section__title">
          <span className="mhome-prompt">&gt;</span> SPONSORS
        </h2>
        <p className="mhome-section__sub">
          Twelve companies backing the arena.
        </p>
      </header>

      <ul className="mhome-sponsors__grid" aria-label="Premium sponsors">
        {PREMIUM.map((s) => {
          const scale = s.scale ?? 1;
          return (
            <li key={s.alt}>
              <Link to="/partners" aria-label={s.alt} className="mhome-sponsor">
                <img
                  src={`/companyLogos/${s.file}`}
                  alt={s.alt}
                  loading="lazy"
                  style={
                    scale !== 1
                      ? {
                          transform: `scale(${scale})`,
                          transformOrigin: 'center',
                        }
                      : undefined
                  }
                />
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="mhome-sponsors__supporting">
        <span className="mhome-sponsors__supporting-label">SUPPORTING</span>
        <span className="mhome-sponsors__supporting-list">
          {SUPPORTING.join(' · ')}
        </span>
      </div>

      <Link to="/partners" className="mhome-section__link">
        VIEW ALL PARTNERS →
      </Link>
    </section>
  );
}

/* ────────────────────────────────────────────────────────────
   CONTACT
   ─────────────────────────────────────────────────────────── */

function MobileContact() {
  return (
    <section className="mhome-section" aria-labelledby="mhome-contact">
      <header className="mhome-section__header">
        <h2 id="mhome-contact" className="mhome-section__title">
          <span className="mhome-prompt">&gt;</span> WHERE_TO_TALK
        </h2>
        <p className="mhome-section__sub">
          Announcements, questions, real-time updates.
        </p>
      </header>

      {/* Discord — the primary channel, card treatment */}
      <div className="mhome-discord">
        <div className="mhome-discord__label">&gt; PRIMARY CHANNEL</div>
        <div className="mhome-discord__title-row">
          <span aria-hidden="true" className="mhome-discord__glyph">
            <DiscordIcon size={22} />
          </span>
          <div>
            <div className="mhome-discord__title">DISCORD</div>
            <div className="mhome-discord__url">discord.gg/fmicodes</div>
          </div>
        </div>
        <p className="mhome-discord__body">
          Team captains <em className="mhome-emph">must</em> be reachable
          there during the event. Everyone else — jump in early to ask
          questions and find teammates.
        </p>
        <a
          href="https://discord.gg/fmicodes"
          target="_blank"
          rel="noopener noreferrer"
          className="mhome-discord__cta"
        >
          JOIN DISCORD →
        </a>
      </div>

      {/* Secondary channels — one row each with a big touch target */}
      <ul className="mhome-channels" aria-label="Other channels">
        {CONTACT_CHANNELS.map((c) => (
          <li key={c.label}>
            <a
              href={c.href}
              target={c.external ? '_blank' : undefined}
              rel={c.external ? 'noopener noreferrer' : undefined}
              className="mhome-channel"
            >
              <span className="mhome-channel__label">{c.label}</span>
              <span className="mhome-channel__value">{c.value}</span>
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
