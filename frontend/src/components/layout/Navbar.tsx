import { useEffect, useRef, useState } from 'react';
import { NavLink, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useConfig } from '@/context/ConfigContext';

export default function Navbar() {
  const { user, role, logout } = useAuth();
  const { REGISTRATION_OPEN } = useConfig();
  const navigate = useNavigate();
  const [, setScrolled] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navRef = useRef<HTMLDivElement>(null);

  // Scroll-aware: add .scrolled class at scrollY > 20
  useEffect(() => {
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          setScrolled(window.scrollY > 20);
          ticking = false;
        });
        ticking = true;
      }
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // ESC key closes drawer
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDrawerOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  // Lock body scroll when drawer is open
  useEffect(() => {
    document.body.style.overflow = drawerOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [drawerOpen]);

  function closeDrawer() {
    setDrawerOpen(false);
  }

  function handleLogout() {
    logout();
    navigate('/login');
  }

  return (
    <>
      <nav
        className="px-navbar"
        id="mainNavbar"
        ref={navRef}
      >
        <div className="px-navbar-inner">
          {/* Logo */}
          <Link
            to="/"
            className="px-logo"
            aria-label="Go to home"
          >
            FMI <span>&#123;CODES&#125;</span> 2026
          </Link>

          {/* Mobile hamburger */}
          <button
            className="mobile-toggle"
            style={{ fontFamily: 'inherit', color: 'var(--px-teal)', marginLeft: 'auto' }}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            &#9776;
          </button>

          {/* Nav links */}
          <div
            className={`navbar-menu${drawerOpen ? ' drawer-open' : ''}`}
            id="navDrawer"
          >
            <button
              className="drawer-close"
              aria-label="Close navigation"
              onClick={closeDrawer}
              style={{ color: 'var(--px-teal)' }}
            >
              &#10005;
            </button>

            <div
              className="px-nav-links"
              onClick={closeDrawer}
            >
              <NavLink
                to="/regulations"
                className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
              >
                REGULATIONS
              </NavLink>
              <NavLink
                to="/schedule"
                className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
              >
                SCHEDULE
              </NavLink>
              <NavLink
                to="/mentors"
                className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
              >
                MENTORS
              </NavLink>
              <NavLink
                to="/registeredTeams"
                className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
              >
                TEAMS
              </NavLink>
              <NavLink
                to="/rankings"
                className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
              >
                RANKINGS
              </NavLink>
              {role === 'participant' && (
                <NavLink
                  to="/team"
                  className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
                >
                  MY TEAM
                </NavLink>
              )}
              {role === 'mentor' && (
                <NavLink
                  to="/mentorDashboard"
                  className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
                >
                  DASHBOARD
                </NavLink>
              )}
              {role === 'admin' && (
                <NavLink
                  to="/admin/matching"
                  className={({ isActive }) => `px-nav-link${isActive ? ' active' : ''}`}
                >
                  ADMIN
                </NavLink>
              )}
            </div>

            <div
              className="nav-actions"
              style={{ marginLeft: 'auto', display: 'flex', gap: '6px', alignItems: 'center' }}
            >
              {user ? (
                <>
                  <Link
                    to="/profile"
                    className="px-nav-link"
                    aria-label="Profile"
                  >
                    PROFILE
                  </Link>
                  <button
                    className="px-nav-link"
                    onClick={handleLogout}
                    style={{ background: 'none', cursor: 'pointer' }}
                  >
                    LOGOUT
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="px-nav-link"
                    onClick={closeDrawer}
                  >
                    LOGIN
                  </Link>
                  {REGISTRATION_OPEN && (
                    <Link
                      to="/registration"
                      className="px-nav-link register"
                      onClick={closeDrawer}
                    >
                      REGISTER
                    </Link>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </nav>

      {/* Drawer overlay (mobile) */}
      <div
        className={`drawer-overlay${drawerOpen ? ' active' : ''}`}
        onClick={closeDrawer}
        aria-hidden="true"
      />

      {/* Spacer so content doesn't hide under navbar */}
      <div className="px-spacer" />
    </>
  );
}
