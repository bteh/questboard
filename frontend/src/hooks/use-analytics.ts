import { useQuery } from '@tanstack/react-query';
import { getDashboardStats, getScoreDistribution, getRecommendations, getSources, getFunnel } from '@/api/analytics';
import { useProfile } from '@/contexts/profile-context';
import { useWorkspace } from '@/contexts/workspace-context';

/** In hosted/workspace mode the backend resolves the workspace from the cookie,
 *  so we intentionally omit the profile query param to avoid stale localStorage values. */
function useEffectiveProfile(): string | undefined {
  const { profile } = useProfile();
  const { hostedMode } = useWorkspace();
  return hostedMode ? undefined : profile;
}

export function useDashboardStats(searchRunId?: string) {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'stats', profile, searchRunId],
    queryFn: () => getDashboardStats(profile, searchRunId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useScoreDistribution(searchRunId?: string) {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'score-distribution', profile, searchRunId],
    queryFn: () => getScoreDistribution(profile, searchRunId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecommendations(searchRunId?: string) {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'recommendations', profile, searchRunId],
    queryFn: () => getRecommendations(profile, searchRunId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSources(searchRunId?: string) {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'sources', profile, searchRunId],
    queryFn: () => getSources(profile, searchRunId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useFunnel(searchRunId?: string) {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'funnel', profile, searchRunId],
    queryFn: () => getFunnel(profile, searchRunId),
    staleTime: 5 * 60 * 1000,
  });
}
