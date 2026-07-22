import { useQuery } from '@tanstack/react-query';
import { getBoardSummary, type BoardSummaryFilters } from '@/api/board';

/** Live per-kind supply for the board rail and the drawer's nav counts.
    Pass the board's active filters so the rail badges and the "All quests"
    total come from the same predicates as the filtered list; no filters =
    the bare whole-board summary (the drawer's global counts). */
export function useBoardSummary(filters?: BoardSummaryFilters) {
  return useQuery({
    queryKey: ['board-summary', filters ?? {}],
    queryFn: () => getBoardSummary(filters ?? {}),
    staleTime: 60_000,
  });
}
