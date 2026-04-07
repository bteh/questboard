import {
  createManualPlace,
  normalizePlaceList,
  type WorkplacePreference,
} from '@/lib/profile-preferences';
import type { SearchDefaults, SearchRequest, SearchRunSnapshot } from '@/types/search';
import type { PlaceSelection, WorkspacePreferences } from '@/types/workspace';

export interface SearchFormSeed {
  rolesText: string;
  keywordsText: string;
  companies: string[];
  preferredPlaces: PlaceSelection[];
  workplacePreference: WorkplacePreference;
  maxDaysOld: number;
  includeLinkedInJobs: boolean;
}

export interface SearchAreaDefaults {
  preferredPlaces: PlaceSelection[];
  workplacePreference: WorkplacePreference;
  maxDaysOld: number;
  includeLinkedInJobs: boolean;
}

export interface SearchSnapshotMetadata {
  currentTitle: string;
  currentLevel: string;
  currentTc: number | null;
  minBase: number | null;
  targetTotalComp: number | null;
  minAcceptableTc: number | null;
  compensationCurrency: 'USD' | string;
  compensationPeriod: 'hourly' | 'monthly' | 'annual';
  includeEquity: boolean | null;
  excludeStaffingAgencies: boolean | null;
}

export function parseMultilineSearchInput(value: string): string[] {
  return value.split('\n').map((item) => item.trim()).filter(Boolean);
}

function placeSyncKey(place: PlaceSelection): string {
  return [
    place.label.trim().toLowerCase(),
    place.match_scope,
    place.city.trim().toLowerCase(),
    place.region.trim().toLowerCase(),
    place.country.trim().toLowerCase(),
  ].join('|');
}

export function samePlaceSelections(a: PlaceSelection[], b: PlaceSelection[]): boolean {
  const left = normalizePlaceList(a).map(placeSyncKey).sort();
  const right = normalizePlaceList(b).map(placeSyncKey).sort();
  return JSON.stringify(left) === JSON.stringify(right);
}

export function buildSearchFormSeed(searchDefaults: SearchDefaults | null | undefined): SearchFormSeed | null {
  if (!searchDefaults) return null;

  const rolesText = searchDefaults.roles?.length
    ? searchDefaults.roles.join('\n')
    : (searchDefaults.current_title || '');

  return {
    rolesText,
    keywordsText: searchDefaults.keywords?.join('\n') ?? '',
    companies: searchDefaults.companies ?? [],
    preferredPlaces: normalizePlaceList(
      searchDefaults.preferred_places?.length
        ? searchDefaults.preferred_places
        : (searchDefaults.locations ?? []).map((item) => createManualPlace(item)),
    ),
    workplacePreference: searchDefaults.workplace_preference
      ?? (searchDefaults.include_remote ? 'remote_friendly' : 'location_only'),
    maxDaysOld: searchDefaults.max_days_old ?? 14,
    includeLinkedInJobs: !!searchDefaults.include_linkedin_jobs,
  };
}

export function resolveSavedSearchAreaDefaults(
  searchDefaults: SearchDefaults | null | undefined,
  preferences: WorkspacePreferences | null | undefined,
): SearchAreaDefaults {
  return {
    preferredPlaces: normalizePlaceList(
      searchDefaults?.preferred_places?.length
        ? searchDefaults.preferred_places
        : (preferences?.preferred_places ?? []),
    ),
    workplacePreference: searchDefaults?.workplace_preference
      ?? preferences?.workplace_preference
      ?? 'remote_friendly',
    maxDaysOld: searchDefaults?.max_days_old ?? preferences?.max_days_old ?? 14,
    includeLinkedInJobs: searchDefaults?.include_linkedin_jobs ?? preferences?.include_linkedin_jobs ?? false,
  };
}

export function hasSearchAreaOverride(
  current: SearchAreaDefaults,
  saved: SearchAreaDefaults,
): boolean {
  return current.workplacePreference !== saved.workplacePreference
    || current.maxDaysOld !== saved.maxDaysOld
    || current.includeLinkedInJobs !== saved.includeLinkedInJobs
    || !samePlaceSelections(current.preferredPlaces, saved.preferredPlaces);
}

