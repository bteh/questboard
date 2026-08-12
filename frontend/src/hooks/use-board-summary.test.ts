/* The summary query must carry the board's active filters: keyed by them
   (so a filter change refetches) and passed to the API (so the rail counts
   come from the same predicates as the list). No filters = the bare
   whole-board summary the drawer's nav counts use. */

import { describe, expect, it, vi } from 'vitest';

const useQueryMock = vi.hoisted(() =>
  vi.fn((options: { queryKey: unknown[]; queryFn: () => unknown }) => options),
);
vi.mock('@tanstack/react-query', () => ({ useQuery: useQueryMock }));

const getBoardSummaryMock = vi.hoisted(() => vi.fn());
vi.mock('@/api/board', () => ({ getBoardSummary: getBoardSummaryMock }));
vi.mock('@/lib/time-zone', () => ({ localTimeZone: () => 'America/Los_Angeles' }));

import { useBoardSummary } from './use-board-summary';

describe('useBoardSummary', () => {
  it('keys the query by the active board filters and passes them through', () => {
    const filters = { search: 'seat', location: 'Chicago', salary_max: 90000 };
    useBoardSummary(filters);

    const options = useQueryMock.mock.calls.at(-1)![0];
    const localFilters = { timezone_name: 'America/Los_Angeles', ...filters };
    expect(options.queryKey).toEqual(['board-summary', localFilters]);
    options.queryFn();
    expect(getBoardSummaryMock).toHaveBeenCalledWith(localFilters);
  });

  it('stays the bare whole-board summary when no filters are given', () => {
    useBoardSummary();

    const options = useQueryMock.mock.calls.at(-1)![0];
    const localFilters = { timezone_name: 'America/Los_Angeles' };
    expect(options.queryKey).toEqual(['board-summary', localFilters]);
    options.queryFn();
    expect(getBoardSummaryMock).toHaveBeenCalledWith(localFilters);
  });
});
