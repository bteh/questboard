import {
  presetKeysFrom,
  presetKeysTo,
  type BoardParams,
} from '@/components/board/board-state';
import { isCareerKind, type KindKey } from './kind-params';

export interface LaneScopedPreset {
  key: string;
  careerOnly?: boolean;
  questOnly?: boolean;
}

/** Keep filters only while their controls remain visible in the next lane. */
export function kindSearchForLane(
  prev: BoardParams,
  key: KindKey,
  presets: LaneScopedPreset[],
  presetKeys: string[],
): BoardParams {
  const wasCareer = isCareerKind(prev.v ?? 'all');
  const nextCareer = isCareerKind(key);
  let keys = presetKeysFrom(prev.p, presetKeys);
  keys = new Set(
    [...keys].filter((active) => {
      const preset = presets.find((item) => item.key === active);
      return nextCareer ? !preset?.questOnly : !preset?.careerOnly;
    }),
  );

  return {
    ...prev,
    v: key === 'all' ? undefined : key,
    f: (prev.v ?? 'all') === key ? prev.f : undefined,
    p: presetKeysTo(keys, presetKeys),
    src: nextCareer ? prev.src : undefined,
    from: wasCareer === nextCareer ? prev.from : undefined,
    to: wasCareer === nextCareer ? prev.to : undefined,
  };
}
