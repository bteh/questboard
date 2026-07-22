// @vitest-environment jsdom
/* The drawer contract: hidden by default, the hamburger opens it, and all
   three exits work (the X, the scrim, Escape). Local mode shows the
   local-first card instead of an account. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

afterEach(cleanup);

const navigateMock = vi.hoisted(() => vi.fn());

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, className, onClick }: { children: ReactNode; className?: string; onClick?: () => void }) => (
    <a className={className} onClick={onClick}>{children}</a>
  ),
  Outlet: () => null,
  useNavigate: () => navigateMock,
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

describe('the topbar search box', () => {
  /* A submit must MERGE ?q into the board's current params, not replace
     them: someone on the work lane with a place and a pay floor set stays
     on their lane with their filters when they search. */
  it('merges the query into the existing board params', () => {
    navigateMock.mockClear();
    render(<AppShell />);

    const input = screen.getByLabelText('Search the board');
    fireEvent.change(input, { target: { value: '  editor  ' } });
    fireEvent.submit(input.closest('form')!);

    expect(navigateMock).toHaveBeenCalledTimes(1);
    const call = navigateMock.mock.calls[0][0];
    expect(call.to).toBe('/board');
    /* a functional updater keeps whatever is already in the URL */
    expect(typeof call.search).toBe('function');
    expect(call.search({ v: 'work', place: 'LA', near: '1', src: 'crypto' })).toEqual({
      v: 'work',
      place: 'LA',
      near: '1',
      src: 'crypto',
      q: 'editor',
    });
    cleanup();
  });

  it('an empty submit clears the query but keeps the rest', () => {
    navigateMock.mockClear();
    render(<AppShell />);

    const input = screen.getByLabelText('Search the board');
    fireEvent.submit(input.closest('form')!);

    const call = navigateMock.mock.calls[0][0];
    expect(call.search({ v: 'work', q: 'old' })).toEqual({ v: 'work', q: undefined });
    cleanup();
  });
});
