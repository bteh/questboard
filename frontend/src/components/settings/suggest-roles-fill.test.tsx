// @vitest-environment jsdom
/* Real case (Brian, Sep 9 2026): he connected Claude Code, clicked Suggest,
   watched a spinner for 70 seconds, and nothing appeared. Rules pinned here:
   the wait says how long it usually takes, a finished run always says what
   happened, and a proposal fills keywords as well as roles. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';

const claudeCode = { id: 'claude', name: 'Claude Code', installed: true, connected: true, restart_required: false };
const claudeDesktop = { id: 'claude_desktop', name: 'Claude Desktop', installed: true, connected: true, restart_required: false };
const clientsQuery = { data: { clients: [claudeCode] } };
type Proposal = {
  id: number;
  status: string;
  proposed_roles: string[];
  proposed_keywords: string[];
  rationale: string;
};
const proposalsQuery = { data: { proposals: [] as Proposal[] } };
const runMutate = vi.fn();
const decideMutate = vi.fn();
const consentMutate = vi.fn();
const intentMutate = vi.fn();
let running = false;

vi.mock('@/hooks/use-agent-clients', () => ({
  useAgentClients: () => clientsQuery,
  useRunAgent: () => ({ mutate: runMutate, isPending: running }),
  useAgentRunActive: () => running,
  useAgentProgress: () => ({ data: running ? { steps: [], phase: 'Reading your resume' } : undefined }),
  useRoleProposals: () => proposalsQuery,
  useDecideRoleProposal: () => ({ mutate: decideMutate, isPending: false }),
  useMarkAgentIntent: () => ({ mutate: intentMutate, isPending: false }),
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
  clientsQuery.data = { clients: [claudeCode] };
  proposalsQuery.data = { proposals: [] };
  running = false;
  runMutate.mockReset();
  decideMutate.mockReset();
  intentMutate.mockReset();
  Object.defineProperty(navigator, 'clipboard', { value: { writeText: vi.fn().mockResolvedValue(undefined) }, configurable: true });
});

describe('SuggestRolesPanel fills roles and keywords', () => {
  it('shows proposed keywords and applies the saved roles and keywords the decision returns', () => {
    proposalsQuery.data = {
      proposals: [
        {
          id: 7,
          status: 'pending',
          proposed_roles: ['Data Engineering Manager', 'Data Platform Manager'],
          proposed_keywords: ['Airflow', 'dbt'],
          rationale: 'Two titles, two tools.',
        },
      ],
    };
    decideMutate.mockImplementation((_vars: unknown, opts: { onSuccess?: (decision: unknown) => void }) =>
      opts.onSuccess?.({
        id: 7,
        status: 'accepted',
        proposed_roles: ['Data Engineering Manager', 'Data Platform Manager'],
        proposed_keywords: ['Airflow', 'dbt'],
        roles: ['Data Engineering Manager', 'Data Platform Manager'],
        keywords: ['Snowflake', 'Airflow', 'dbt'],
        decided_at: null,
      }),
    );
    const onAccepted = vi.fn();
    render(<SuggestRolesPanel resumeExists onAccepted={onAccepted} />);

    expect(screen.getByText('Airflow')).toBeTruthy();
    expect(screen.getByText('dbt')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: /use these/i }));
    expect(decideMutate.mock.calls[0][0]).toEqual({ id: 7, accept: true });
    expect(onAccepted).toHaveBeenCalledWith({
      roles: ['Data Engineering Manager', 'Data Platform Manager'],
      keywords: ['Snowflake', 'Airflow', 'dbt'],
    });
  });

  it('says how long the wait usually is while the assistant runs', () => {
    running = true;
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    expect(screen.getByText(/usually about a minute/i)).toBeTruthy();
    expect(screen.getByText(/reading your resume/i)).toBeTruthy();
  });

  it('shows what the assistant said when a run ends with nothing to accept', () => {
    runMutate.mockImplementation((_vars: unknown, opts: { onSuccess?: (result: unknown) => void }) =>
      opts.onSuccess?.({
        ok: true,
        result: 'Your saved roles already match your resume, so I proposed nothing new.',
        error: '',
        cost_usd: null,
        num_turns: 3,
      }),
    );
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /suggest roles and keywords from my resume/i }));
    expect(screen.getByText(/proposed nothing new/i)).toBeTruthy();
  });

  it('marks the pasted-prompt path as asked for by the person', async () => {
    clientsQuery.data = { clients: [claudeDesktop] };
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /copy prompt for claude desktop/i }));
    await Promise.resolve();
    expect(intentMutate).toHaveBeenCalledTimes(1);
    expect(intentMutate.mock.calls[0][0]).toEqual('propose_roles');
  });
});
