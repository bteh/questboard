import type { AgentClientStatus } from '@/types/resume';

/* Decisions for the "suggest roles from my resume" panel. No hooks, no
   network, so the branches are pinned by plain tests. */

export type SuggestPanelState = 'hidden' | 'connect' | 'resume' | 'ready';

export function pickAssistant(clients: AgentClientStatus[]): AgentClientStatus | null {
  return clients.find((client) => client.connected) ?? null;
}

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
  if (!input.consentGranted) return `Allow resume access and suggest roles`;
  return `Suggest roles from my resume with ${input.assistantName}`;
}
