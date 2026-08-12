import { useIsMutating, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  connectAgent,
  decideRoleProposal,
  disconnectAgent,
  getAgentClients,
  getAgentProgress,
  getRoleProposals,
  runAgent,
} from '@/api/agent';

const AGENT_CLIENTS_KEY = ['agent-clients'] as const;
const ROLE_PROPOSALS_KEY = ['role-proposals'] as const;
const AGENT_RUN_KEY = ['agent-run'] as const;

/** Read which MCP assistants are installed and connected. */
export function useAgentClients() {
  return useQuery({
    queryKey: AGENT_CLIENTS_KEY,
    queryFn: getAgentClients,
  });
}

/** Wire Questboard's local MCP server into an assistant (a human action). */
export function useConnectAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (client: string) => connectAgent(client),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGENT_CLIENTS_KEY }),
  });
}

/** Remove Questboard's MCP server from an assistant. */
export function useDisconnectAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (client: string) => disconnectAgent(client),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: AGENT_CLIENTS_KEY }),
  });
}

/** Run the connected assistant headlessly (app drives it; user never opens it).
 *  Long-running (~1 min); the caller shows progress and renders the result. */
export function useRunAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: AGENT_RUN_KEY,
    mutationFn: ({ task, client }: { task?: string; client?: string } = {}) => runAgent(task, client),
    onSettled: () => {
      void queryClient.refetchQueries({ queryKey: ROLE_PROPOSALS_KEY, type: 'active' });
    },
  });
}

/** Shared truth for the headless assistant run, so the board cannot keep an
 *  old "no jobs added" line visible while the primary button is refreshing. */
export function useAgentRunActive(): boolean {
  return useIsMutating({ mutationKey: AGENT_RUN_KEY }) > 0;
}

/** Poll the running assistant's real progress. Enabled only while a run is in
 *  flight, so an idle board makes no requests. */
export function useAgentProgress(running: boolean) {
  return useQuery({
    queryKey: ['agent-progress'],
    queryFn: getAgentProgress,
    enabled: running,
    refetchInterval: running ? 2000 : false,
    gcTime: 0,
  });
}

export function useRoleProposals(enabled = true) {
  return useQuery({
    queryKey: ROLE_PROPOSALS_KEY,
    queryFn: getRoleProposals,
    enabled,
  });
}

export function useDecideRoleProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) =>
      decideRoleProposal(id, accept),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ROLE_PROPOSALS_KEY }),
        queryClient.invalidateQueries({ queryKey: AGENT_CLIENTS_KEY }),
      ]);
    },
  });
}