export function buildSearchRequestFromForm({
  rolesText,
  keywordsText,
  preferredPlaces,
  companies,
  includeRemote,
  workplacePreference,
  maxDaysOld,
  includeLinkedInJobs,
  useAi,
  profile,
  mode,
}: {
  rolesText: string;
  keywordsText: string;
  preferredPlaces: PlaceSelection[];
  companies: string[];
  includeRemote: boolean;
  workplacePreference: WorkplacePreference;
  maxDaysOld: number;
  includeLinkedInJobs: boolean;
  useAi: boolean;
  profile: string;
  mode: SearchRequest['mode'];
}): SearchRequest {
  return {
    roles: parseMultilineSearchInput(rolesText),
    locations: preferredPlaces.map((item) => item.label),
    preferred_places: preferredPlaces,
    keywords: parseMultilineSearchInput(keywordsText),
    companies,
    include_remote: includeRemote,
    workplace_preference: workplacePreference,
    max_days_old: maxDaysOld,
    include_linkedin_jobs: includeLinkedInJobs,
    use_ai: useAi,
    profile,
    mode,
  };
}

export function resolveSearchSnapshotMetadata(
  searchDefaults: SearchDefaults | null | undefined,
  preferences: WorkspacePreferences | null | undefined,
): SearchSnapshotMetadata {
  return {
    currentTitle: searchDefaults?.current_title ?? preferences?.current_title ?? '',
    currentLevel: searchDefaults?.current_level ?? preferences?.current_level ?? '',
    currentTc: searchDefaults?.current_tc ?? preferences?.compensation.current_comp ?? null,
    minBase: searchDefaults?.min_base ?? preferences?.compensation.min_base ?? null,
    targetTotalComp: searchDefaults?.target_total_comp ?? preferences?.compensation.target_total_comp ?? null,
    minAcceptableTc: searchDefaults?.min_acceptable_tc ?? preferences?.compensation.min_acceptable_tc ?? null,
    compensationCurrency: searchDefaults?.compensation_currency ?? preferences?.compensation.currency ?? 'USD',
    compensationPeriod: searchDefaults?.compensation_period ?? preferences?.compensation.pay_period ?? 'annual',
    includeEquity: preferences?.compensation.include_equity ?? null,
    excludeStaffingAgencies: searchDefaults?.exclude_staffing_agencies ?? preferences?.exclude_staffing_agencies ?? null,
  };
}

export function buildSearchSnapshotMetadataFromPreferences(
  preferences: WorkspacePreferences,
): SearchSnapshotMetadata {
  return {
    currentTitle: preferences.current_title,
    currentLevel: preferences.current_level,
    currentTc: preferences.compensation.current_comp,
    minBase: preferences.compensation.min_base,
    targetTotalComp: preferences.compensation.target_total_comp,
    minAcceptableTc: preferences.compensation.min_acceptable_tc,
    compensationCurrency: preferences.compensation.currency,
    compensationPeriod: preferences.compensation.pay_period,
    includeEquity: preferences.compensation.include_equity,
    excludeStaffingAgencies: preferences.exclude_staffing_agencies,
  };
}

export function buildSearchRunSnapshot({
  request,
  profile,
  metadata,
}: {
  request: Pick<
  SearchRequest,
  'mode'
  | 'roles'
  | 'locations'
  | 'keywords'
  | 'companies'
  | 'include_remote'
  | 'workplace_preference'
  | 'max_days_old'
  | 'include_linkedin_jobs'
  | 'use_ai'
  >;
  profile: string;
  metadata: SearchSnapshotMetadata;
}): SearchRunSnapshot {
  return {
    profile,
    mode: request.mode,
    roles: request.roles.length > 0
      ? request.roles
      : (metadata.currentTitle ? [metadata.currentTitle] : ['Resume-derived']),
    locations: request.locations,
    keywords: request.keywords,
    companies: request.companies,
    include_remote: request.include_remote,
    workplace_preference: request.workplace_preference,
    max_days_old: request.max_days_old,
    include_linkedin_jobs: request.include_linkedin_jobs,
    use_ai: request.use_ai,
    current_title: metadata.currentTitle,
    current_level: metadata.currentLevel,
    current_tc: metadata.currentTc,
    min_base: metadata.minBase,
    target_total_comp: metadata.targetTotalComp,
    min_acceptable_tc: metadata.minAcceptableTc,
    compensation_currency: metadata.compensationCurrency,
    compensation_period: metadata.compensationPeriod,
    include_equity: metadata.includeEquity,
    exclude_staffing_agencies: metadata.excludeStaffingAgencies,
  };
}
