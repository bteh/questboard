import { apiGet } from '@/lib/api-client';
import type { DashboardStats, ChartDataPoint } from '@/types/analytics';

export function getDashboardStats(): Promise<DashboardStats> {
  return apiGet<DashboardStats>('/analytics/stats');
}

export function getScoreDistribution(): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/score-distribution');
}

export function getRecommendations(): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/recommendations');
}

export function getSources(): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/sources');
}

export function getFunnel(): Promise<ChartDataPoint[]> {
  return apiGet<ChartDataPoint[]>('/analytics/funnel');
}
