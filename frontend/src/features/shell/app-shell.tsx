import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, Outlet, useMatchRoute, useMatches, useNavigate } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import {
  Home01Icon,
  Menu01Icon,
  Notebook01Icon,
  PinIcon,
  Search01Icon,
  Settings02Icon,
} from '@hugeicons/core-free-icons';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { BrandMark } from '@/components/shared/brand-mark';
import { cx } from '@questboard/ui';
import { Drawer } from './drawer';
import { UpdatePill } from './update-pill';
import './app-shell.css';

const PAGE_TITLES: Record<string, string> = {
  '/home': 'Home',
  '/log': 'Your log',
  '/log/ledger': 'The full ledger',
  '/log/numbers': 'Your numbers',
  '/board': 'The board',
  '/settings': 'Settings',
  '/health': 'Source health',
};

function SearchBox() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  /* submits into the board's own ?q= filter, MERGING into whatever board
     params are already set: someone searching from the work lane stays on
     their lane with their place/pay filters intact */
  function submit(event: FormEvent) {
    event.preventDefault();
    void navigate({
      to: '/board',
      search: (prev: Record<string, unknown>) => ({ ...prev, q: query.trim() || undefined }),
    });
  }
  return (
    <form className="qb-search" role="search" onSubmit={submit}>
      <HugeiconsIcon icon={Search01Icon} size={15} strokeWidth={1.7} />
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
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);

  useEffect(() => {
    const path = matches[matches.length - 1]?.fullPath || '/';
    const title = PAGE_TITLES[path] || 'Questboard';
    document.title = `${title}, Questboard`;
  }, [matches]);

  const onHome = Boolean(matchRoute({ to: '/home' }));
  const onBoardRoute = Boolean(matchRoute({ to: '/board' }));
  /* Find work (?v=work) is the board's second lane, not a separate place:
     the stub bar lights The board for both lanes, and only the drawer's
     sub-entry distinguishes the work lane */
  const lastSearch = (matches[matches.length - 1]?.search ?? {}) as { v?: string };
  const onWork = onBoardRoute && lastSearch.v === 'work';
  /* fuzzy so the ledger and the numbers keep the log tab lit */
  const onLog = Boolean(matchRoute({ to: '/log', fuzzy: true }));
  const onSettings = Boolean(matchRoute({ to: '/settings' }));
  const onHealth = Boolean(matchRoute({ to: '/health' }));

  return (
    <TooltipProvider>
      <div className="qb-page qb-app" data-menu={menuOpen ? 'open' : 'closed'}>
        <Drawer
          open={menuOpen}
          onClose={closeMenu}
          onHome={onHome}
          onBoard={onBoardRoute && !onWork}
          onWork={onWork}
          onLog={onLog}
          onSettings={onSettings}
          onHealth={onHealth}
        />

        <main className="qb-main">
          <div className="qb-topbar">
            <button
              type="button"
              className="qb-fold"
              aria-label="Open the menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <HugeiconsIcon icon={Menu01Icon} size={17} strokeWidth={1.7} />
            </button>
            <Link to="/home" className="qb-brand">
              <span className="qb-brand-tile" aria-hidden="true"><BrandMark /></span>
              <b>Questboard</b>
            </Link>
            <SearchBox />
            <UpdatePill />
          </div>
          <ErrorBoundary resetKey={matches[matches.length - 1]?.fullPath}>
            <Outlet />
          </ErrorBoundary>
          {/* phone-web: a strip of ticket stubs along the bottom, drawn from
              scratch (perforations between stubs, the active one half torn
              free), never a reskinned platform tab bar */}
          <nav className="qb-stubbar" aria-label="Main">
            <Link to="/home" className={cx('qb-stub', onHome && 'qb-stub-on')}>
              <HugeiconsIcon icon={Home01Icon} size={18} strokeWidth={1.7} />
              Home
            </Link>
            <Link to="/board" className={cx('qb-stub', onBoardRoute && 'qb-stub-on')}>
              <HugeiconsIcon icon={PinIcon} size={18} strokeWidth={1.7} />
              The board
            </Link>
            <Link to="/log" className={cx('qb-stub', onLog && 'qb-stub-on')}>
              <HugeiconsIcon icon={Notebook01Icon} size={18} strokeWidth={1.7} />
              Your log
            </Link>
            <Link
              to="/settings"
              search={{ tab: undefined }}
              className={cx('qb-stub', onSettings && 'qb-stub-on')}
            >
              <HugeiconsIcon icon={Settings02Icon} size={18} strokeWidth={1.7} />
              Settings
            </Link>
          </nav>
        </main>
      </div>
      <Toaster />
    </TooltipProvider>
  );
}
