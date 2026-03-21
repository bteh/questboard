import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  bootstrapWorkspaceSession,
  getOnboardingState,
  saveWorkspacePreferences,
  suggestLocations,
  startOnboardingSearch,
  uploadWorkspaceResume,
} from '@/api/workspace';
import type { WorkspacePreferences } from '@/types/workspace';

export function useBootstrapWorkspace() {
  return useMutation({
    mutationFn: () => bootstrapWorkspaceSession(),
  });
}

export function useOnboardingState(enabled = true) {
  return useQuery({
    queryKey: ['workspace', 'onboarding'],
    queryFn: getOnboardingState,
    enabled,
    staleTime: 60_000, // invalidated on preference save / resume upload
  });
}

export function useSaveWorkspacePreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (preferences: WorkspacePreferences) => saveWorkspacePreferences(preferences),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace', 'onboarding'] });
      queryClient.invalidateQueries({ queryKey: ['search', 'defaults'] });
    },
  });
}

export function useStartOnboardingSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (preferences: WorkspacePreferences) => startOnboardingSearch(preferences),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace', 'onboarding'] });
      queryClient.invalidateQueries({ queryKey: ['search', 'defaults'] });
      queryClient.invalidateQueries({ queryKey: ['search'] });
    },
  });
}

export function useUploadWorkspaceResume() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadWorkspaceResume(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workspace', 'onboarding'] });
      queryClient.invalidateQueries({ queryKey: ['search', 'defaults'] });
    },
  });
}

export function useLocationSuggestions(query: string, enabled = true) {
  return useQuery({
    queryKey: ['workspace', 'locations', query],
    queryFn: () => suggestLocations(query),
    enabled: enabled && query.trim().length >= 2,
    staleTime: 30_000,
  });
}
