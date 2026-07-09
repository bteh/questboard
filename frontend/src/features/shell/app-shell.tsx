import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, Outlet, useMatchRoute, useMatches, useNavigate } from '@tanstack/react-router';
import { HugeiconsIcon } from '@hugeicons/react';
import { Menu01Icon, Search01Icon, Settings02Icon } from '@hugeicons/core-free-icons';
import { TooltipProvider } from '@/components/ui/tooltip';
import { Toaster } from '@/components/ui/sonner';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { BrandMark } from '@/components/shared/brand-mark';
import { cx } from '@questboard/ui';
import { Drawer } from './drawer';
import './app-shell.css';

const PAGE_TITLES: Record<string, string> = {
  '/home': 'Home',
  '/restock': 'Restock',
  '/log': 'Your log',
  '/log/ledger': 'The full ledger',
  '/log/numbers': 'Your numbers',
  '/board': 'The board',
  '/settings': 'Settings',
};

function SearchBox() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  /* submits into the board's own ?q= filter; explicit params beat the
     board's saved state, so this always lands on the typed search */
  function submit(event: FormEvent) {
    event.preventDefault();
    void navigate({ to: '/board', search: { q: query.trim() || undefined } });
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
  const onBoard = Boolean(matchRoute({ to: '/board' }));
  /* fuzzy so the ledger and the numbers keep the log tab lit */
  const onLog = Boolean(matchRoute({ to: '/log', fuzzy: true }));
  const onSettings = Boolean(matchRoute({ to: '/settings' }));

  return (
    <TooltipProvider>
      <div className="qb-page qb-app" data-menu={menuOpen ? 'open' : 'closed'}>
        <Drawer
          open={menuOpen}
          onClose={closeMenu}
          onBoard={onBoard}
          onLog={onLog}
          onSettings={onSettings}
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
          </div>
          <nav className="qb-mobilebar" aria-label="Main">
            <Link to="/home" className={cx('qb-mtab', onHome && 'qb-active')}>
              Home
            </Link>
            <Link to="/board" className={cx('qb-mtab', onBoard && 'qb-active')}>
              The board
            </Link>
            <Link to="/log" className={cx('qb-mtab', onLog && 'qb-active')}>
              Your log
            </Link>
            <Link
              to="/settings"
              search={{ tab: undefined }}
              className={cx('qb-mtab', 'qb-mgear', onSettings && 'qb-active')}
              aria-label="Settings"
            >
              <HugeiconsIcon icon={Settings02Icon} size={17} strokeWidth={1.7} />
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
