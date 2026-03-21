import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getLLMStatus, updateLLMConfig, testLLMConnection, getLLMPresets,
  fetchProviderModels, detectOllama, getProfiles, getProfilePreferences, updateProfilePreferences,
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
    staleTime: 2 * 60 * 1000, // only changes when user saves settings
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
    staleTime: 60 * 60 * 1000, // presets are static
  });
}

/**
 * Fetch live model list from a provider's /models endpoint.
 * Only runs when both base_url and api_key are provided (or provider doesn't need a key).
 */
export function useProviderModels(baseUrl: string, apiKey: string, enabled: boolean) {
  // Hash the key for the cache key — never store the raw key in React Query state
  const keyHint = apiKey ? `key-${apiKey.length}` : 'no-key';
  return useQuery({
    queryKey: ['settings', 'llm', 'models', baseUrl, keyHint],
    queryFn: () => fetchProviderModels(baseUrl, apiKey),
    enabled: enabled && !!baseUrl,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

/**
 * Detect Ollama running on localhost. Only enabled when no LLM is configured.
 */
export function useDetectOllama(enabled: boolean) {
  return useQuery({
    queryKey: ['settings', 'llm', 'detect-ollama'],
    queryFn: detectOllama,
    enabled,
    staleTime: 30 * 1000,
    retry: false,
  });
}

/**
 * Detect OpenAI-compatible AI servers on common localhost ports.
 * Runs directly from the browser so it works in both local and hosted mode.
 */
export function useDetectLocalAI(enabled: boolean) {
  return useQuery({
    queryKey: ['settings', 'llm', 'detect-local-browser'],
    queryFn: async () => {
      const ports = [8317, 8741, 1234, 3456, 5001, 4000];
      const results = await Promise.allSettled(
        ports.map(async (port) => {
          const base = `http://localhost:${port}/v1`;
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 1500);
          try {
            const resp = await fetch(`${base}/models`, { signal: controller.signal });
            clearTimeout(timeout);
            if (!resp.ok) return null;
            const data = await resp.json();
            const models = (data.data || []).map((m: { id?: string }) => m.id).filter(Boolean) as string[];
            if (models.length === 0) return null;
            return { port, base_url: base, model: models[0], models: models.slice(0, 10), label: `AI server` };
          } catch {
            clearTimeout(timeout);
            return null;
          }
        }),
      );
      const servers = results
        .map((r) => (r.status === 'fulfilled' ? r.value : null))
        .filter((s): s is NonNullable<typeof s> => s !== null);
      return { servers };
    },
    enabled,
    staleTime: 30 * 1000,
    retry: false,
  });
}

export function useProfiles() {
  return useQuery({
    queryKey: ['settings', 'profiles'],
    queryFn: getProfiles,
    staleTime: 60 * 60 * 1000,
  });
}

export function useProfilePreferences() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['settings', 'preferences', profile],
    queryFn: () => getProfilePreferences(profile),
    staleTime: 2 * 60 * 1000,
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
