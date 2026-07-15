/* The board's filter state, serialized two ways and pinned by
   board-state.test.ts:
   - URL search params (?v, ?q, ?place, ?from, ?to, ?p) so a filtered board is a
     shareable address and back/forward walks filter changes;
   - localStorage at questboard:board.v1 so Tuesday's board is already set
     up on Wednesday. Params beat saved state: the board route redirects a
     bare /board to the saved params once, then the URL is the only truth.
   Storage access follows lib/entry.ts: every read and write in try/catch,
   a locked-down browser just gets the default board. */

import { normalizeKindKey, type KindKey } from '@/features/board/kind-params';

export const BOARD_STATE_KEY = 'questboard:board.v1';
export const BOARD_NOTICE_KEY = 'questboard:board-notice';

export interface BoardParams {
  /** Kind tag; absent means All. Legacy vertical values normalize on read. */
  v?: KindKey;
  /** Board search text. */
  q?: string;
  /** Place text ("Los Angeles", "NV"); remote and no-place rows always pass. */
  place?: string;
  /** "1" = near me only: with a place set, drop remote/placeless rows. */
  near?: string;
  /** Typed pay floor, as typed ("150k"). */
  from?: string;
  /** Typed pay ceiling, as typed. */
  to?: string;
  /** Active preset keys, comma list ("noexp,remote"). */
  p?: string;
  /** Open job detail sheet (?job=123). Never persisted: a share or refresh
      reopens it from the URL alone. */
  job?: number;
}

/** The persisted shape: the URL params plus the sort toggle. */
export interface SavedBoardState extends BoardParams {
  sort?: 'new' | 'score';
}

function cleanString(value: unknown): string | undefined {
  return typeof value === 'string' && value !== '' ? value : undefined;
}

/** The router may hand ?job=123 back as a number or a string. */
function cleanId(value: unknown): number | undefined {
  const n =
    typeof value === 'number' ? value : typeof value === 'string' ? Number(value) : NaN;
  return Number.isInteger(n) && n > 0 ? n : undefined;
}

export function validateBoardSearch(search: Record<string, unknown>): BoardParams {
  const v = cleanString(search.v);
  return {
    v: normalizeKindKey(v),
    q: cleanString(search.q),
    place: cleanString(search.place),
    // the router may hand back near as the number 1, the string "1", or a
    // boolean, depending on how it round-tripped the URL; treat them alike
    near:
      search.near === '1' || search.near === 1 || search.near === true ? '1' : undefined,
    from: cleanString(search.from),
    to: cleanString(search.to),
    p: cleanString(search.p),
    job: cleanId(search.job),
  };
}

/* job stays out on purpose: a shared ?job link is about the one posting,
   not a filtered board, so it must not block the saved-state redirect
   test in beforeLoad (which skips redirecting when job is set). */
export function hasBoardParams(params: BoardParams): boolean {
  return Boolean(
    params.v || params.q || params.place || params.near || params.from || params.to || params.p,
  );
}

/** ?p= comma list -> the set of keys the board recognizes today. */
export function presetKeysFrom(p: string | undefined, validKeys: string[]): Set<string> {
  if (!p) return new Set();
  return new Set(p.split(',').map((k) => k.trim()).filter((k) => validKeys.includes(k)));
}

/** The set back to ?p=, in the given canonical order; undefined when empty. */
export function presetKeysTo(keys: Set<string>, order: string[]): string | undefined {
  const list = order.filter((k) => keys.has(k));
  return list.length > 0 ? list.join(',') : undefined;
}

export function readSavedBoardState(): SavedBoardState | null {
  try {
    const raw = window.localStorage.getItem(BOARD_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const state: SavedBoardState = validateBoardSearch(parsed);
    if (parsed.sort === 'new' || parsed.sort === 'score') state.sort = parsed.sort;
    return state;
  } catch {
    return null;
  }
}

export function saveBoardState(state: SavedBoardState): void {
  try {
    const compact: Record<string, string> = {};
    for (const key of ['v', 'q', 'place', 'near', 'from', 'to', 'p', 'sort'] as const) {
      const value = state[key];
      if (value) compact[key] = value;
    }
    window.localStorage.setItem(BOARD_STATE_KEY, JSON.stringify(compact));
  } catch {
    /* storage refused: the board still works, it just resets next visit */
  }
}

/* The first-run notice line ("Never done any of this?..."): shown until
   dismissed, dismissal stored locally like the entered flag. */

export function noticeDismissed(): boolean {
  try {
    return window.localStorage.getItem(BOARD_NOTICE_KEY) === '1';
  } catch {
    return false;
  }
}

export function dismissNotice(): void {
  try {
    window.localStorage.setItem(BOARD_NOTICE_KEY, '1');
  } catch {
    /* storage refused: the notice shows again next visit, nothing breaks */
  }
}
