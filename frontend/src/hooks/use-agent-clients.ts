import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { connectAgent, disconnectAgent, getAgentClients, runAgent } from '@/api/agent';

const AGENT_CLIENTS_KEY = ['agent-clients'] as const;

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
  return useMutation({
    mutationFn: ({ task, client }: { task?: string; client?: string } = {}) => runAgent(task, client),
  });
}
