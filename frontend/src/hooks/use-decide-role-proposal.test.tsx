// @vitest-environment jsdom
/* Real case (Sep 9 2026): "Use these" stayed busy for about ten seconds.
   Accepting a proposal waited on a refetch of the assistant-status query,
   which has nothing to do with the decision. Accepting refreshes the
   proposals only. */
import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  decideRoleProposal: vi.fn(),
}));

vi.mock('@/api/agent', () => ({
  decideRoleProposal: mocks.decideRoleProposal,
  getAgentClients: vi.fn(),
  connectAgent: vi.fn(),
  disconnectAgent: vi.fn(),
  runAgent: vi.fn(),
  getAgentProgress: vi.fn(),
  getRoleProposals: vi.fn(),
  markAgentIntent: vi.fn(),
}));

import { useDecideRoleProposal } from './use-agent-clients';

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { invalidate, rendered: renderHook(() => useDecideRoleProposal(), { wrapper }) };
}

beforeEach(() => {
  mocks.decideRoleProposal.mockReset();
  mocks.decideRoleProposal.mockResolvedValue({
    id: 7,
    status: 'accepted',
    proposed_roles: ['Data Platform Manager'],
    proposed_keywords: ['dbt'],
    roles: ['Data Platform Manager'],
    keywords: ['Snowflake', 'dbt'],
    decided_at: null,
  });
});

describe('useDecideRoleProposal', () => {
  it('refreshes the proposals and nothing else after a decision', async () => {
    const { invalidate, rendered } = setup();

    await act(async () => {
      await rendered.result.current.mutateAsync({ id: 7, accept: true });
    });

    const keys = invalidate.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(['role-proposals']));
    expect(keys).not.toContain(JSON.stringify(['agent-clients']));
  });
});
