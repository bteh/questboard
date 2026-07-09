// @vitest-environment jsdom
/* The drawer contract: hidden by default, the hamburger opens it, and all
   three exits work (the X, the scrim, Escape). Local mode shows the
   local-first card instead of an account. */

import { describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

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
  useBoardSummary: () => ({ data: { total: 941, new_today: 38, kinds: [] } }),
}));
vi.mock('@/components/ui/tooltip', () => ({
  TooltipProvider: ({ children }: { children: ReactNode }) => <>{children}</>,
}));
vi.mock('@/components/ui/sonner', () => ({ Toaster: () => null }));

import { AppShell } from './app-shell';

function menuState() {
  return document.querySelector('.qb-app')?.getAttribute('data-menu');
}

describe('the app shell drawer', () => {
  it('starts closed and opens from the hamburger', () => {
    render(<AppShell />);
    expect(menuState()).toBe('closed');

    const fold = screen.getByRole('button', { name: 'Open the menu' });
    expect(fold.getAttribute('aria-expanded')).toBe('false');
    fireEvent.click(fold);

    expect(menuState()).toBe('open');
    expect(fold.getAttribute('aria-expanded')).toBe('true');
    cleanup();
  });

  it('closes from the X, the scrim, and Escape', () => {
    render(<AppShell />);
    const fold = screen.getByRole('button', { name: 'Open the menu' });

    fireEvent.click(fold);
    fireEvent.click(screen.getByRole('button', { name: 'Close the menu' }));
    expect(menuState()).toBe('closed');

    fireEvent.click(fold);
    fireEvent.click(screen.getByTestId('qb-scrim'));
    expect(menuState()).toBe('closed');

    fireEvent.click(fold);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(menuState()).toBe('closed');
    cleanup();
  });

  it('shows the live board count and the local-first card', () => {
    render(<AppShell />);
    fireEvent.click(screen.getByRole('button', { name: 'Open the menu' }));

    expect(screen.getByText('941 up')).toBeTruthy();
    expect(screen.getByText('Local workspace')).toBeTruthy();
    expect(screen.getByText('everything stays on this machine')).toBeTruthy();
    expect(screen.getByText(/pinned here, it's real/)).toBeTruthy();
    cleanup();
  });
});
