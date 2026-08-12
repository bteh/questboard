import { useQuery } from '@tanstack/react-query';
import { getBoardSummary, type BoardSummaryFilters } from '@/api/board';
import { localTimeZone } from '@/lib/time-zone';

/** Live per-kind supply for the board rail and the drawer's nav counts.
    Pass the board's active filters so the rail badges and the "All quests"
    total come from the same predicates as the filtered list; no filters =
    the bare whole-board summary (the drawer's global counts). */
export function useBoardSummary(filters?: BoardSummaryFilters) {
  const localFilters: BoardSummaryFilters = {
    timezone_name: localTimeZone(),
    ...(filters ?? {}),
  };
  return useQuery({
    queryKey: ['board-summary', localFilters],
    queryFn: () => getBoardSummary(localFilters),
    staleTime: 60_000,
    // A desktop window can stay open across midnight. Re-read the calendar
    // boundary so "new today" rolls over without requiring an app restart.
    refetchInterval: 60_000,
  });
}
