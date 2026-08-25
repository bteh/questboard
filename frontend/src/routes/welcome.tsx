import { createRoute, Link } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { LandingPage } from '@/components/landing/landing-page';
import { isDesktopApp } from '@/lib/platform';

/* The stable marketing URL. On the web it renders the landing as-is and
   never sets the entered flag; only a CTA click counts as entering.

   Inside the desktop app (Settings -> "See the front page") the landing's
   download states make no sense: the build is already running, so "Email
   me when the Mac build is ready" reads like the app forgot who it is.
   The wrap below hides those states and puts a "Back to the board" bar on
   top instead. The landing files stay untouched; welcome.test.tsx pins
   the two hidden class names against the real download-cta markup. */

const HIDE_DOWNLOAD_STATES = `
.qb-welcome-in-app .qb-cta-stack,
.qb-welcome-in-app .qb-notify-form {
  display: none;
}
`;

export function WelcomeFrontPage() {
  if (!isDesktopApp()) {
    return <LandingPage />;
  }
  return (
    <div className="qb-welcome-in-app">
      <style>{HIDE_DOWNLOAD_STATES}</style>
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 60,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '10px 18px',
          background: '#1C1B17',
          color: '#FFFDF8',
          fontSize: 13.5,
        }}
      >
        <span>You already have Questboard. This is its public front page.</span>
        <Link
          to="/board"
          style={{ color: '#FFFDF8', fontWeight: 600, textDecoration: 'underline', whiteSpace: 'nowrap' }}
        >
          Back to the board
        </Link>
      </div>
      <LandingPage />
    </div>
  );
}

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/welcome',
  component: WelcomeFrontPage,
});
