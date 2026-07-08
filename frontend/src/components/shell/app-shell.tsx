import { useEffect, useState, type FormEvent } from 'react';
import { Link, Outlet, useMatchRoute, useMatches, useNavigate } from '@tanstack/react-router';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { useWorkspace } from '@/contexts/workspace-context';
import { cx } from '@questboard/ui';
import './app-shell.css';

const PAGE_TITLES: Record<string, string> = {
  '/home': 'Home',
  '/search': 'Search',
  '/applications': 'Your log',
  '/board': 'The board',
  '/analytics': 'Analytics',
  '/settings': 'Settings',
};

function BoardIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 5h16M4 12h16M4 19h10" />
    </svg>
  );
}

function LogIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
      <path d="M9 9h6M9 13h4" />
    </svg>
  );
}

function BellIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 9a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7" />
      <path d="M10.5 20a2 2 0 0 0 3 0" />
    </svg>
  );
}

function GearIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M4.5 4.5l2.1 2.1M17.4 17.4l2.1 2.1M2 12h3M19 12h3M4.5 19.5l2.1-2.1M17.4 6.6l2.1-2.1" />
    </svg>
  );
}

function BrandTile() {
  return (
    <span className="qb-brand-tile">
      <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
        <circle cx="4" cy="12" r="1.5" fill="#fff" />
        <path d="M5.2 10.8 10.8 5.2" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" />
        <path d="M7.4 5H11V8.6" stroke="#fff" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '?';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/* Hosted mode only: local-first has no account to represent. Click signs
   out, which is where the old sidebar's sign-out entry moved. */
function AvatarDisc() {
  const { hostedMode, user, currentPersona, signOut } = useWorkspace();
  if (!hostedMode) return null;
  const name = user?.full_name || currentPersona?.full_name || user?.email || '';
  if (!name) return null;
  return (
    <button
      type="button"
      className="qb-avatar"
      title={`Signed in as ${name}. Click to sign out.`}
      onClick={() => void signOut()}
    >
      {initialsOf(name)}
    </button>
  );
}

function SearchBox() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  /* PR 6 wires ?q=; for now submitting lands on the board itself */
  function submit(event: FormEvent) {
    event.preventDefault();
    void navigate({ to: '/board' });
  }
  return (
    <form className="qb-search" role="search" onSubmit={submit}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.8-3.8" />
      </svg>
      <input
        type="text"
        placeholder="Search the board"
        aria-label="Search the board"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
    </form>
  );
}

export function AppShell() {
  const matchRoute = useMatchRoute();
  const matches = useMatches();

  useEffect(() => {
    const path = matches[matches.length - 1]?.fullPath || '/';
    const title = PAGE_TITLES[path] || 'Questboard';
    document.title = `${title}, Questboard`;
  }, [matches]);

  const onHome = Boolean(matchRoute({ to: '/home' }));
  const onBoard = Boolean(matchRoute({ to: '/board' }));
  const onLog = Boolean(matchRoute({ to: '/applications' }));
  const onSettings = Boolean(matchRoute({ to: '/settings' }));

  return (
    <TooltipProvider>
      <div className="qb-page qb-app">
        <aside className="qb-side">
          <Link to="/home" className="qb-brand">
            <BrandTile />
            <span><b>Questboard</b></span>
          </Link>

          <Link to="/board" className={cx('qb-nav-item', onBoard && 'qb-active')}>
            <BoardIcon />
            The board
          </Link>
          <Link
            to="/applications"
            search={{ run: undefined, scope: undefined }}
            className={cx('qb-nav-item', onLog && 'qb-active')}
          >
            <LogIcon />
            Your log
          </Link>
          <button type="button" className="qb-nav-item qb-soon" disabled>
            <BellIcon />
            Alerts <em>soon</em>
          </button>
          <Link
            to="/settings"
            search={{ tab: undefined }}
            className={cx('qb-nav-item', onSettings && 'qb-active')}
          >
            <GearIcon />
            Settings
          </Link>

          <div className="qb-side-note">
            Every listing links straight to the source, with pay shown when the listing states it.
          </div>
        </aside>

        <main className="qb-main">
          <div className="qb-topbar">
            <SearchBox />
            <AvatarDisc />
          </div>
          <nav className="qb-mobilebar" aria-label="Main">
            <Link to="/home" className={cx('qb-mtab', onHome && 'qb-active')}>
              Home
            </Link>
            <Link to="/board" className={cx('qb-mtab', onBoard && 'qb-active')}>
              The board
            </Link>
            <Link
              to="/applications"
              search={{ run: undefined, scope: undefined }}
              className={cx('qb-mtab', onLog && 'qb-active')}
            >
              Your log
            </Link>
            <Link
              to="/settings"
              search={{ tab: undefined }}
              className={cx('qb-mtab', 'qb-mgear', onSettings && 'qb-active')}
              aria-label="Settings"
            >
              <GearIcon />
            </Link>
          </nav>
          <ErrorBoundary resetKey={matches[matches.length - 1]?.fullPath}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <Toaster />
    </TooltipProvider>
  );
}
