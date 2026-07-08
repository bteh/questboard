import { useState, useRef, useEffect, useMemo } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { useStartSearch, useSearchDefaults, useSuggestSearch } from '@/hooks/use-search';
import { toast } from 'sonner';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState, useSaveWorkspacePreferences } from '@/hooks/use-workspace';
import { useWorkspace } from '@/contexts/workspace-context';
import { useProfile } from '@/contexts/profile-context';
import { useSearchContext } from '@/contexts/search-context';
import type { FunnelSummary as FunnelSummaryData, MatchStrictness, SearchRequest, SearchRunSnapshot } from '@/types/search';
import { getRunFunnel } from '@/api/search';
import type { PlaceSelection } from '@/types/workspace';
import { useScraperSources, buildSourceLabels } from '@/hooks/use-scrapers';
import {
  createManualPlace,
  normalizePlaceList,
  type WorkplacePreference,
} from '@/lib/profile-preferences';
import {
  deriveWorkplacePreferenceFromPlaces,
  getSearchReadiness,
} from '@/lib/search-readiness';
import { getSearchAreaSummary } from '@/lib/search-area';
import {
  buildSearchFormSeed,
  buildSearchRequestFromForm,
  buildSearchRunSnapshot,
  hasSearchAreaOverride,
  parseMultilineSearchInput,
  resolveSavedSearchAreaDefaults,
  resolveSearchSnapshotMetadata,
} from '@/lib/search-preferences';
import { SearchConfigForm } from '@/components/search/SearchConfigForm';
import { SearchRunView } from '@/components/search/SearchRunView';
import { getStagesForMode } from '@/components/search/search-leaf-helpers';

/* Restock: the old Search page whole, at its verb address. The form, the
   run view, the per-run filter funnel, and the saved-defaults actions all
   moved intact; the search machinery keeps its internal names. Not in the
   sidebar: the board's restock line, the stale states, and Settings are
   the doors in. */

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/restock',
  component: RestockPage,
});

