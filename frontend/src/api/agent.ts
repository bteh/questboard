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

export interface AgentProgressStep {
  tool: string;
  at: string;
  /** the run polls get_refresh_status on a loop; repeats collapse into a count */
  count: number;
}

/** Where the running assistant has actually got to, read from the MCP tool
 *  calls it has made. The run is a separate process with no feed of its own,
 *  so this is polled; the alternative was guessing from a stopwatch. */
export function getAgentProgress(): Promise<{ steps: AgentProgressStep[]; phase: string }> {
  return apiGet<{ steps: AgentProgressStep[]; phase: string }>('/agent/progress');
}

export interface RoleProposal {
  id: number;
  workspace_id: string | null;
  base_roles: string[];
  proposed_roles: string[];
  rationale: string;
  status: string;
  created_at: string | null;
  decided_at: string | null;
}

export interface RoleProposalDecision {
  id: number;
  status: string;
  proposed_roles: string[];
  decided_at: string | null;
}

export function getRoleProposals(): Promise<{ proposals: RoleProposal[] }> {
  return apiGet<{ proposals: RoleProposal[] }>('/agent/role-proposals');
}

export function decideRoleProposal(
  id: number,
  accept: boolean,
): Promise<RoleProposalDecision> {
  return apiPost<RoleProposalDecision>(`/agent/role-proposals/${id}/decide`, { accept });
}
