import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import {
  getWorkspaceCompanies,
  addWorkspaceCompany,
  removeWorkspaceCompany,
} from '@/api/workspace-companies';
import type { WatchlistAddPayload } from '@/api/watchlist';

/* One source of truth: these hit the workspace target-companies store the pull
   reads (build_pipeline_config_override), NOT the default.yaml profile
   watchlist. Onboarding state is invalidated too so the Search-defaults pointer
   ("managed in the Companies tab") reflects a change right away. */

const COMPANIES_KEY = ['workspace', 'companies'] as const;

export function useWorkspaceCompanies() {
  return useQuery({
    queryKey: COMPANIES_KEY,
    queryFn: getWorkspaceCompanies,
  });
}

export function useAddWorkspaceCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: WatchlistAddPayload) => addWorkspaceCompany(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: COMPANIES_KEY });
      queryClient.invalidateQueries({ queryKey: ['workspace', 'onboarding'] });
    },
  });
}

export function useRemoveWorkspaceCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => removeWorkspaceCompany(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: COMPANIES_KEY });
      queryClient.invalidateQueries({ queryKey: ['workspace', 'onboarding'] });
    },
  });
}
