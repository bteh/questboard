import { kindById } from '@questboard/kinds';

/* Hand-drawn postmark stamps, one per quest kind. The shared arc reads as a
   postmark; the inner glyph names the kind. These stay hand-drawn on
   purpose; utility icons elsewhere come from Hugeicons. */

const ARC =
  'M17 2.6 A14.4 14.4 0 1 1 6.5 6.1';
const ARC_DASH =
  'M4.8 8.3 A14.4 14.4 0 0 1 15.2 2.7';

const GLYPHS: Record<string, string> = {
  skill:
    'M14 9.2 l1.3 3.5 3.5 1.3 -3.5 1.3 -1.3 3.5 -1.3 -3.5 -3.5 -1.3 3.5 -1.3z',
  think:
    'M9.4 10.6 h11.2 a1.6 1.6 0 0 1 1.6 1.6 v5.4 a1.6 1.6 0 0 1 -1.6 1.6 h-6.4 l-3.4 3 v-3 h-1.4 a1.6 1.6 0 0 1 -1.6 -1.6 v-5.4 a1.6 1.6 0 0 1 1.6 -1.6 z M12.4 14.9 l1.9 1.9 3.5 -3.7',
  perform:
    'M11.6 9 h4.8 v0 a2.4 2.4 0 0 1 2.4 2.4 v3.4 a2.4 2.4 0 0 1 -4.8 0 v-3.4 a2.4 2.4 0 0 1 2.4 -2.4 z M9.3 14.6 a4.7 4.7 0 0 0 9.4 0 M14 19.4 v2.4',
  audience:
    'M9.6 13.4 a1.8 1.8 0 1 0 3.6 0 a1.8 1.8 0 1 0 -3.6 0 M8.2 19.8 a3.2 3.2 0 0 1 6.4 0 M14.8 12.4 a1.8 1.8 0 1 0 3.6 0 a1.8 1.8 0 1 0 -3.6 0 M13.4 18.8 a3.2 3.2 0 0 1 6.4 0',
  odd:
    'M8.5 12.4 h11 v7.2 a1 1 0 0 1 -1 1 h-9 a1 1 0 0 1 -1 -1 z M8.5 12.4 L14 9.4 L19.5 12.4 M14 12.4 v8.2',
  flip:
    'M9.2 12.1 l6.6 -1.8 a1.3 1.3 0 0 1 1.6 .9 l2 7.4 a1.3 1.3 0 0 1 -.9 1.6 l-6.6 1.8 a1.3 1.3 0 0 1 -1.6 -.9 l-2 -7.4 a1.3 1.3 0 0 1 .9 -1.6 z',
  deliver:
    'M8.4 15.6 a5.6 5.6 0 1 0 11.2 0 a5.6 5.6 0 1 0 -11.2 0 M11.2 15.6 h5.4 M14.5 13.1 l2.6 2.5 -2.6 2.5',
  lookafter:
    'M14 20.6 C7.4 16.2 9 11 12.4 11 c1.2 0 1.6 .9 1.6 .9 s.4 -.9 1.6 -.9 c3.4 0 5 5.2 -1.6 9.6z',
  house:
    'M8.6 15.6 a5.4 5.4 0 1 0 10.8 0 a5.4 5.4 0 1 0 -10.8 0 M14 12 v7.2 M12.3 13.4 h2.7 a1.3 1.3 0 0 1 0 2.6 h-2 a1.3 1.3 0 0 0 0 2.6 h2.7',
  body:
    'M14 9.2 C10.4 13.8 10.4 16.7 12.2 18.6 a3.4 3.4 0 0 0 5.1 -0.2 c1.6 -2 1.2 -4.8 -3.3 -9.2z',
  party:
    'M11.1 9.4 h5.8 v10.6 a1 1 0 0 1 -1 1 h-3.8 a1 1 0 0 1 -1 -1 z',
  speak:
    'M10.2 13.2 l7.4 -3.6 v10.4 l-7.4 -3.6 z M10.2 13.2 h-1.8 v3.2 h1.8 M10.6 16.4 l1 3.8 h2',
  pitch:
    'M8.8 14.8 l11.4 -5 -3.6 10.6 -3 -3.6 -4.8 -2 z M13.6 16.8 l6.6 -7',
  work:
    'M8.6 12.2 h10.8 a1 1 0 0 1 1 1 v6 a1 1 0 0 1 -1 1 h-10.8 a1 1 0 0 1 -1 -1 v-6 a1 1 0 0 1 1 -1 z M11.7 12.2 v-1.1 a1.3 1.3 0 0 1 1.3 -1.3 h2 a1.3 1.3 0 0 1 1.3 1.3 v1.1 M7.6 15.6 h12.8',
};

export interface KindStampProps {
  kind: string;
  size?: number;
  /** overrides the kind's own hue, e.g. '#fff' on dark tiles */
  color?: string;
  className?: string;
}

export function KindStamp({ kind, size = 24, color, className }: KindStampProps) {
  const meta = kindById(kind);
  const stroke = color ?? meta?.hue ?? 'currentColor';
  const glyph = GLYPHS[kind] ?? GLYPHS.odd;
  return (
    <svg
      viewBox="0 0 28 28"
      width={size}
      height={size}
      fill="none"
      stroke={stroke}
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d={ARC} />
      <path d={ARC_DASH} strokeDasharray="3 2.4" />
      <path d={glyph} />
    </svg>
  );
}
