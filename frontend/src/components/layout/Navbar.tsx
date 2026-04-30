import { useEffect, useRef, useState } from 'react';
import { NavLink, Link, useNavigate } from 'react-router-dom';
import { useAuth } from '@/context/AuthContext';
import { useConfig } from '@/context/ConfigContext';

export default function Navbar() {
  const { user, role, logout } = useAuth();
  const { REGISTRATION_OPEN } = useConfig();
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
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

  const navLinkClass = ({ isActive }: { isActive: boolean }) =>
    `nav-link${isActive ? ' active drawer-nav-active' : ''}`;

  return (
    <>
      <nav
        className={`navbar${scrolled ? ' scrolled' : ''}`}
        id="mainNavbar"
        ref={navRef}
      >
        <div className="navbar-container">
          {/* Logo */}
          <div className="navbar-logo">
            <Link
              to="/"
              aria-label="Go to home"
            >
              <img
                src="/images/FSS_logo_vector_trans_white.svg"
                alt="FSS"
              />
            </Link>
          </div>

          {/* Mobile hamburger */}
          <button
            className="mobile-toggle"
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            onClick={() => setDrawerOpen(true)}
          >
            &#9776;
          </button>

          {/* Nav drawer */}
          <div
            className={`navbar-menu${drawerOpen ? ' drawer-open' : ''}`}
            id="navDrawer"
          >
            <button
              className="drawer-close"
              aria-label="Close navigation"
              onClick={closeDrawer}
            >
              &#10005;
            </button>

            <div
              className="nav-links"
              onClick={closeDrawer}
            >
              <NavLink
                to="/"
                end
                className={navLinkClass}
              >
                Home
              </NavLink>
              <NavLink
                to="/regulations"
                className={navLinkClass}
              >
                Regulations
              </NavLink>
              <NavLink
                to="/schedule"
                className={navLinkClass}
              >
                Schedule
              </NavLink>
              <NavLink
                to="/mentors"
                className={navLinkClass}
              >
                Mentors
              </NavLink>
              <NavLink
                to="/registeredTeams"
                className={navLinkClass}
              >
                Teams
              </NavLink>
              <NavLink
                to="/rankings"
                className={navLinkClass}
              >
                Rankings
              </NavLink>

              {/* Role-specific links */}
              {role === 'participant' && (
                <NavLink
                  to="/team"
                  className={navLinkClass}
                >
                  My Team
                </NavLink>
              )}
              {role === 'mentor' && (
                <NavLink
                  to="/mentorDashboard"
                  className={navLinkClass}
                >
                  Dashboard
                </NavLink>
              )}
              {role === 'admin' && (
                <NavLink
                  to="/admin/matching"
                  className={navLinkClass}
                >
                  Admin
                </NavLink>
              )}
            </div>

            <div className="nav-actions">
              {user ? (
                <>
                  <Link
                    to="/profile"
                    className="profile-btn"
                    aria-label="Profile"
                  >
                    <svg
                      width="22"
                      height="22"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                      <circle
                        cx="12"
                        cy="7"
                        r="4"
                      />
                    </svg>
                  </Link>
                  <button
                    className="login-btn logout-btn"
                    onClick={handleLogout}
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="login-btn ghost-btn"
                    onClick={closeDrawer}
                  >
                    Login
                  </Link>
                  {REGISTRATION_OPEN && (
                    <Link
                      to="/registration"
                      className="login-btn"
                      onClick={closeDrawer}
                    >
                      Register
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
      <div className="navbar-spacer" />

      {/* Floating geo shapes */}
      <div
        className="geo-shapes"
        aria-hidden="true"
      >
        <div className="geo-shape geo-hex-1" />
        <div className="geo-shape geo-circle-1" />
        <div className="geo-shape geo-diamond-1" />
        <div className="geo-shape geo-ring-1" />
        <div className="geo-shape geo-triangle-1" />
        <div className="geo-shape geo-dot-1" />
        <div className="geo-shape geo-hex-2" />
        <div className="geo-shape geo-circle-2" />
      </div>
    </>
  );
}
