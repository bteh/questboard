import type { AgentClientStatus, AgentRunResult } from '@/types/resume';

/* Decisions for the "suggest roles and keywords from my resume" panel. No
   hooks, no network, so the branches are pinned by plain tests. */

export type SuggestPanelState = 'hidden' | 'connect' | 'resume' | 'ready';

/** Only Claude Code has a print mode the app can drive; the others need a
 *  prompt pasted into their own window. */
export function canRunHeadless(client: AgentClientStatus): boolean {
  return client.id === 'claude';
}

export function pickAssistant(clients: AgentClientStatus[]): AgentClientStatus | null {
  const connected = clients.filter((client) => client.connected);
  return connected.find(canRunHeadless) ?? connected[0] ?? null;
}

/** What a person pastes into Claude Desktop or Codex to get the same proposal
 *  the in-app run asks Claude Code for. */
export const PROPOSE_ROLES_PROMPT =
  'Use my local Questboard tools: read my resume, look at my saved target roles and keywords, then call propose_career_preferences with 6 to 10 target roles I should search and 10 to 15 keywords (tools, technologies, and domain terms from my resume that a job posting would mention). For roles: keep the saved ones that fit, add adjacent titles I might not think of, and match my real seniority. If my resume has no professional title in the field I want, I am breaking in: propose entry-level and adjacent titles only, never senior or manager titles. Do not save anything; I will accept the proposal in Questboard.';

export function panelState(input: {
  desktop: boolean;
  clients: AgentClientStatus[];
  resumeExists: boolean;
}): SuggestPanelState {
  // The headless run only exists in the desktop app.
  if (!input.desktop) return 'hidden';
  if (!pickAssistant(input.clients)) return 'connect';
  if (!input.resumeExists) return 'resume';
  return 'ready';
}

export function suggestButtonLabel(input: {
  assistantName: string;
  consentGranted: boolean;
  running: boolean;
}): string {
  if (input.running) return `Asking ${input.assistantName}…`;
  if (!input.consentGranted) return 'Allow resume access and suggest roles and keywords';
  return `Suggest roles and keywords from my resume with ${input.assistantName}`;
}

const OUTCOME_MAX_CHARS = 280;

/** What to say under the button once a run has finished. A failed run is
 *  reported by the toast, and a pending proposal speaks for itself, so this
 *  only fills the silence when the assistant finished with nothing to accept. */
export function runOutcomeNote(result: AgentRunResult, pendingCount: number): string | null {
  if (!result.ok || pendingCount > 0) return null;
  const answer = result.result.replace(/\s+/g, ' ').trim();
  if (!answer) return 'Finished, but nothing new to suggest.';
  if (answer.length <= OUTCOME_MAX_CHARS) return answer;
  return `${answer.slice(0, OUTCOME_MAX_CHARS - 1).trimEnd()}…`;
}
