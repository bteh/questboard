// @vitest-environment jsdom
/* The desktop/local shell must never mount on a dead session. When the
   local bootstrap fails, workspace-context sets error but app.tsx used to
   branch only on hostedMode, so the shell rendered and every call 401ed
   silently. This pins the local error screen: what happened, "Quit and
   reopen Questboard", and the raw detail behind a fold. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const workspace = {
  hostedMode: false,
  isAuthenticated: false,
  isLoading: false,
  error: null as string | null,
};

vi.mock('@/contexts/workspace-context', () => ({
  useWorkspace: () => workspace,
}));
vi.mock('@/features/shell/app-shell', () => ({
  AppShell: () => <div data-testid="shell" />,
}));
vi.mock('@/components/auth/hosted-auth-screen', () => ({
  HostedAuthScreen: () => <div data-testid="hosted-auth" />,
}));
vi.mock('./__root', () => ({ Route: {} }));
vi.mock('@tanstack/react-router', () => ({
  createRoute: (options: unknown) => options,
}));
vi.mock('@/lib/entry', () => ({ markEntered: () => {} }));

import { AppLayout } from './app';

afterEach(() => {
  cleanup();
  workspace.hostedMode = false;
  workspace.isAuthenticated = false;
  workspace.isLoading = false;
  workspace.error = null;
});

describe('the app layout in local mode', () => {
  it('renders the shell when the local session bootstrapped', () => {
    render(<AppLayout />);
    expect(screen.getByTestId('shell')).toBeTruthy();
  });

  it('replaces the shell with a plain error screen when bootstrap failed', () => {
    workspace.error = 'ECONNREFUSED 127.0.0.1:8765';
    render(<AppLayout />);

    expect(screen.queryByTestId('shell')).toBeNull();
    expect(screen.getByText(/Quit and reopen Questboard/)).toBeTruthy();
    expect(screen.getByText('ECONNREFUSED 127.0.0.1:8765')).toBeTruthy();
    expect(document.querySelector('details')).toBeTruthy();
  });

  it('offers a retry that reloads the app', () => {
    workspace.error = 'boom';
    const reload = vi.fn();
    const original = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...original, reload },
    });
    try {
      render(<AppLayout />);
      fireEvent.click(screen.getByRole('button', { name: /try again/i }));
      expect(reload).toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', { configurable: true, value: original });
    }
  });
});

describe('the app layout in hosted mode', () => {
  it('still shows the auth screen, not the local error screen', () => {
    workspace.hostedMode = true;
    workspace.error = 'hosted bootstrap failed';
    render(<AppLayout />);

    expect(screen.getByTestId('hosted-auth')).toBeTruthy();
    expect(screen.queryByText(/Quit and reopen Questboard/)).toBeNull();
  });
});
