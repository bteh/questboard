/* The rail's tiles. Most lanes are one registry kind; Small jobs folds odd,
   skill, and deliver into one tile where the first of them sits in registry
   order. Career rows never make a tile, and a lane with nothing live stays
   off the rail, except ALWAYS_SHOWN_LANES: Part-time is searched near your
   place, so it shows at 0 and a refresh fills it. */

import type { KindSummary } from '@/api/board';
import {
  SMALL_JOBS_KEY,
  isCareerKind,
  isSmallJobsKind,
} from '@/features/board/kind-params';

export interface RailLane {
  id: string;
  label: string;
  sub: string;
  /** the kind whose hand-drawn stamp marks the tile */
  stamp: string;
  count: number;
  new_today: number;
}

export const SMALL_JOBS_LABEL = 'Small jobs';
const SMALL_JOBS_SUB = 'odd jobs, gigs, delivery';
export const ALWAYS_SHOWN_LANES: ReadonlySet<string> = new Set(['parttime']);

export function railLanes(kinds: readonly KindSummary[]): RailLane[] {
  const lanes: RailLane[] = [];
  let small: RailLane | null = null;
  for (const kind of kinds) {
    if (isCareerKind(kind.id)) continue;
    if (isSmallJobsKind(kind.id)) {
      if (!small) {
        small = {
          id: SMALL_JOBS_KEY,
          label: SMALL_JOBS_LABEL,
          sub: SMALL_JOBS_SUB,
          stamp: 'odd',
          count: 0,
          new_today: 0,
        };
        lanes.push(small);
      }
      small.count += kind.count;
      small.new_today += kind.new_today;
      continue;
    }
    lanes.push({
      id: kind.id,
      label: kind.label,
      sub: kind.sub,
      stamp: kind.id,
      count: kind.count,
      new_today: kind.new_today,
    });
  }
  return lanes.filter((lane) => lane.count > 0 || ALWAYS_SHOWN_LANES.has(lane.id));
}
