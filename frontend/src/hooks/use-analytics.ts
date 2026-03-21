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

export function useDashboardStats() {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'stats', profile],
    queryFn: () => getDashboardStats(profile),
    staleTime: 5 * 60 * 1000,
  });
}

export function useScoreDistribution() {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'score-distribution', profile],
    queryFn: () => getScoreDistribution(profile),
    staleTime: 5 * 60 * 1000,
  });
}

export function useRecommendations() {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'recommendations', profile],
    queryFn: () => getRecommendations(profile),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSources() {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'sources', profile],
    queryFn: () => getSources(profile),
    staleTime: 5 * 60 * 1000,
  });
}

export function useFunnel() {
  const profile = useEffectiveProfile();
  return useQuery({
    queryKey: ['analytics', 'funnel', profile],
    queryFn: () => getFunnel(profile),
    staleTime: 5 * 60 * 1000,
  });
}
