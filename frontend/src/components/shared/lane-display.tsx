/* Display adapters for rows from ANY registry lane on the pre-kinds
   surfaces (home, log). Those pages were built on the legacy six-vertical
   design system (Stamp, PostmarkStamp, the verticals record); rows from
   newer lanes (house, odd, flip, body, lookafter, think) reach them the
   moment they are clipped. Legacy verticals keep their original art;
   newer lanes draw their KIND's postmark, label, and hue, so a bank
   bonus never masquerades as a career job. Migrate-on-touch: when these
   pages move to KindStamp wholesale, this module retires. */

import { kindForVertical } from '@questboard/kinds';
import {
  KindStamp,
  PostmarkStamp,
  Stamp,
  cx,
  verticals,
  type Vertical,
} from '@questboard/ui';

const LEGACY_UI: ReadonlySet<string> = new Set(Object.keys(verticals));

// eslint-disable-next-line react-refresh/only-export-components
export function isLegacyUiVertical(v: string): v is Vertical {
  return LEGACY_UI.has(v);
}

export interface LaneDisplay {
  label: string;
  hue: string;
  bandClass: string;
}

/** Label, hue, and band styling for any lane. */
// eslint-disable-next-line react-refresh/only-export-components
export function laneDisplay(v: string): LaneDisplay {
  if (isLegacyUiVertical(v)) return verticals[v];
  const kind = kindForVertical(v);
  return {
    label: kind?.label ?? 'Quest',
    hue: kind?.hue ?? verticals.career.hue,
    bandClass: 'sage',
  };
}

export function LaneStamp({
  vertical,
  size,
  inheritColor,
}: {
  vertical: string;
  size: number;
  inheritColor?: boolean;
}) {
  if (isLegacyUiVertical(vertical)) {
    return <Stamp vertical={vertical} size={size} inheritColor={inheritColor} />;
  }
  const kind = kindForVertical(vertical);
  return (
    <KindStamp
      kind={kind?.id ?? 'odd'}
      size={size}
      color={inheritColor ? 'currentColor' : undefined}
    />
  );
}

export function LanePostmark({ vertical, press }: { vertical: string; press?: boolean }) {
  if (isLegacyUiVertical(vertical)) {
    return <PostmarkStamp vertical={vertical} press={press} />;
  }
  const kind = kindForVertical(vertical);
  return (
    <KindStamp
      kind={kind?.id ?? 'odd'}
      className={cx('qb-postmark', press && 'qb-press')}
    />
  );
}
