import { apiGet, apiPost } from '@/lib/api-client';
import type { AgentClientStatus, AgentRunResult } from '@/types/resume';

/** MCP assistants (Claude Code, Codex): installed on this machine + whether
 *  Questboard's local MCP server is wired into each. Desktop-only in practice. */
export function getAgentClients(): Promise<{ clients: AgentClientStatus[] }> {
  return apiGet<{ clients: AgentClientStatus[] }>('/agent/clients');
}

export function connectAgent(client: string): Promise<AgentClientStatus> {
  return apiPost<AgentClientStatus>('/agent/connect', { client });
}

export function disconnectAgent(client: string): Promise<AgentClientStatus> {
  return apiPost<AgentClientStatus>('/agent/disconnect', { client });
}

/** Run the connected assistant once, headlessly, to do the AI step in-app.
 *  The user never opens their agent; the app drives it over the local MCP. */
export function runAgent(task = 'find_and_rank', client = 'claude'): Promise<AgentRunResult> {
  return apiPost<AgentRunResult>('/agent/run', { client, task });
}
