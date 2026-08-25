// @vitest-environment jsdom
/* When /agent/clients fails, the tab used to render a silent blank
   (isLoading false, empty list). This pins the error branch: plain copy
   plus a retry that refetches. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

const clientsQuery = {
  data: undefined as { clients: { id: string; name: string; installed: boolean; connected: boolean }[] } | undefined,
  isLoading: false,
  isError: false,
  error: null as unknown,
  refetch: vi.fn(),
};

vi.mock('@/hooks/use-agent-clients', () => ({
  useAgentClients: () => clientsQuery,
  useConnectAgent: () => ({ mutate: vi.fn(), isPending: false, variables: undefined }),
  useDisconnectAgent: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/hooks/use-agent-consent', () => ({
  useAgentConsent: () => ({ data: { granted: false }, isLoading: false }),
  useSetAgentConsent: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/platform', () => ({ isDesktopApp: () => true }));
vi.mock('@/lib/open-external', () => ({ openExternal: vi.fn() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={String(to)}>{children}</a>,
}));

import { AssistantTab } from './AssistantTab';

afterEach(() => {
  cleanup();
  clientsQuery.data = undefined;
  clientsQuery.isLoading = false;
  clientsQuery.isError = false;
  clientsQuery.error = null;
  clientsQuery.refetch = vi.fn();
});

describe('the assistant tab when the clients call fails', () => {
  it('shows plain error copy with the reason, never a blank', () => {
    clientsQuery.isError = true;
    clientsQuery.error = new Error('Questboard could not reach its background service.');
    render(<AssistantTab />);

    expect(screen.getByText(/could not check this Mac for assistants/i)).toBeTruthy();
    expect(screen.getByText(/could not reach its background service/i)).toBeTruthy();
  });

  it('retries the check on click', () => {
    clientsQuery.isError = true;
    clientsQuery.error = new Error('boom');
    render(<AssistantTab />);

    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(clientsQuery.refetch).toHaveBeenCalled();
  });
});

describe('the assistant tab when the clients call works', () => {
  it('still lists assistants', () => {
    clientsQuery.data = {
      clients: [{ id: 'claude', name: 'Claude Code', installed: true, connected: false }],
    };
    render(<AssistantTab />);
    expect(screen.getByText('Claude Code')).toBeTruthy();
    expect(screen.queryByText(/could not check this Mac/i)).toBeNull();
  });
});
