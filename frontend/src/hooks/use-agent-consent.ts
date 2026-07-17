import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { getAgentConsent, setAgentConsent } from '@/api/resume';

const AGENT_CONSENT_KEY = ['agent-resume-consent'] as const;

/** Read whether the connected agent may read the local resume. */
export function useAgentConsent() {
  return useQuery({
    queryKey: AGENT_CONSENT_KEY,
    queryFn: getAgentConsent,
  });
}

/** Grant or revoke the connected agent's resume access (a human action). */
export function useSetAgentConsent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (grant: boolean) => setAgentConsent(grant),
    onSuccess: (data) => queryClient.setQueryData(AGENT_CONSENT_KEY, data),
  });
}
