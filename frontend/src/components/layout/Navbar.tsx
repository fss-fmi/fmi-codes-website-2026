import { useEffect, useRef, useState } from 'react';
import { NavLink, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useConfig } from '@/context/ConfigContext';

export default function Navbar() {
  const { user, role, logout } = useAuth();
  const { REGISTRATION_OPEN } = useConfig();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const drawerRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);

  // ESC closes the drawer, focus returns to the hamburger
  useEffect(() => {
    if (!drawerOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        setDrawerOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // Lock body scroll while the drawer is open
  useEffect(() => {
    if (!drawerOpen) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [drawerOpen]);

  // Focus trap — cycle Tab / Shift-Tab within the drawer while open
  useEffect(() => {
    if (!drawerOpen) return;
    const container = drawerRef.current;
    if (!container) return;

    // Move focus into the drawer's first focusable element
    const focusables = () =>
      Array.from(
        container.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);

    const first = focusables()[0];
    first?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      const items = focusables();
      if (!items.length) return;
      const firstEl = items[0];
      const lastEl = items[items.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    container.addEventListener('keydown', onKey);
    return () => container.removeEventListener('keydown', onKey);
  }, [drawerOpen]);

  // Return focus to the hamburger when the drawer closes
  useEffect(() => {
    if (drawerOpen) return;
    openerRef.current?.focus({ preventScroll: true });
  }, [drawerOpen]);

  const closeDrawer = () => setDrawerOpen(false);

  const handleLogout = () => {
    logout();
    closeDrawer();
    navigate('/login');
  };

  const desktopLinks = (
    <>
      <NavLink to="/regulations" className={navLinkClass}>
        REGULATIONS
      </NavLink>
      <NavLink to="/schedule" className={navLinkClass}>
        SCHEDULE
      </NavLink>
      <NavLink to="/mentors" className={navLinkClass}>
        MENTORS
      </NavLink>
      <NavLink to="/registeredTeams" className={navLinkClass}>
        TEAMS
      </NavLink>
      <NavLink to="/rankings" className={navLinkClass}>
        RANKINGS
      </NavLink>
      {role === 'participant' && (
        <NavLink to="/team" className={navLinkClass}>
          MY TEAM
        </NavLink>
      )}
      {role === 'mentor' && (
        <NavLink to="/mentorDashboard" className={navLinkClass}>
          DASHBOARD
        </NavLink>
      )}
      {role === 'admin' && (
        <NavLink to="/admin/matching" className={navLinkClass}>
          ADMIN
        </NavLink>
      )}
    </>
  );

  const desktopActions = user ? (
    <>
      <Link to="/profile" className="px-nav-link" aria-label="Profile">
        PROFILE
      </Link>
      <button
        type="button"
        className="px-nav-link"
        onClick={handleLogout}
        style={{ background: 'none', cursor: 'pointer' }}
      >
        LOGOUT
      </button>
    </>
  ) : (
    <>
      <Link to="/login" className="px-nav-link">
        LOGIN
      </Link>
      {REGISTRATION_OPEN && (
        <Link to="/registration" className="px-nav-link register">
          REGISTER
        </Link>
      )}
    </>
  );

  return (
    <>
      <nav className="px-navbar" id="mainNavbar">
        <div className="px-navbar-inner">
          <Link to="/" className="px-logo" aria-label="Go to home">
            FMI <span>&#123;CODES&#125;</span> 2026
          </Link>

          {/* Hamburger — mobile only, hidden ≥769px */}
          <button
            ref={openerRef}
            type="button"
            className="px-mobile-toggle"
            aria-label="Open navigation menu"
            aria-expanded={drawerOpen}
            aria-controls="mobile-drawer"
            onClick={() => setDrawerOpen(true)}
          >
            <span aria-hidden="true">&#9776;</span>
          </button>

          {/* Desktop inline nav — hidden <769px */}
          <div className="px-desktop-nav">
            <div className="px-nav-links">{desktopLinks}</div>
            <div
              className="px-nav-actions"
              style={{ marginLeft: 'auto', display: 'flex', gap: '6px', alignItems: 'center' }}
            >
              {desktopActions}
            </div>
          </div>
        </div>
      </nav>

      {/* Mobile drawer — full-viewport overlay with opaque navy fill, 2px teal
          border, arcade voice throughout. Rendered as a sibling of the navbar
          so it stacks cleanly above everything, including the navbar pill. */}
      {drawerOpen && (
        <div
          className="px-mobile-drawer"
          id="mobile-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="Site navigation"
          ref={drawerRef}
          onClick={(e) => {
            // Click on the backdrop (not the content) closes the drawer
            if (e.target === e.currentTarget) closeDrawer();
          }}
        >
          <div className="px-mobile-drawer__panel">
            <header className="px-mobile-drawer__header">
              <span className="px-mobile-drawer__title">
                &gt; NAVIGATION
              </span>
              <button
                type="button"
                className="px-mobile-drawer__close"
                aria-label="Close navigation menu"
                onClick={closeDrawer}
              >
                <span aria-hidden="true">&#10005;</span>
              </button>
            </header>

            <div className="px-mobile-drawer__group">
              <div className="px-mobile-drawer__label">EVENT</div>
              <ul className="px-mobile-drawer__list">
                {[
                  { to: '/', label: 'HOME', end: true },
                  { to: '/regulations', label: 'REGULATIONS' },
                  { to: '/schedule', label: 'SCHEDULE' },
                  { to: '/mentors', label: 'MENTORS' },
                  { to: '/registeredTeams', label: 'TEAMS' },
                  { to: '/rankings', label: 'RANKINGS' },
                ].map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      className={mobileNavLinkClass}
                      onClick={closeDrawer}
                    >
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>

            {(role === 'participant' || role === 'mentor' || role === 'admin') && (
              <div className="px-mobile-drawer__group">
                <div className="px-mobile-drawer__label">YOU</div>
                <ul className="px-mobile-drawer__list">
                  {role === 'participant' && (
                    <li>
                      <NavLink
                        to="/team"
                        className={mobileNavLinkClass}
                        onClick={closeDrawer}
                      >
                        MY TEAM
                      </NavLink>
                    </li>
                  )}
                  {role === 'mentor' && (
                    <li>
                      <NavLink
                        to="/mentorDashboard"
                        className={mobileNavLinkClass}
                        onClick={closeDrawer}
                      >
                        DASHBOARD
                      </NavLink>
                    </li>
                  )}
                  {role === 'admin' && (
                    <li>
                      <NavLink
                        to="/admin/matching"
                        className={mobileNavLinkClass}
                        onClick={closeDrawer}
                      >
                        ADMIN
                      </NavLink>
                    </li>
                  )}
                </ul>
              </div>
            )}

            <div className="px-mobile-drawer__footer">
              {user ? (
                <>
                  <Link
                    to="/profile"
                    className="px-mobile-drawer__link"
                    onClick={closeDrawer}
                  >
                    PROFILE
                  </Link>
                  <button
                    type="button"
                    className="px-mobile-drawer__cta-secondary"
                    onClick={handleLogout}
                  >
                    LOGOUT
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="px-mobile-drawer__cta-secondary"
                    onClick={closeDrawer}
                  >
                    LOGIN
                  </Link>
                  {REGISTRATION_OPEN && (
                    <Link
                      to="/registration"
                      className="px-mobile-drawer__cta-primary"
                      onClick={closeDrawer}
                    >
                      REGISTER →
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="px-spacer" />
    </>
  );
}

function navLinkClass({ isActive }: { isActive: boolean }): string {
  return `px-nav-link${isActive ? ' active' : ''}`;
}

function mobileNavLinkClass({ isActive }: { isActive: boolean }): string {
  return `px-mobile-drawer__link${isActive ? ' active' : ''}`;
}
