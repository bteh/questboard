import { useQuery } from '@tanstack/react-query';
import { getSystemHealth } from '@/api/health';

/**
 * Fetch the unified system health (backend, AI, resume, search, keychain).
 * 10s staleTime — refreshes automatically when things change without
 * burning too many requests.
 */
export function useSystemHealth(enabled = true) {
  return useQuery({
    queryKey: ['health', 'system'],
    queryFn: getSystemHealth,
    enabled,
    staleTime: 10 * 1000,
    refetchOnWindowFocus: true,
  });
}
