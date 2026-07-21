// @vitest-environment jsdom
/* Find Work is one of the two co-equal workflows, so it gets a standing
   door in the drawer nav and on the phone stub bar, independent of how
   many career rows happen to be live. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import type { ReactNode } from 'react';

afterEach(cleanup);

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, className, onClick }: { children: ReactNode; className?: string; onClick?: () => void }) => (
    <a className={className} onClick={onClick}>{children}</a>
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

describe('the find work nav doors', () => {
  it('gives the drawer a standing Find work entry', () => {
    render(<AppShell />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the menu' }));

    const nav = document.querySelector('.qb-drawer-nav');
    expect(nav).toBeTruthy();
    expect(within(nav as HTMLElement).getByText('Find work')).toBeTruthy();
  });

  it('gives the phone stub bar a Find work stub', () => {
    render(<AppShell />);

    const stubbar = screen.getByLabelText('Main');
    expect(within(stubbar).getByText('Find work')).toBeTruthy();
  });
});
