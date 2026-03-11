import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getLLMStatus, updateLLMConfig, testLLMConnection, getLLMPresets,
  fetchProviderModels, getProfilePreferences, updateProfilePreferences,
} from '@/api/settings';
import { useProfile } from '@/contexts/profile-context';
import type { LLMConfig, ProfilePreferences } from '@/types/settings';

/** Dev mode shows internal/proxy presets. Auto-enabled on localhost, or manually via localStorage. */
function isDevMode(): boolean {
  try {
    if (localStorage.getItem('launchboard-dev-mode') === 'true') return true;
    const host = window.location.hostname;
    return host === 'localhost' || host === '127.0.0.1' || host === '0.0.0.0';
  } catch { return false; }
}

export function useLLMStatus() {
  return useQuery({
    queryKey: ['settings', 'llm'],
    queryFn: getLLMStatus,
  });
}

export function useUpdateLLM() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: LLMConfig) => updateLLMConfig(config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'llm'] });
    },
  });
}

export function useTestConnection() {
  return useMutation({
    mutationFn: () => testLLMConnection(),
  });
}

export function useLLMPresets() {
  const devMode = isDevMode();
  return useQuery({
    queryKey: ['settings', 'llm', 'presets', devMode],
    queryFn: () => getLLMPresets(devMode),
  });
}

/**
 * Fetch live model list from a provider's /models endpoint.
 * Only runs when both base_url and api_key are provided (or provider doesn't need a key).
 */
export function useProviderModels(baseUrl: string, apiKey: string, enabled: boolean) {
  return useQuery({
    queryKey: ['settings', 'llm', 'models', baseUrl, apiKey],
    queryFn: () => fetchProviderModels(baseUrl, apiKey),
    enabled: enabled && !!baseUrl,
    staleTime: 5 * 60 * 1000, // cache for 5 minutes
    retry: false,
  });
}

export function useProfilePreferences() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['settings', 'preferences', profile],
    queryFn: () => getProfilePreferences(profile),
  });
}

export function useUpdateProfilePreferences() {
  const { profile } = useProfile();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prefs: ProfilePreferences) => updateProfilePreferences(profile, prefs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'preferences'] });
    },
  });
}
