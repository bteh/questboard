import { useQuery } from '@tanstack/react-query';
import { getBoardSummary } from '@/api/board';

/** Live per-kind supply for the board rail and the drawer's nav counts. */
export function useBoardSummary() {
  return useQuery({
    queryKey: ['board-summary'],
    queryFn: getBoardSummary,
    staleTime: 60_000,
  });
}
