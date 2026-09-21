// @vitest-environment jsdom
/* Sep 21 2026 multi-model review, two defects in the suggest-roles panel:
   1. lastRun was cleared only when a new run started, so after a proposal
      was accepted or dismissed the old run's outcome note came back under
      an empty panel ("Finished, but nothing new to suggest.").
   2. The copy-prompt path fired the intent mark and forgot it, so a failed
      mark was silent and the pasted answer could wait out the quiet week. */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { toast } from 'sonner';

const claudeCode = { id: 'claude', name: 'Claude Code', installed: true, connected: true, restart_required: false };
const claudeDesktop = { id: 'claude_desktop', name: 'Claude Desktop', installed: true, connected: true, restart_required: false };
const clientsQuery = { data: { clients: [claudeCode] } };
type Proposal = { id: number; status: string; proposed_roles: string[]; proposed_keywords: string[]; rationale: string };
const proposal: Proposal = { id: 7, status: 'pending', proposed_roles: ['Data Analyst'], proposed_keywords: [], rationale: '' };
const proposalsQuery = { data: { proposals: [] as Proposal[] } };
const runMutate = vi.fn();
const decideMutate = vi.fn();
const consentMutate = vi.fn();
const intentMutateAsync = vi.fn(async () => undefined);

vi.mock('@/hooks/use-agent-clients', () => ({
  useAgentClients: () => clientsQuery,
  useRunAgent: () => ({ mutate: runMutate, isPending: false }),
  useAgentRunActive: () => false,
  useAgentProgress: () => ({ data: undefined }),
  useRoleProposals: () => proposalsQuery,
  useDecideRoleProposal: () => ({ mutate: decideMutate, isPending: false }),
  useMarkAgentIntent: () => ({ mutate: vi.fn(), mutateAsync: intentMutateAsync, isPending: false }),
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

import { PROPOSE_ROLES_PROMPT } from './suggest-roles-logic';
import { SuggestRolesPanel } from './suggest-roles-panel';

const finishedRun = { ok: true, result: '', error: '', cost_usd: null, num_turns: 3 };
const decided = {
  id: 7,
  status: 'accepted',
  proposed_roles: ['Data Analyst'],
  proposed_keywords: [],
  roles: ['Data Analyst'],
  keywords: [],
  decided_at: null,
};

type Opts<T> = { onSuccess?: (value: T) => void };

/* a run that finished with an empty answer while its proposal is pending:
   the note is hidden because the card speaks for itself */
function renderAfterFinishedRun() {
  proposalsQuery.data = { proposals: [proposal] };
  runMutate.mockImplementation((_vars: unknown, opts: Opts<typeof finishedRun>) => opts.onSuccess?.(finishedRun));
  decideMutate.mockImplementation((_vars: unknown, opts: Opts<typeof decided>) => opts.onSuccess?.(decided));
  const view = render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /suggest roles and keywords from my resume/i }));
  expect(screen.queryByText(/nothing new to suggest/i)).toBeNull();
  return view;
}

afterEach(() => {
  cleanup();
  clientsQuery.data = { clients: [claudeCode] };
  proposalsQuery.data = { proposals: [] };
  runMutate.mockReset();
  decideMutate.mockReset();
  intentMutateAsync.mockReset();
  vi.mocked(toast.error).mockReset();
});

describe('the outcome note after a decision', () => {
  it.each([
    ['accepts', /use these/i],
    ['dismisses', /not now/i],
  ])('stays gone when the person %s the proposal', (_verb, name) => {
    const { rerender } = renderAfterFinishedRun();
    fireEvent.click(screen.getByRole('button', { name }));
    proposalsQuery.data = { proposals: [] };
    rerender(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    expect(screen.queryByText(/nothing new to suggest/i)).toBeNull();
  });
});

describe('the copy-prompt path', () => {
  function stubClipboard() {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    return writeText;
  }

  it('still copies the prompt and says so when the intent mark fails', async () => {
    clientsQuery.data = { clients: [claudeDesktop] };
    intentMutateAsync.mockRejectedValueOnce(new Error('backend down'));
    const writeText = stubClipboard();
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /copy prompt for claude desktop/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PROPOSE_ROLES_PROMPT));
    expect(toast.error).toHaveBeenCalledWith(
      "Couldn't tell the app you asked; the suggestion may wait out the quiet week.",
    );
    expect(screen.getByRole('button', { name: /copied/i })).toBeTruthy();
  });

  it('stays quiet when the mark lands', async () => {
    clientsQuery.data = { clients: [claudeDesktop] };
    const writeText = stubClipboard();
    render(<SuggestRolesPanel resumeExists onAccepted={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /copy prompt for claude desktop/i }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(PROPOSE_ROLES_PROMPT));
    expect(intentMutateAsync).toHaveBeenCalledWith('propose_roles');
    expect(toast.error).not.toHaveBeenCalled();
  });
});
