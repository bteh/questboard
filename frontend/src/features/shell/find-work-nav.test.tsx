// @vitest-environment jsdom
/* Find work is the board's second workflow, not a separate place. The nav
   says so: the board page carries a two-tab lane switcher (Side quests |
   Find work), the drawer shows Find work as a sub-entry directly under
   The board, and the phone stub bar has one board door that stays lit for
   both lanes. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';

afterEach(cleanup);

vi.mock('@tanstack/react-router', () => ({
  Link: ({
    children,
    className,
    onClick,
    'aria-current': ariaCurrent,
  }: {
    children: ReactNode;
    className?: string;
    onClick?: () => void;
    'aria-current'?: 'page';
    to?: unknown;
    search?: unknown;
  }) => (
    <a className={className} onClick={onClick} aria-current={ariaCurrent}>{children}</a>
  ),
  Outlet: () => null,
  useNavigate: () => vi.fn(),
  useMatchRoute: () => () => false,
  useMatches: () => [],
}));
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ hostedMode: false, user: null, currentPersona: null, signOut: vi.fn() }),
}));
vi.mock('@/hooks/use-board-summary', () => ({
  useBoardSummary: () => ({ data: { total: 0, new_today: 0, kinds: [] } }),
}));
vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/ui/sonner', () => ({ Toaster: () => null }));

import { AppShell } from './app-shell';
import { LaneTabs } from '@/features/board/lane-tabs';
import type { BoardParams } from '@/components/board/board-state';

const keepSearch = () => (prev: BoardParams) => prev;

describe('how the nav reaches find work', () => {
  it('keeps Find work in the drawer as a sub-entry under The board', () => {
    render(<AppShell />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the menu' }));

    const nav = document.querySelector('.qb-drawer-nav') as HTMLElement;
    expect(nav).toBeTruthy();
    const items = Array.from(nav.querySelectorAll('a, button')).map((el) => el.textContent);
    // directly under The board, so the pair reads as one group
    expect(items.indexOf('Find work')).toBe(items.findIndex((t) => t?.startsWith('The board')) + 1);
    const link = within(nav).getByText('Find work').closest('a');
    expect(link?.className).toContain('qb-nav-sub');
  });

  it('gives the phone stub bar one board door, no Find work stub', () => {
    render(<AppShell />);

    const stubbar = screen.getByLabelText('Main');
    expect(within(stubbar).getByText('The board')).toBeTruthy();
    expect(within(stubbar).queryByText('Find work')).toBeNull();
  });

  it('puts both workflows on the board lane switcher', () => {
    render(<LaneTabs kindKey="all" searchFor={keepSearch} />);

    const tabs = screen.getByLabelText('Workflows');
    expect(within(tabs).getByText('Side quests')).toBeTruthy();
    expect(within(tabs).getByText('Find work')).toBeTruthy();
  });

  it('marks the active lane from the kind in the URL', () => {
    render(<LaneTabs kindKey="work" searchFor={keepSearch} />);
    expect(screen.getByText('Find work').getAttribute('aria-current')).toBe('page');
    expect(screen.getByText('Side quests').getAttribute('aria-current')).toBeNull();
    cleanup();

    render(<LaneTabs kindKey="all" searchFor={keepSearch} />);
    expect(screen.getByText('Side quests').getAttribute('aria-current')).toBe('page');
    expect(screen.getByText('Find work').getAttribute('aria-current')).toBeNull();
  });
});
