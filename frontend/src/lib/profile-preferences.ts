import {
  LOCATION_OPTIONS,
  type LocationKind,
  type LocationOption,
} from '@/lib/location-catalog';
import type { PlaceSelection, WorkspacePreferences } from '@/types/workspace';

export type WorkplacePreference = 'remote_friendly' | 'remote_only' | 'location_only';

export interface LocationSuggestion {
  label: string;
  kind: LocationKind;
  subtitle: string;
  city?: string;
  region?: string;
  country?: string;
  country_code?: string;
  lat?: number | null;
  lon?: number | null;
  provider?: string;
  provider_id?: string;
}

export const LEVEL_OPTIONS = [
  { value: 'intern', label: 'Intern' },
  { value: 'junior', label: 'Junior' },
  { value: 'associate', label: 'Associate' },
  { value: 'mid', label: 'Mid' },
  { value: 'senior', label: 'Senior' },
  { value: 'staff', label: 'Staff' },
  { value: 'principal', label: 'Principal' },
  { value: 'manager', label: 'Manager' },
  { value: 'director', label: 'Director' },
  { value: 'vp', label: 'VP' },
  { value: 'executive', label: 'Executive' },
] as const;

export const WORKPLACE_OPTIONS = [
  {
    value: 'remote_friendly' as const,
    label: 'Remote + local',
    description: 'Show remote jobs plus jobs in your preferred locations.',
  },
  {
    value: 'remote_only' as const,
    label: 'Remote only',
    description: 'Only show fully remote roles.',
  },
  {
    value: 'location_only' as const,
    label: 'Local only',
    description: 'Only show hybrid or on-site jobs in your preferred locations.',
  },
] as const;

export const REMOTE_LOCATION_VALUES = new Set([
  'remote',
  'anywhere',
  'united states',
  'usa',
  'us',
]);

const STATE_NAME_TO_ABBR: Record<string, string> = {
  alabama: 'AL',
  alaska: 'AK',
  arizona: 'AZ',
  arkansas: 'AR',
  california: 'CA',
  colorado: 'CO',
  connecticut: 'CT',
  delaware: 'DE',
  florida: 'FL',
  georgia: 'GA',
  hawaii: 'HI',
  idaho: 'ID',
  illinois: 'IL',
  indiana: 'IN',
  iowa: 'IA',
  kansas: 'KS',
  kentucky: 'KY',
  louisiana: 'LA',
  maine: 'ME',
  maryland: 'MD',
  massachusetts: 'MA',
  michigan: 'MI',
  minnesota: 'MN',
  mississippi: 'MS',
  missouri: 'MO',
  montana: 'MT',
  nebraska: 'NE',
  nevada: 'NV',
  'new hampshire': 'NH',
  'new jersey': 'NJ',
  'new mexico': 'NM',
  'new york': 'NY',
  'north carolina': 'NC',
  'north dakota': 'ND',
  ohio: 'OH',
  oklahoma: 'OK',
  oregon: 'OR',
  pennsylvania: 'PA',
  'rhode island': 'RI',
  'south carolina': 'SC',
  'south dakota': 'SD',
  tennessee: 'TN',
  texas: 'TX',
  utah: 'UT',
  vermont: 'VT',
  virginia: 'VA',
  washington: 'WA',
  'west virginia': 'WV',
  wisconsin: 'WI',
  wyoming: 'WY',
  'district of columbia': 'DC',
};

const STATE_ABBREVIATIONS = new Set(Object.values(STATE_NAME_TO_ABBR));

function normalizeSearchKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function buildLocationSearchTerms(option: LocationOption): string[] {
  return [
    option.label,
    option.country ?? '',
    option.region ?? '',
    ...(option.aliases ?? []),
  ].filter(Boolean);
}

function toLocationSubtitle(option: LocationOption): string {
  if (option.kind === 'country') return 'Country';
  if (option.kind === 'region') return option.country ? `Region in ${option.country}` : 'Region';
  const parts = [option.region, option.country].filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : 'City';
}

function titleCase(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(' ');
}

function levenshteinDistance(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const matrix = Array.from({ length: rows }, () => Array<number>(cols).fill(0));

  for (let i = 0; i < rows; i += 1) matrix[i][0] = i;
  for (let j = 0; j < cols; j += 1) matrix[0][j] = j;

  for (let i = 1; i < rows; i += 1) {
    for (let j = 1; j < cols; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + cost,
      );
    }
  }

  return matrix[a.length][b.length];
}

function coalesceSplitCityStateEntries(values: string[]): string[] {
  const merged: string[] = [];

  for (let i = 0; i < values.length; i += 1) {
    const current = values[i]?.trim() ?? '';
    const next = values[i + 1]?.trim() ?? '';

    if (
      current
      && next
      && !current.includes(',')
      && /^[A-Za-z]{2}$/.test(next)
      && STATE_ABBREVIATIONS.has(next.toUpperCase())
    ) {
      merged.push(`${current}, ${next.toUpperCase()}`);
      i += 1;
      continue;
    }

    if (current) merged.push(current);
  }

  return merged;
}

function findLocationOption(value: string): LocationOption | undefined {
  const normalized = normalizeSearchKey(value);
  if (!normalized) return undefined;
  return LOCATION_OPTIONS.find((option) =>
    buildLocationSearchTerms(option).some((term) => normalizeSearchKey(term) === normalized),
  );
}

export function isRemoteLocation(value: string): boolean {
  return REMOTE_LOCATION_VALUES.has(value.trim().toLowerCase());
}

