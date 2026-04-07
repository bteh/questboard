import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { startSearchRun, getRunStatus, getSearchDefaults, getSearchRuns, suggestSearchParams } from '@/api/search';
import type { SearchSuggestions } from '@/api/search';
import type { SearchRequest, RunStatus } from '@/types/search';

export function useSearchDefaults(profile: string) {
  return useQuery({
    queryKey: ['search', 'defaults', profile],
    queryFn: () => getSearchDefaults(profile),
    staleTime: 2 * 60 * 1000,
  });
}

export function useSuggestSearch() {
  return useMutation({
    mutationFn: (profile: string) => suggestSearchParams(profile),
  });
}

export type { SearchSuggestions };

export function useStartSearch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: SearchRequest) => startSearchRun(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['search'] });
    },
  });
}

export function useRunStatus(runId: string | null) {
  return useQuery({
    queryKey: ['search', 'status', runId],
    queryFn: () => getRunStatus(runId!),
    enabled: !!runId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === 'completed' || data.status === 'failed')) return false;
      return 2000;
    },
  });
}

export function useSearchRuns(limit = 20) {
  return useQuery({
    queryKey: ['search', 'runs', limit],
    queryFn: () => getSearchRuns(limit),
    staleTime: 30_000,
  });
}

export function pickLatestCompletedRun(runs: RunStatus[] | undefined): RunStatus | null {
  if (!runs || runs.length === 0) return null;
  return runs.find((run) => run.status === 'completed') ?? null;
}
