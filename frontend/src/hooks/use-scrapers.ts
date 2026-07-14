import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getScraperSources,
  getScrapeRuns,
  getSourceHealth,
  type ScraperSource,
} from '@/api/scrapers';

/** Format a raw source key into a readable label (offline fallback). */
export function formatSourceKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Pure helper: build labels map from API data, no hooks. */
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
    // wrapped: react-query passes its context object as the first argument,
    // which must not land in getScraperSources' optional vertical param
    queryFn: () => getScraperSources(),
    staleTime: 60 * 60 * 1000, // 1 hour
  });
}

/* Labels cover every vertical: the board shows quest sources too, and the
   career-only default would leave them falling back to slug prettification
   ("Flip Onramps" instead of "Questboard"). Settings keeps the career
   default via useScraperSources above. */
export function useSourceLabels(): Record<string, string> {
  const { data } = useQuery({
    queryKey: ['scrapers', 'sources', 'all'],
    queryFn: () => getScraperSources('all'),
    staleTime: 60 * 60 * 1000,
  });
  return useMemo(() => buildSourceLabels(data), [data]);
}

/* The /health ops page watches these while a restock runs, so both queries
   refetch on a slow heartbeat instead of going stale. */
export function useSourceHealth(days: number) {
  return useQuery({
    queryKey: ['scrapers', 'health', days],
    queryFn: () => getSourceHealth(days),
    refetchInterval: 60_000,
  });
}

export function useScrapeRuns(days: number) {
  return useQuery({
    queryKey: ['scrapers', 'runs', days],
    queryFn: () => getScrapeRuns(days),
    refetchInterval: 60_000,
  });
}