function RestockPage() {
  const SUGGEST_TOAST_ID = 'search-suggest';
  const SEARCH_TOAST_ID = 'search-start';
  const navigate = useNavigate();
  const { profile } = useProfile();
  const { hostedMode } = useWorkspace();
  const { data: searchDefaults, isLoading: configLoading } = useSearchDefaults(profile);
  const { data: llm } = useLLMStatus();
  const { data: onboarding } = useOnboardingState();
  const savePreferences = useSaveWorkspacePreferences();
  const startSearch = useStartSearch();
  const suggest = useSuggestSearch();
  const { state, runId, messages, result, error, mode, progress, snapshot, activate, reset: resetSearch } = useSearchContext();
  const { data: scraperSources } = useScraperSources();
  const sourceLabels = useMemo(() => buildSourceLabels(scraperSources), [scraperSources]);

  const [roles, setRoles] = useState('');
  const [keywords, setKeywords] = useState('');
  const [locations, setLocations] = useState<PlaceSelection[]>([]);
  const [maxDays, setMaxDays] = useState(30);
  const [includeLinkedInJobs, setIncludeLinkedInJobs] = useState(false);
  const [workplacePreference, setWorkplacePreference] = useState<WorkplacePreference>('remote_friendly');
  const [matchStrictness, setMatchStrictness] = useState<MatchStrictness>('balanced');
  const [selectedMode, setSelectedMode] = useState<SearchRequest['mode']>(mode);
  const [showFilters, setShowFilters] = useState(false);
  const [suggestedCompanies, setSuggestedCompanies] = useState<string[]>([]);
  const [funnel, setFunnel] = useState<FunnelSummaryData | null>(null);
  const [funnelDismissed, setFunnelDismissed] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const formSeed = useMemo(() => buildSearchFormSeed(searchDefaults), [searchDefaults]);
  const savedSearchAreaDefaults = useMemo(
    () => resolveSavedSearchAreaDefaults(searchDefaults, onboarding?.preferences),
    [searchDefaults, onboarding?.preferences],
  );
  const snapshotMetadata = useMemo(
    () => resolveSearchSnapshotMetadata(searchDefaults, onboarding?.preferences),
    [searchDefaults, onboarding?.preferences],
  );

  // Pre-fill from saved defaults when config loads
  useEffect(() => {
    if (formSeed) {
      /* eslint-disable react-hooks/set-state-in-effect -- form initialization from async data */
      setRoles(formSeed.rolesText);
      setKeywords(formSeed.keywordsText);
      setSuggestedCompanies(formSeed.companies);
      setLocations(formSeed.preferredPlaces);
      setWorkplacePreference(formSeed.workplacePreference);
      setMaxDays(formSeed.maxDaysOld);
      setIncludeLinkedInJobs(formSeed.includeLinkedInJobs);
      setMatchStrictness(formSeed.matchStrictness);
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [formSeed]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  // Fetch the per-stage filter funnel once the run completes so the user can
  // see why their result count is what it is.
  useEffect(() => {
    if (state !== 'completed' || !runId) {
      return;
    }
    let cancelled = false;
    getRunFunnel(runId)
      .then((data) => {
        if (!cancelled) {
          setFunnel(data);
          setFunnelDismissed(false);
        }
      })
      .catch(() => {
        // Funnel is best-effort; missing data shouldn't break the run view.
      });
    return () => {
      cancelled = true;
    };
  }, [state, runId]);

  // First-run hand-off: when the brand-new user's very first restock lands,
  // ship them straight to the results so they don't get stranded staring at
  // the run log. Only fires once: the flag is set in the onboarding wizard,
  // then cleared here.
  useEffect(() => {
    if (state !== 'completed' || !runId) return;
    let pending: string | null = null;
    try {
      pending = window.localStorage.getItem('questboard:first-run-pending');
    } catch {
      pending = null;
    }
    if (pending !== '1') return;
    try {
      window.localStorage.removeItem('questboard:first-run-pending');
    } catch {
      // ignore
    }
    toast.success('Your first restock is in. Opening your top matches.');
    navigate({
      to: '/log/ledger',
      search: { run: runId, scope: undefined },
    });
  }, [state, runId, navigate]);

  const llmAvailable = llm?.available ?? false;
  const searchAreaSummary = getSearchAreaSummary(workplacePreference, locations);
  const effectiveWorkplacePreference = searchAreaSummary.effectiveWorkplacePreference;
  const includeRemote = effectiveWorkplacePreference !== 'location_only';
  const parsedRoles = parseMultilineSearchInput(roles);
  const parsedKeywords = parseMultilineSearchInput(keywords);
  const canUseResumeFallback = hostedMode && onboarding?.resume.exists === true;
  const isRemoteOnly = effectiveWorkplacePreference === 'remote_only';
  const { usesRemoteFallback, missingLocations, missingSearchTerms } = getSearchReadiness({
    roles: parsedRoles,
    keywords: parsedKeywords,
    locations,
    workplacePreference: effectiveWorkplacePreference,
    allowResumeFallback: canUseResumeFallback,
  });
  const filtersExpanded = showFilters || missingLocations;
  const filterSummary = [
    locations.length > 0
      ? `${locations.length} location${locations.length === 1 ? '' : 's'}`
      : isRemoteOnly
        ? searchAreaSummary.shortLabel
        : usesRemoteFallback
          ? searchAreaSummary.shortLabel
          : null,
    maxDays !== 30 ? `${maxDays} day window` : null,
    includeLinkedInJobs ? 'LinkedIn enabled' : null,
    matchStrictness !== 'balanced' ? `${matchStrictness} matching` : null,
    suggestedCompanies.length > 0 ? `${suggestedCompanies.length} target companies` : null,
  ].filter(Boolean);
  const searchAreaOverridesSavedDefaults = hasSearchAreaOverride(
    {
      preferredPlaces: locations,
      workplacePreference,
      maxDaysOld: maxDays,
      includeLinkedInJobs,
      matchStrictness,
    },
    savedSearchAreaDefaults,
  );

  const applySavedSearchArea = () => {
    setLocations(savedSearchAreaDefaults.preferredPlaces);
    setWorkplacePreference(savedSearchAreaDefaults.workplacePreference);
    setMaxDays(savedSearchAreaDefaults.maxDaysOld);
    setIncludeLinkedInJobs(savedSearchAreaDefaults.includeLinkedInJobs);
    setMatchStrictness(savedSearchAreaDefaults.matchStrictness);
    toast.success('Back to your saved defaults');
  };

  const handleSaveSearchAreaDefaults = () => {
    if (!onboarding?.preferences) {
      toast.error('Settings are still loading. Try again in a moment.');
      return;
    }
    savePreferences.mutate(
      {
        ...onboarding.preferences,
        preferred_places: locations,
        workplace_preference: workplacePreference,
        max_days_old: maxDays,
        include_linkedin_jobs: includeLinkedInJobs,
        match_strictness: matchStrictness,
      },
      {
        onSuccess: () => toast.success('Saved as your default'),
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save your defaults'),
      },
    );
  };

  const handleStart = () => {
    const aiEnabledForRun = selectedMode !== 'search_only' && llmAvailable;
    const request: SearchRequest = buildSearchRequestFromForm({
      rolesText: roles,
      keywordsText: keywords,
      preferredPlaces: locations,
      companies: suggestedCompanies,
      includeRemote,
      workplacePreference: effectiveWorkplacePreference,
      maxDaysOld: maxDays,
      includeLinkedInJobs,
      matchStrictness,
      useAi: aiEnabledForRun,
      profile,
      mode: selectedMode,
    });
    const runSnapshot: SearchRunSnapshot = buildSearchRunSnapshot({
      request,
      profile: searchDefaults?.profile ?? profile,
      metadata: snapshotMetadata,
    });

    startSearch.mutate(request, {
      onSuccess: (data) => {
        toast.dismiss(SUGGEST_TOAST_ID);
        activate(data.run_id, selectedMode, runSnapshot);
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : 'Failed to start the restock';
        if (message.includes('At least one role or keyword')) {
          toast.error('We still need at least one role or keyword. Try filling from your resume again, or type one manually.', { id: SEARCH_TOAST_ID });
          return;
        }
        if (message.includes('At least one location')) {
          toast.error('Add a place first, or switch to Remote only.', { id: SEARCH_TOAST_ID });
          return;
        }
        toast.error(message, { id: SEARCH_TOAST_ID });
      },
    });
  };

  const handleReset = () => {
    resetSearch();
  };

  const handleSuggest = () => {
    if (!llmAvailable) {
      toast.error('Connect an AI provider in Settings to use this feature.');
      return;
    }
    suggest.mutate(profile, {
      onSuccess: (data) => {
        const nextRoles = data.roles.filter(Boolean);
        const nextKeywords = data.keywords.filter(Boolean);
        const nextPlaces = normalizePlaceList(data.locations.map((item) => createManualPlace(item)));
        const nextCompanies = data.companies.filter(Boolean);

        if (nextRoles.length > 0) setRoles(nextRoles.join('\n'));
        if (nextKeywords.length > 0) setKeywords(nextKeywords.join('\n'));
        if (nextPlaces.length > 0) {
          setLocations(nextPlaces);
          setWorkplacePreference(deriveWorkplacePreferenceFromPlaces(nextPlaces));
        }
        if (nextCompanies.length > 0) setSuggestedCompanies(nextCompanies);

        const updatedParts = [
          nextRoles.length > 0 ? `${nextRoles.length} roles` : null,
          nextKeywords.length > 0 ? `${nextKeywords.length} keywords` : null,
          nextPlaces.length > 0 ? `${nextPlaces.length} places` : null,
          nextCompanies.length > 0 ? `${nextCompanies.length} companies` : null,
        ].filter(Boolean);

        if (updatedParts.length === 0) {
          toast.error('Resume analysis finished, but it did not return usable terms. Add a role or keyword manually and continue.', {
            id: SUGGEST_TOAST_ID,
          });
          return;
        }

        toast.success('Filled in from your resume', {
          id: SUGGEST_TOAST_ID,
          description: updatedParts.join(', '),
        });
      },
      onError: (error) => {
        const message = error instanceof Error ? error.message : '';
        const msg = error instanceof Error ? error.message : '';
        if (msg.includes('No LLM') || msg.includes('provider')) {
          toast.error('Connect an AI provider in Settings to analyze your resume.', { id: SUGGEST_TOAST_ID });
        } else if (msg.includes('No resume') || msg.includes('Upload')) {
          toast.error('Upload your resume in Settings first.', { id: SUGGEST_TOAST_ID });
        } else if (message.includes('too long')) {
          toast.error('Resume analysis took too long. You can still restock now, or try again later.', { id: SUGGEST_TOAST_ID });
        } else if (message.includes('unreadable')) {
          toast.error('Resume analysis came back in an unreadable format. You can still restock now, or try again later.', { id: SUGGEST_TOAST_ID });
        } else {
          toast.error('Resume analysis failed. Try again or fill in the fields manually.', { id: SUGGEST_TOAST_ID });
        }
      },
    });
  };

  const canSuggest = llmAvailable && onboarding?.resume.exists && !suggest.isPending && state !== 'running';

  // Auto-trigger AI suggest when the page loads with sparse data
  // (≤1 role = just the resume title fallback, not real AI analysis).
  // This ensures the user always sees a fully populated form
  // without needing to manually click "Re-fill from resume".
  const autoSuggestFiredRef = useRef(false);
  useEffect(() => {
    if (
      canSuggest &&
      !autoSuggestFiredRef.current &&
      !configLoading &&
      roles != null &&
      roles.split('\n').filter(Boolean).length <= 1
    ) {
      autoSuggestFiredRef.current = true;
      handleSuggest();
    }
  }, [canSuggest, configLoading, roles]);

  // When running/completed, use the mode from context (what was actually started)
  // When idle, use the locally selected mode
  const activeMode = state === 'idle' ? selectedMode : mode;

  const sourceCount = scraperSources?.length ?? 0;

  const [showSources, setShowSources] = useState(false);

  // Group sources by category for display
  const sourcesByCategory = useMemo(() => {
    const sources = scraperSources ?? [];
    const formatCategoryLabel = (key: string) =>
      key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
    const grouped = new Map<string, { label: string; cat: string; sources: typeof sources }>();
    for (const s of sources) {
      const cat = s.category || 'general';
      if (!grouped.has(cat)) grouped.set(cat, { label: formatCategoryLabel(cat), cat, sources: [] });
      grouped.get(cat)!.sources.push(s);
    }
    return Array.from(grouped.values());
  }, [scraperSources]);

  const boardsLabel = sourceCount > 0 ? `${sourceCount} sources` : 'the live sources';

  type ModeInfo = { label: string; desc: string; detail: string };
  const modeLabels: Record<SearchRequest['mode'], ModeInfo> = {
    search_only: {
      label: 'Find quests',
      desc: 'Restock only',
      detail: `Restocks the board from ${boardsLabel}.`,
    },
    search_score: {
      label: 'Find and rank',
      desc: llmAvailable ? 'Restock, then rank by resume fit' : 'Restock with basic ranking for now',
      detail: llmAvailable
        ? `Restocks from ${boardsLabel}, then ranks each job by how well your skills and experience match the requirements.`
        : `Restocks from ${boardsLabel}, then ranks results using keywords, filters, and resume context. Connect AI to upgrade this into deeper resume-fit ranking.`,
    },
    full_pipeline: {
      label: 'Find, rank, and prepare',
      desc: llmAvailable ? 'Rank, draft cover letters, company notes' : 'Needs AI connected',
      detail: llmAvailable
        ? `Restocks from ${boardsLabel}, ranks by resume fit, drafts tailored cover letters, and prepares company background notes. You always review before applying.`
        : 'Connect AI to unlock tailored cover letters and company notes. Basic restock and ranking work without it.',
    },
  };

  const resumeDrivenRun = parsedRoles.length === 0 && parsedKeywords.length === 0 && canUseResumeFallback;
  const startLabel = selectedMode === 'search_only' ? (resumeDrivenRun ? 'Restock from your resume' : 'Restock the board')
    : selectedMode === 'search_score' ? (resumeDrivenRun ? 'Restock and rank from your resume' : (llmAvailable ? 'Restock and rank' : 'Restock with basic ranking'))
    : 'Restock and prepare';

  const stageForDisplay = progress?.stage === 'queued'
    ? getStagesForMode(activeMode)[0]?.key
    : progress?.stage;

  // ── Idle view: the restock form ─────────────────────────────────────
  if (state === 'idle') {
    return (
      <SearchConfigForm
        sourceCount={sourceCount}
        llmAvailable={llmAvailable}
        showSources={showSources}
        setShowSources={setShowSources}
        sourcesByCategory={sourcesByCategory}
        canSuggest={canSuggest}
        roles={roles}
        setRoles={setRoles}
        keywords={keywords}
        setKeywords={setKeywords}
        handleSuggest={handleSuggest}
        suggestPending={suggest.isPending}
        configLoading={configLoading}
        filtersExpanded={filtersExpanded}
        setShowFilters={setShowFilters}
        filterSummary={filterSummary}
        locations={locations}
        setLocations={setLocations}
        workplacePreference={workplacePreference}
        setWorkplacePreference={setWorkplacePreference}
        includeLinkedInJobs={includeLinkedInJobs}
        setIncludeLinkedInJobs={setIncludeLinkedInJobs}
        matchStrictness={matchStrictness}
        setMatchStrictness={setMatchStrictness}
        maxDays={maxDays}
        setMaxDays={setMaxDays}
        searchAreaOverridesSavedDefaults={searchAreaOverridesSavedDefaults}
        applySavedSearchArea={applySavedSearchArea}
        handleSaveSearchAreaDefaults={handleSaveSearchAreaDefaults}
        savePreferencesPending={savePreferences.isPending}
        onboarding={onboarding}
        canUseResumeFallback={canUseResumeFallback}
        suggestedCompanies={suggestedCompanies}
        setSuggestedCompanies={setSuggestedCompanies}
        selectedMode={selectedMode}
        setSelectedMode={setSelectedMode}
        modeLabels={modeLabels}
        handleStart={handleStart}
        startSearchPending={startSearch.isPending}
        missingSearchTerms={missingSearchTerms}
        missingLocations={missingLocations}
        parsedRoles={parsedRoles}
        parsedKeywords={parsedKeywords}
        usesRemoteFallback={usesRemoteFallback}
        startLabel={startLabel}
      />
    );
  }

  // ── Running / Completed / Failed: the run view ─────────────────────
  return (
    <SearchRunView
      state={state}
      activeMode={activeMode}
      progress={progress}
      stageForDisplay={stageForDisplay}
      result={result}
      error={error}
      snapshot={snapshot}
      messages={messages}
      funnel={funnel}
      funnelDismissed={funnelDismissed}
      setFunnelDismissed={setFunnelDismissed}
      sourceLabels={sourceLabels}
      logRef={logRef}
      handleReset={handleReset}
      onViewJobs={() => navigate({ to: '/log/ledger', search: { run: runId ?? undefined, scope: undefined } })}
    />
  );
}
