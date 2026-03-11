import { useQuery } from '@tanstack/react-query';
import { getDashboardStats, getScoreDistribution, getRecommendations, getSources, getFunnel } from '@/api/analytics';

export function useDashboardStats() {
  return useQuery({
    queryKey: ['analytics', 'stats'],
    queryFn: () => getDashboardStats(),
  });
}

export function useScoreDistribution() {
  return useQuery({
    queryKey: ['analytics', 'score-distribution'],
    queryFn: () => getScoreDistribution(),
  });
}

export function useRecommendations() {
  return useQuery({
    queryKey: ['analytics', 'recommendations'],
    queryFn: () => getRecommendations(),
  });
}

export function useSources() {
  return useQuery({
    queryKey: ['analytics', 'sources'],
    queryFn: () => getSources(),
  });
}

export function useFunnel() {
  return useQuery({
    queryKey: ['analytics', 'funnel'],
    queryFn: () => getFunnel(),
  });
}
