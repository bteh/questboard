/**
 * The quest-kind registry. kinds.json is the single source of truth;
 * this wrapper only adds types and lookups. The Python side
 * (src/job_finder/kinds.py) reads the same file, and sync tests on both
 * sides pin the contract.
 */
import raw from '../kinds.json';

export interface KindFacet {
  id: string;
  label: string;
  /** the words the API matches against a row's title and description */
  terms: string[];
}

export interface Kind {
  id: string;
  label: string;
  /** the small example line under the label ("focus groups, user tests") */
  sub: string;
  hue: string;
  order: number;
  /** historical DB `vertical` values this kind absorbs at read time */
  legacy_verticals: string[];
  /** the kind's own sub-filters; [] for kinds without any */
  facets: KindFacet[];
}

type RawKind = Omit<Kind, 'facets'> & { facets?: KindFacet[] };

export const KINDS: readonly Kind[] = (raw.kinds as RawKind[])
  .map((k) => ({ ...k, facets: k.facets ?? [] }))
  .sort((a, b) => a.order - b.order);

export const KIND_IDS: readonly string[] = KINDS.map((k) => k.id);

const byId = new Map(KINDS.map((k) => [k.id, k]));

/** legacy vertical value -> kind; kind ids map to themselves */
const toKind = new Map<string, Kind>();
for (const kind of KINDS) {
  toKind.set(kind.id, kind);
  for (const legacy of kind.legacy_verticals) toKind.set(legacy, kind);
}

export function kindById(id: string): Kind | undefined {
  return byId.get(id);
}

/** Resolve a stored vertical value (legacy or kind id) to its kind. */
export function kindForVertical(vertical: string): Kind | undefined {
  return toKind.get(vertical);
}

/** Every stored value a kind answers to, for API queries against old rows. */
export function verticalValuesFor(kindId: string): string[] {
  const kind = byId.get(kindId);
  if (!kind) return [];
  return [kind.id, ...kind.legacy_verticals];
}

/** A kind's facets ([] when it has none); legacy spellings resolve too. */
export function facetsFor(kindId: string): KindFacet[] {
  return toKind.get(kindId)?.facets ?? [];
}
