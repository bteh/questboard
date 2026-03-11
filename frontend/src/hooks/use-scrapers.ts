import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { getScraperSources, type ScraperSource } from '@/api/scrapers';

/** Format a raw source key into a readable label (offline fallback). */
export function formatSourceKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Pure helper — build labels map from API data, no hooks. */
export function buildSourceLabels(data: ScraperSource[] | undefined): Record<string, string> {
  if (!data) return {};
  return Object.fromEntries(data.map((s) => [s.name, s.display_name]));
}

/** Look up a source label, falling back to a formatted key. */
export function resolveSourceLabel(key: string, labels?: Record<string, string>): string {
  return labels?.[key] || formatSourceKey(key);
}

export function useScraperSources() {
  return useQuery({
    queryKey: ['scrapers', 'sources'],
    queryFn: getScraperSources,
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}

export function useSourceLabels(): Record<string, string> {
  const { data } = useScraperSources();
  return useMemo(() => buildSourceLabels(data), [data]);
}
