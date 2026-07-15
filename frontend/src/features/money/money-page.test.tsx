// @vitest-environment jsdom
/* The money page contract: the heading and every claim of the payment
   constitution render, and the drawer carries a door to the page. */

import { describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children, className, onClick }: { children: ReactNode; className?: string; onClick?: () => void }) => (
    <a className={className} onClick={onClick}>{children}</a>
  ),
}));
vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => ({ hostedMode: false, user: null, currentPersona: null, signOut: vi.fn() }),
}));
vi.mock('@/hooks/use-board-summary', () => ({
  useBoardSummary: () => ({ data: { total: 941, new_today: 38, kinds: [] } }),
}));

import { MoneyPage } from './money-page';
import { Drawer } from '../shell/drawer';

describe('the money page', () => {
  it('renders the heading and the five claims', () => {
    render(<MoneyPage />);

    expect(screen.getByRole('heading', { name: 'How we make money' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'The board is free' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'The people listed here never pay us' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'You can pay us' })).toBeTruthy();
    expect(screen.getByRole('heading', { name: 'Some side-quest links may carry a referral' })).toBeTruthy();
    expect(
      screen.getByRole('heading', { name: 'One sponsor, clearly marked' }),
    ).toBeTruthy();

    expect(screen.getByText(/never a subscription dressed up as one/)).toBeTruthy();
    expect(screen.getByText(/the poster says so right next to it/)).toBeTruthy();
    expect(screen.getByText(/job listings never carry one/)).toBeTruthy();
    cleanup();
  });

  it('has a door in the drawer', () => {
    render(
      <Drawer
        open
        onClose={() => {}}
        onHome={false}
        onBoard={false}
        onLog={false}
        onSettings={false}
        onHealth={false}
        onMoney={false}
      />,
    );
    expect(screen.getByText('How we make money')).toBeTruthy();
    cleanup();
  });
});
