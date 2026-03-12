import { useQuery } from '@tanstack/react-query';
import { getDashboardStats, getScoreDistribution, getRecommendations, getSources, getFunnel } from '@/api/analytics';
import { useProfile } from '@/contexts/profile-context';

export function useDashboardStats() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['analytics', 'stats', profile],
    queryFn: () => getDashboardStats(profile),
  });
}

export function useScoreDistribution() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['analytics', 'score-distribution', profile],
    queryFn: () => getScoreDistribution(profile),
  });
}

export function useRecommendations() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['analytics', 'recommendations', profile],
    queryFn: () => getRecommendations(profile),
  });
}

export function useSources() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['analytics', 'sources', profile],
    queryFn: () => getSources(profile),
  });
}

export function useFunnel() {
  const { profile } = useProfile();
  return useQuery({
    queryKey: ['analytics', 'funnel', profile],
    queryFn: () => getFunnel(profile),
  });
}
