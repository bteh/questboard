import { apiGet } from '@/lib/api-client';
import type { DashboardStats, ChartDataPoint } from '@/types/analytics';

export function getDashboardStats(profile?: string, searchRunId?: string): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/analytics/stats', { profile, search_run_id: searchRunId });
}

export function getScoreDistribution(profile?: string, searchRunId?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/score-distribution', { profile, search_run_id: searchRunId });
}

export function getRecommendations(profile?: string, searchRunId?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/recommendations', { profile, search_run_id: searchRunId });
}

export function getSources(profile?: string, searchRunId?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/sources', { profile, search_run_id: searchRunId });
}

export function getFunnel(profile?: string, searchRunId?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/funnel', { profile, search_run_id: searchRunId });
}
