/* Starts the existing search pipeline from the reader's saved defaults: the
   same request and snapshot the Restock page builds, streamed through the
   shared SearchProvider, so the run keeps going and reporting wherever the
   reader navigates. Nothing new on the backend. */

import { toast } from 'sonner';
import { useProfile } from '@/contexts/profile-context';
import { useSearchContext } from '@/contexts/search-context';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState } from '@/hooks/use-workspace';
import { useSearchDefaults, useStartSearch } from '@/hooks/use-search';
import { getSearchAreaSummary } from '@/lib/search-area';
import {
  buildSearchFormSeed,
  buildSearchRequestFromForm,
  buildSearchRunSnapshot,
  resolveSearchSnapshotMetadata,
} from '@/lib/search-preferences';

export function useRunWorkSearch() {
  const { profile } = useProfile();
  const { data: searchDefaults } = useSearchDefaults(profile);
  const { data: llm } = useLLMStatus();
  const { data: onboarding } = useOnboardingState();
  const startSearch = useStartSearch();
  const { state, activate } = useSearchContext();

  const seed = buildSearchFormSeed(searchDefaults);
  const running = state === 'running';
  const ready = seed !== null && !running && !startSearch.isPending;

  function run() {
    if (!seed || running || startSearch.isPending) return;
    const area = getSearchAreaSummary(seed.workplacePreference, seed.preferredPlaces);
    const eff = area.effectiveWorkplacePreference;
    const request = buildSearchRequestFromForm({
      rolesText: seed.rolesText,
      keywordsText: seed.keywordsText,
      preferredPlaces: seed.preferredPlaces,
      companies: seed.companies,
      includeRemote: eff !== 'location_only',
      workplacePreference: eff,
      maxDaysOld: seed.maxDaysOld,
      includeLinkedInJobs: seed.includeLinkedInJobs,
      matchStrictness: seed.matchStrictness,
      useAi: llm?.available === true,
      profile,
      mode: 'search_score',
    });
    const snapshot = buildSearchRunSnapshot({
      request,
      profile: searchDefaults?.profile ?? profile,
      metadata: resolveSearchSnapshotMetadata(searchDefaults, onboarding?.preferences),
    });
    startSearch.mutate(request, {
      onSuccess: (data) => activate(data.run_id, 'search_score', snapshot),
      onError: (error) => {
        const message = error instanceof Error ? error.message : 'The search did not start';
        if (message.includes('At least one role or keyword')) {
          toast.error('Nothing to search for yet. Add your resume, or set roles on the Restock page.');
          return;
        }
        if (message.includes('At least one location')) {
          toast.error('Add a place in Settings first, or set your saved search to remote.');
          return;
        }
        toast.error(message);
      },
    });
  }

  return { run, ready, running };
}
