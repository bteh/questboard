/* Whether the one "Get new jobs" button can rank as well as pull: the user
   is on the desktop app, their local Claude is installed, and they've granted
   resume access. Off the desktop the assistant never runs, so ready is false
   without touching the queries. The same conditions the old ranking door
   used, now in one place both the button and its receipt read. */

import { useAgentClients } from '@/hooks/use-agent-clients';
import { useAgentConsent } from '@/hooks/use-agent-consent';
import { isDesktopApp } from '@/lib/platform';

export interface AssistantReady {
  /** the local Claude is installed and consent is granted */
  ready: boolean;
  /** running inside the Tauri desktop shell, where the agent can spawn */
  isDesktop: boolean;
  /** the clients or consent queries are still loading */
  loading: boolean;
}

export function useAssistantReady(): AssistantReady {
  const clients = useAgentClients();
  const consent = useAgentConsent();
  const isDesktop = isDesktopApp();

  if (!isDesktop) return { ready: false, isDesktop: false, loading: false };

  const loading = clients.isLoading || consent.isLoading;
  // Claude only: the backend's run_headless rejects codex (see
  // agent_integration_service.py); codex users get the pasteable prompt in
  // Settings > Assistant instead.
  const claude = clients.data?.clients.find((c) => c.id === 'claude');
  const ready = (claude?.installed ?? false) && (consent.data?.granted ?? false);
  return { ready, isDesktop, loading };
}
