// @vitest-environment jsdom
/* The Search defaults "suggest roles" panel: the assistant proposes, the
   person accepts, and only then do the roles in the form change. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

const clientsQuery = { data: { clients: [{ id: 'claude', name: 'Claude Code', installed: true, connected: true, restart_required: false }] } };
const proposalsQuery = { data: { proposals: [] as { id: number; status: string; proposed_roles: string[]; rationale: string }[] } };
const runMutate = vi.fn();
const decideMutate = vi.fn();
const consentMutate = vi.fn();

vi.mock('@/hooks/use-agent-clients', () => ({
  useAgentClients: () => clientsQuery,
  useRunAgent: () => ({ mutate: runMutate, isPending: false }),
  useAgentRunActive: () => false,
  useAgentProgress: () => ({ data: undefined }),
  useRoleProposals: () => proposalsQuery,
  useDecideRoleProposal: () => ({ mutate: decideMutate, isPending: false }),
}));
vi.mock('@/hooks/use-agent-consent', () => ({
  useAgentConsent: () => ({ data: { granted: true }, isLoading: false }),
  useSetAgentConsent: () => ({ mutate: consentMutate, isPending: false }),
}));
vi.mock('@/lib/platform', () => ({ isDesktopApp: () => true }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, children }: { to: string; children: ReactNode }) => <a href={String(to)}>{children}</a>,
}));

import { SuggestRolesPanel } from './suggest-roles-panel';

afterEach(() => {
  cleanup();
  proposalsQuery.data = { proposals: [] };
  runMutate.mockReset();
  decideMutate.mockReset();
});

describe('SuggestRolesPanel', () => {
  it('runs the propose_roles task with the connected assistant', () => {
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /suggest roles from my resume with claude code/i }));
    expect(runMutate).toHaveBeenCalledTimes(1);
    expect(runMutate.mock.calls[0][0]).toEqual({ task: 'propose_roles', client: 'claude' });
  });

  it('shows a pending proposal and applies it only when the person accepts', () => {
    proposalsQuery.data = {
      proposals: [{ id: 7, status: 'pending', proposed_roles: ['Data Analyst', 'IT Support Specialist'], rationale: 'Entry-level fits.' }],
    };
    decideMutate.mockImplementation((_vars: unknown, opts: { onSuccess?: () => void }) => opts.onSuccess?.());
    const onAccepted = vi.fn();
    render(<SuggestRolesPanel resumeExists onAccepted={onAccepted} />);
    expect(screen.getByText('Data Analyst')).toBeTruthy();
    expect(onAccepted).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: /use these roles/i }));
    expect(decideMutate.mock.calls[0][0]).toEqual({ id: 7, accept: true });
    expect(onAccepted).toHaveBeenCalledWith(['Data Analyst', 'IT Support Specialist']);
  });

  it('points at the Resume tab when no resume is uploaded yet', () => {
    render(<SuggestRolesPanel resumeExists={false} onAccepted={vi.fn()} />);
    expect(screen.getByText(/upload your resume/i)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /suggest roles/i })).toBeNull();
  });
});
