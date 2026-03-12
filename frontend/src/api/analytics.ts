import { apiGet } from '@/lib/api-client';
import type { DashboardStats, ChartDataPoint } from '@/types/analytics';

export function getDashboardStats(profile?: string): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/analytics/stats', { profile });
}

export function getScoreDistribution(profile?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/score-distribution', { profile });
}

export function getRecommendations(profile?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/recommendations', { profile });
}

export function getSources(profile?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/sources', { profile });
}

export function getFunnel(profile?: string): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/funnel', { profile });
}