export function normalizeLocationInput(value: string): string {
  const trimmed = value.trim().replace(/\s+/g, ' ');
  if (!trimmed) return '';

  const exactOption = findLocationOption(trimmed);
  if (exactOption) return exactOption.label;

  const stateOnly = trimmed.toLowerCase().replace(/\s+state$/, '');
  if (STATE_NAME_TO_ABBR[stateOnly]) {
    return titleCase(stateOnly);
  }

  const parts = trimmed.split(',').map((part) => part.trim()).filter(Boolean);
  if (parts.length === 2) {
    const [cityRaw, stateRaw] = parts;
    const normalizedStateKey = stateRaw.toLowerCase().replace(/\./g, '');
    const stateAbbr = STATE_NAME_TO_ABBR[normalizedStateKey]
      ?? (STATE_ABBREVIATIONS.has(stateRaw.toUpperCase()) ? stateRaw.toUpperCase() : null);
    if (stateAbbr) {
      return `${titleCase(cityRaw)}, ${stateAbbr}`;
    }
  }

  return titleCase(trimmed);
}

export function normalizeLocationList(values: string[]): string[] {
  const cleaned: string[] = [];
  const seen = new Set<string>();

  for (const value of coalesceSplitCityStateEntries(values)) {
    const item = normalizeLocationInput(value);
    if (!item || isRemoteLocation(item)) continue;
    const key = normalizeSearchKey(item);
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push(item);
  }

  return cleaned;
}

export function createManualPlace(label: string): PlaceSelection {
  return {
    label,
    kind: 'manual',
    city: '',
    region: '',
    country: '',
    country_code: '',
    lat: null,
    lon: null,
    provider: 'manual',
    provider_id: '',
  };
}

export function placeLabel(value: Pick<PlaceSelection, 'label'> | string): string {
  return typeof value === 'string' ? value : value.label;
}

export function normalizePlaceSelection(value: PlaceSelection | string): PlaceSelection {
  if (typeof value !== 'string') {
    return {
      ...createManualPlace(normalizeLocationInput(value.label)),
      ...value,
      label: normalizeLocationInput(value.label),
    };
  }
  return createManualPlace(normalizeLocationInput(value));
}

export function normalizePlaceList(values: Array<PlaceSelection | string>): PlaceSelection[] {
  const cleaned: PlaceSelection[] = [];
  const seen = new Set<string>();

  for (const item of values) {
    const normalized = normalizePlaceSelection(item);
    if (!normalized.label || isRemoteLocation(normalized.label)) continue;
    const key = normalizeSearchKey(normalized.label);
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push(normalized);
  }

  return cleaned;
}

export function suggestionToPlace(suggestion: LocationSuggestion): PlaceSelection {
  return {
    label: suggestion.label,
    kind: (suggestion.kind as PlaceSelection['kind']) || 'manual',
    city: suggestion.city || '',
    region: suggestion.region || '',
    country: suggestion.country || '',
    country_code: suggestion.country_code || '',
    lat: suggestion.lat ?? null,
    lon: suggestion.lon ?? null,
    provider: suggestion.provider || 'local',
    provider_id: suggestion.provider_id || suggestion.label,
  };
}

export function buildDefaultWorkspacePreferences(): WorkspacePreferences {
  return {
    roles: [],
    keywords: [],
    preferred_places: [],
    workplace_preference: 'remote_friendly',
    max_days_old: 14,
    current_title: '',
    current_level: 'mid',
    compensation: {
      currency: 'USD',
      pay_period: 'annual',
      current_comp: 100000,
      min_base: 80000,
      target_total_comp: 150000,
      min_acceptable_tc: null,
      include_equity: true,
    },
    exclude_staffing_agencies: true,
  };
}

export function getWorkplacePreferenceLabel(value: WorkplacePreference): string {
  return WORKPLACE_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

export function getLocationSuggestions(query: string, selected: string[] = [], limit = 6): LocationSuggestion[] {
  const trimmed = query.trim();
  if (!trimmed) return [];

  const selectedKeys = new Set(selected.map((item) => normalizeSearchKey(item)));
  const queryKey = normalizeSearchKey(trimmed);

  const directMatches = LOCATION_OPTIONS.filter((option) => {
    const optionKey = normalizeSearchKey(option.label);
    if (selectedKeys.has(optionKey)) return false;
    return buildLocationSearchTerms(option).some((term) => {
      const termKey = normalizeSearchKey(term);
      return termKey.includes(queryKey) || term.toLowerCase().includes(trimmed.toLowerCase());
    });
  });

  if (directMatches.length > 0) {
    return directMatches.slice(0, limit).map((option) => ({
      label: option.label,
      kind: option.kind,
      subtitle: toLocationSubtitle(option),
      city: option.city,
      region: option.region,
      country: option.country,
      country_code: option.country_code,
      provider: 'local',
      provider_id: option.label,
    }));
  }

  return LOCATION_OPTIONS
    .filter((option) => !selectedKeys.has(normalizeSearchKey(option.label)))
    .map((option) => ({
      option,
      distance: Math.min(
        ...buildLocationSearchTerms(option).map((term) =>
          levenshteinDistance(queryKey, normalizeSearchKey(term)),
        ),
      ),
    }))
    .filter((item) => item.distance <= Math.max(2, Math.floor(queryKey.length * 0.35)))
    .sort((a, b) => a.distance - b.distance)
    .slice(0, limit)
    .map(({ option }) => ({
      label: option.label,
      kind: option.kind,
      subtitle: toLocationSubtitle(option),
      city: option.city,
      region: option.region,
      country: option.country,
      country_code: option.country_code,
      provider: 'local',
      provider_id: option.label,
    }));
}
