import { useState, useRef, useEffect, useMemo } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { Search as SearchIcon, CheckCircle2, XCircle, FileText, Loader2, Sparkles, ArrowRight, Circle, Clock, RefreshCw, SlidersHorizontal, ChevronDown, ChevronRight, BarChart3, Bot, Zap, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select';
import { SearchAreaSection } from '@/components/shared/search-area-section';
import { JobBoardOptionsSection } from '@/components/shared/job-board-options-section';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PageHeader } from '@/components/layout/page-header';
import { PipelineSteps } from '@/components/shared/pipeline-steps';
import { ConnectAiPopover } from '@/components/onboarding/connect-ai-popover';
import { useStartSearch, useSearchDefaults, useSuggestSearch } from '@/hooks/use-search';
import { toast } from 'sonner';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState, useSaveWorkspacePreferences } from '@/hooks/use-workspace';
import { useWorkspace } from '@/contexts/workspace-context';
import { useProfile } from '@/contexts/profile-context';
import { useSearchContext } from '@/contexts/search-context';
import { cn } from '@/lib/utils';
import type { SearchRequest, SearchRunSnapshot } from '@/types/search';
import type { PlaceSelection } from '@/types/workspace';
import { useScraperSources, buildSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { useSchedule, useUpdateSchedule } from '@/hooks/use-schedule';
import {
  createManualPlace,
  getWorkplacePreferenceLabel,
  normalizePlaceList,
  placeLabel,
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

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/search',
  component: SearchPage,
});

const FREQ_LABELS: Record<number, string> = {
  1: 'Every hour', 2: 'Every 2 hours', 4: 'Every 4 hours',
  6: 'Every 6 hours', 12: 'Every 12 hours', 24: 'Once a day',
};
const MODE_LABELS: Record<string, string> = {
  search_only: 'Find Jobs', search_score: 'Find & Rank', full_pipeline: 'Find, Rank & Prepare',
};

function formatCurrency(value: number | null | undefined, currency = 'USD'): string {
  if (value == null) return 'Not set';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function compactList(values: string[], limit = 8): { visible: string[]; hidden: number } {
  return {
    visible: values.slice(0, limit),
    hidden: Math.max(values.length - limit, 0),
  };
}

function SnapshotField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-card/70 px-3 py-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
      <p className="mt-1 text-xs text-text-secondary">{value}</p>
    </div>
  );
}

function SnapshotList({ label, values, emptyLabel = 'Not set' }: { label: string; values: string[]; emptyLabel?: string }) {
  const filtered = values.filter(Boolean);
  const { visible, hidden } = compactList(filtered);

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
      {visible.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {visible.map((value) => (
            <span
              key={value}
              className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default"
            >
              {value}
            </span>
          ))}
          {hidden > 0 && (
            <span className="inline-flex items-center rounded-full bg-bg-subtle px-2.5 py-1 text-[11px] text-text-muted ring-1 ring-border-default">
              +{hidden} more
            </span>
          )}
        </div>
      ) : (
        <p className="text-xs text-text-muted">{emptyLabel}</p>
      )}
    </div>
  );
}

function formatRelativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 0) {
    const abs = Math.abs(diff);
    if (abs < 60) return 'in <1m';
    if (abs < 3600) return `in ${Math.floor(abs / 60)}m`;
    return `in ${Math.floor(abs / 3600)}h`;
  }
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function SuggestLoadingState() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setElapsed((prev) => prev + 1), 1000);
    return () => clearInterval(t);
  }, []);
  const hint = elapsed < 10
    ? 'Reading your resume...'
    : elapsed < 25
      ? 'Identifying roles, keywords, and target companies...'
      : elapsed < 60
        ? 'Generating suggestions — speed depends on your AI provider...'
        : 'Still working — slower models may take a couple minutes...';
  return (
    <div className="w-full rounded-xl border-2 border-dashed border-brand/25 bg-gradient-to-br from-brand-light/40 to-brand-light/20 p-6 text-center">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10">
        <Loader2 className="h-5 w-5 text-brand animate-spin" />
      </div>
      <p className="text-sm font-semibold text-brand">Analyzing your resume...</p>
      <p className="text-xs text-text-muted mt-1">{hint}</p>
      <p className="text-[11px] text-text-muted/60 mt-2 tabular-nums">{elapsed}s</p>
    </div>
  );
}

function SearchPage() {
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
  const { data: schedule } = useSchedule(profile, !hostedMode);
  const updateSchedule = useUpdateSchedule(profile);

  const [roles, setRoles] = useState('');
  const [keywords, setKeywords] = useState('');
  const [locations, setLocations] = useState<PlaceSelection[]>([]);
  const [maxDays, setMaxDays] = useState(14);
  const [includeLinkedInJobs, setIncludeLinkedInJobs] = useState(false);
  const [workplacePreference, setWorkplacePreference] = useState<WorkplacePreference>('remote_friendly');
  const [selectedMode, setSelectedMode] = useState<SearchRequest['mode']>(mode);
  const [showFilters, setShowFilters] = useState(false);
  const [suggestedCompanies, setSuggestedCompanies] = useState<string[]>([]);

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

  // Pre-fill from search defaults when config loads
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
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [formSeed]);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  // First-run hand-off: when the brand-new user's very first search completes,
  // ship them straight to the results so they don't get stranded staring at
  // the run log. Only fires once — the flag is set in the onboarding wizard
  // and FirstRunHero quick-search path, then cleared here.
  useEffect(() => {
    if (state !== 'completed' || !runId) return;
    let pending: string | null = null;
    try {
      pending = window.localStorage.getItem('launchboard:first-run-pending');
    } catch {
      pending = null;
    }
    if (pending !== '1') return;
    try {
      window.localStorage.removeItem('launchboard:first-run-pending');
    } catch {
      // ignore
    }
    toast.success('Your first search is ready — opening your top matches.');
    navigate({
      to: '/applications',
      search: { run: runId, scope: undefined },
    });
  }, [state, runId, navigate]);

  const llmAvailable = llm?.available ?? false;
  const searchAreaSummary = getSearchAreaSummary(workplacePreference, locations, 'search');
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
    maxDays !== 14 ? `${maxDays} day window` : null,
    includeLinkedInJobs ? 'LinkedIn enabled' : null,
    suggestedCompanies.length > 0 ? `${suggestedCompanies.length} target companies` : null,
  ].filter(Boolean);
  const savedDefaultSummary = getSearchAreaSummary(
    savedSearchAreaDefaults.workplacePreference,
    savedSearchAreaDefaults.preferredPlaces,
    'search',
  );
  const searchAreaOverridesSavedDefaults = hasSearchAreaOverride(
    {
      preferredPlaces: locations,
      workplacePreference,
      maxDaysOld: maxDays,
      includeLinkedInJobs,
    },
    savedSearchAreaDefaults,
  );

  const applySavedSearchArea = () => {
    setLocations(savedSearchAreaDefaults.preferredPlaces);
    setWorkplacePreference(savedSearchAreaDefaults.workplacePreference);
    setMaxDays(savedSearchAreaDefaults.maxDaysOld);
    setIncludeLinkedInJobs(savedSearchAreaDefaults.includeLinkedInJobs);
    toast.success('Search reset to your saved defaults');
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
      },
      {
        onSuccess: () => toast.success('Saved this search area as your default'),
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save search defaults'),
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
        const message = error instanceof Error ? error.message : 'Failed to start search';
        if (message.includes('At least one role or keyword')) {
          toast.error('We still need at least one role or keyword. Try Auto-fill from your resume again, or type one manually.', { id: SEARCH_TOAST_ID });
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
          toast.error('Resume analysis finished, but it did not return usable search terms. Add a role or keyword manually and continue.', {
            id: SUGGEST_TOAST_ID,
          });
          return;
        }

        toast.success('Search updated from your resume', {
          id: SUGGEST_TOAST_ID,
          description: updatedParts.join(' · '),
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
          toast.error('Resume analysis took too long. You can still search now, or try Analyze again later.', { id: SUGGEST_TOAST_ID });
        } else if (message.includes('unreadable')) {
          toast.error('Resume analysis came back in an unreadable format. You can still search now, or try again later.', { id: SUGGEST_TOAST_ID });
        } else {
          toast.error('Resume analysis failed. Try again or fill in the fields manually.', { id: SUGGEST_TOAST_ID });
        }
      },
    });
  };

  const canSuggest = llmAvailable && onboarding?.resume.exists && !suggest.isPending && state !== 'running';

  // When running/completed, use the mode from context (what was actually started)
  // When idle, use the locally selected mode
  const activeMode = state === 'idle' ? selectedMode : mode;

  const activeStep = state === 'idle' ? undefined
    : activeMode === 'search_only' ? 0
    : activeMode === 'search_score' ? 1
    : 2;

  const sourceCount = scraperSources?.length ?? 0;
  const allSources = scraperSources
    ? scraperSources.map((s) => s.display_name).join(', ')
    : '';

  const [showSources, setShowSources] = useState(false);

  // Category color mapping — applied dynamically from whatever categories the API returns
  const CATEGORY_COLORS: Record<string, string> = {
    jobspy: 'text-blue-600 dark:text-blue-400',
    remote: 'text-emerald-600 dark:text-emerald-400',
    startup: 'text-violet-600 dark:text-violet-400',
    ats: 'text-sky-600 dark:text-sky-400',
    community: 'text-amber-600 dark:text-amber-400',
    crypto: 'text-orange-600 dark:text-orange-400',
    general: 'text-slate-600 dark:text-slate-400',
  };
  const CATEGORY_DOTS: Record<string, string> = {
    jobspy: 'bg-blue-500',
    remote: 'bg-emerald-500',
    startup: 'bg-violet-500',
    ats: 'bg-sky-500',
    community: 'bg-amber-500',
    crypto: 'bg-orange-500',
    general: 'bg-slate-400',
  };

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

  const boardsLabel = sourceCount > 0 ? `${sourceCount} job boards` : 'multiple job boards';

  type ModeInfo = {
    label: string; desc: string; detail: string; icon: typeof SearchIcon;
    color: string; bg: string; selectedBg: string; selectedBorder: string; iconBg: string;
  };
  const modeLabels: Record<SearchRequest['mode'], ModeInfo> = {
    search_only: {
      label: 'Find Jobs',
      desc: 'Search only',
      detail: allSources ? `Searches ${boardsLabel}: ${allSources}.` : `Searches ${boardsLabel}.`,
      icon: SearchIcon,
      color: 'text-blue-600 dark:text-blue-400',
      bg: 'bg-blue-50/60 dark:bg-blue-950/30',
      selectedBg: 'bg-blue-50 dark:bg-blue-950/40',
      selectedBorder: 'border-blue-400 dark:border-blue-500',
      iconBg: 'bg-blue-100 dark:bg-blue-900/50',
    },
    search_score: {
      label: 'Find & Rank',
      desc: llmAvailable ? 'Search + AI resume-fit ranking' : 'Search + basic ranking for now',
      detail: llmAvailable
        ? `Searches ${boardsLabel}, then ranks each job by how well your skills and experience match the requirements.`
        : `Searches ${boardsLabel}, then ranks results using keywords, filters, and resume context. Connect AI to upgrade this into deeper resume-fit scoring.`,
      icon: BarChart3,
      color: 'text-violet-600 dark:text-violet-400',
      bg: 'bg-violet-50/60 dark:bg-violet-950/30',
      selectedBg: 'bg-violet-50 dark:bg-violet-950/40',
      selectedBorder: 'border-violet-400 dark:border-violet-500',
      iconBg: 'bg-violet-100 dark:bg-violet-900/50',
    },
    full_pipeline: {
      label: 'Find, Rank & Prepare',
      desc: llmAvailable ? 'Rank + draft cover letters + company notes' : 'Requires AI',
      detail: llmAvailable
        ? `Searches ${boardsLabel}, ranks by resume fit, drafts tailored cover letters, and prepares company background notes. You always review before applying.`
        : 'Connect AI to unlock tailored cover letters, company notes, and the full Launchboard workflow. Basic search and ranking still work without it.',
      icon: Bot,
      color: 'text-amber-600 dark:text-amber-400',
      bg: 'bg-amber-50/60 dark:bg-amber-950/30',
      selectedBg: 'bg-amber-50 dark:bg-amber-950/40',
      selectedBorder: 'border-amber-400 dark:border-amber-500',
      iconBg: 'bg-amber-100 dark:bg-amber-900/50',
    },
  };

  const resumeDrivenRun = parsedRoles.length === 0 && parsedKeywords.length === 0 && canUseResumeFallback;
  const startLabel = selectedMode === 'search_only' ? (resumeDrivenRun ? 'Search from Resume' : 'Start Search')
    : selectedMode === 'search_score' ? (resumeDrivenRun ? (llmAvailable ? 'Rank from Resume' : 'Start Resume Ranking') : (llmAvailable ? 'Search & Rank' : 'Start Basic Ranking'))
    : 'Search & Prepare';

  // Progress bar helpers — must be inside the component (uses activeMode)
  const formatElapsed = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}s`;
  };

  type StageInfo = { key: string; label: string };
  const STAGE_MAP: Record<string, StageInfo[]> = {
    search_only: [
      { key: 'searching', label: 'Searching' },
      { key: 'saving', label: 'Saving' },
    ],
    search_score: [
      { key: 'searching', label: 'Searching' },
      { key: 'scoring', label: 'Ranking' },
      { key: 'ai_scoring', label: 'Analyzing' },
      { key: 'saving', label: 'Saving' },
    ],
    full_pipeline: [
      { key: 'searching', label: 'Searching' },
      { key: 'scoring', label: 'Ranking' },
      { key: 'ai_scoring', label: 'Analyzing' },
      { key: 'enhancing', label: 'Preparing' },
      { key: 'saving', label: 'Saving' },
    ],
  };

  const getStagesForMode = (m: string): StageInfo[] => STAGE_MAP[m] || STAGE_MAP.search_score;
  const stageForDisplay = progress?.stage === 'queued'
    ? getStagesForMode(activeMode)[0]?.key
    : progress?.stage;

  const isStageComplete = (stageKey: string, currentStage: string | undefined, m: string): boolean => {
    if (!currentStage) return false;
    const stages = getStagesForMode(m);
    const stageIdx = stages.findIndex((s) => s.key === stageKey);
    const currentIdx = stages.findIndex((s) => s.key === currentStage);
    return stageIdx >= 0 && currentIdx >= 0 && stageIdx < currentIdx;
  };

  // ── Idle view: config form ──────────────────────────────────────────
  if (state === 'idle') {
    return (
      <div>
        <PageHeader title="Search" description={sourceCount > 0 ? `Search ${sourceCount} job boards at once, ranked by how well they match your experience` : 'Search multiple job boards at once, ranked by how well they match your experience'} />

        <div className="mb-6">
          <PipelineSteps llmAvailable={llmAvailable} activeStep={undefined} sourceCount={sourceCount} />
        </div>

        <div className="max-w-3xl mx-auto space-y-5">
          {!llmAvailable && (
            <div className="rounded-xl border border-brand/20 bg-brand-light/20 p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm font-medium text-text-primary">Launchboard works best with AI connected.</p>
                  <p className="mt-1 text-xs text-text-muted">
                    Start with basic search now. Connect AI when you want resume-fit ranking, search suggestions, target-company autofill, and tailored draft materials.
                  </p>
                </div>
                <ConnectAiPopover side="bottom" align="end">
                  <Button variant="outline" size="sm" className="shrink-0">
                    <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                    Connect AI
                  </Button>
                </ConnectAiPopover>
              </div>
            </div>
          )}

          {/* Source transparency */}
          {sourceCount > 0 && (
            <div className="px-1">
              <button
                type="button"
                onClick={() => setShowSources(!showSources)}
                className="flex w-full items-center gap-2 text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer group"
              >
                <Globe className="h-3.5 w-3.5 shrink-0" />
                <span>
                  Searching{' '}
                  <span className="font-medium text-text-secondary">{sourceCount} sources</span>
                  <span className="mx-1.5 text-border-default">|</span>
                  {/* Pick first from each category for variety */}
                  {sourcesByCategory.slice(0, 4).map((g) => g.sources[0].display_name).join(', ')}
                  {sourceCount > 4 && ` + ${sourceCount - 4} more`}
                </span>
                <ChevronRight className={cn('h-3 w-3 shrink-0 transition-transform', showSources && 'rotate-90')} />
              </button>
              {showSources && (
                <div className="mt-3 rounded-xl border border-border-default bg-bg-card px-4 py-4">
                  <div className="space-y-2.5">
                    {sourcesByCategory.map((group) => (
                      <div key={group.label} className="flex items-center gap-2.5">
                        <span className={cn('h-1.5 w-1.5 rounded-full shrink-0', CATEGORY_DOTS[group.cat] || 'bg-slate-400')} />
                        <span className={cn('text-[11px] font-semibold whitespace-nowrap w-24 shrink-0', CATEGORY_COLORS[group.cat] || 'text-text-tertiary')}>
                          {group.label}
                        </span>
                        <span className="text-xs text-text-secondary leading-relaxed">
                          {group.sources.map((s, i) => (
                            <span key={s.name}>
                              {i > 0 && <span className="text-text-muted"> · </span>}
                              {s.display_name}
                            </span>
                          ))}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand/10">
                    <SearchIcon className="h-4.5 w-4.5 text-brand" />
                  </div>
                  <div>
                    <CardTitle className="text-base">Search configuration</CardTitle>
                    <p className="text-xs text-text-tertiary mt-0.5">Define what you're looking for</p>
                  </div>
                </div>
                {canSuggest && roles && (
                  <Button variant="outline" size="sm" onClick={handleSuggest} disabled={suggest.isPending} className="text-xs">
                    {suggest.isPending ? (
                      <><Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Analyzing...</>
                    ) : (
                      <><Sparkles className="h-3.5 w-3.5 mr-1.5" /> Re-fill from resume</>
                    )}
                  </Button>
                )}
              </div>
            </CardHeader>
            <CardContent>
              {configLoading ? (
                <div className="space-y-4">
                  {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}
                </div>
              ) : (
                <div className="space-y-5">
                  {/* Suggest CTA when fields are empty */}
                  {!roles && !keywords && (suggest.isPending ? (
                    <SuggestLoadingState />
                  ) : canSuggest ? (
                    <button
                      type="button"
                      onClick={handleSuggest}
                      className="group w-full rounded-xl border-2 border-dashed border-brand/25 bg-gradient-to-br from-brand-light/40 to-brand-light/20 p-6 text-center transition-all hover:border-brand/50 hover:from-brand-light/60 hover:to-brand-light/30 hover:shadow-lg hover:shadow-brand/5 cursor-pointer"
                    >
                      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10 group-hover:bg-brand/15 transition-colors">
                        <Sparkles className="h-5 w-5 text-brand" />
                      </div>
                      <p className="text-sm font-semibold text-brand">Auto-fill from your resume</p>
                      <p className="text-xs text-text-muted mt-1">AI analyzes your resume and suggests roles, keywords, and locations</p>
                    </button>
                  ) : !llmAvailable && (
                    <div className="w-full rounded-xl border border-border-default bg-bg-subtle/50 p-5 text-center">
                      <p className="text-sm font-medium text-text-primary">
                        {canUseResumeFallback ? 'You can start from your uploaded resume, or add roles and keywords below' : 'Type your target roles and keywords below to get started'}
                      </p>
                      <p className="text-xs text-text-muted mt-1">
                        {onboarding?.resume.exists
                          ? 'Launchboard can derive a first search from your resume right away. Connect AI from the sidebar if you want auto-fill, deeper fit ranking, and drafting.'
                          : 'This gets you basic search right away. Upload a resume and connect AI later if you want auto-fill and deeper ranking.'}
                      </p>
                    </div>
                  ))}

                  {/* 2-col form fields */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Target Roles</Label>
                      <Textarea value={roles} onChange={(e) => setRoles(e.target.value)} rows={4} placeholder="e.g. Marketing Manager&#10;Product Designer&#10;Nurse Practitioner" />
                      <p className="text-xs text-text-muted">One role per line</p>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Keywords</Label>
                      <Textarea value={keywords} onChange={(e) => setKeywords(e.target.value)} rows={4} placeholder="e.g. Project Management&#10;Patient Care&#10;Data Analysis" />
                      <p className="text-xs text-text-muted">One keyword per line</p>
                    </div>
                  </div>

                  {/* Collapsible filters */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowFilters(!filtersExpanded)}
                      className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      <span className="font-medium">Filters</span>
                      {!filtersExpanded && filterSummary.length > 0 && (
                        <span className="text-[10px] bg-brand-light text-brand font-medium rounded-full px-1.5 py-0.5">
                          {filterSummary.join(', ')}
                        </span>
                      )}
                      <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', filtersExpanded && 'rotate-180')} />
                    </button>
                    {filtersExpanded && (
                      <div className="grid grid-cols-1 sm:grid-cols-[1.2fr_0.8fr] gap-5 mt-4 pt-4 border-t border-border-default">
                        <div className="space-y-4">
                          <SearchAreaSection
                            preferredPlaces={locations}
                            onPreferredPlacesChange={setLocations}
                            workplacePreference={workplacePreference}
                            onWorkplacePreferenceChange={setWorkplacePreference}
                            context="search"
                          />

                          <JobBoardOptionsSection
                            includeLinkedInJobs={includeLinkedInJobs}
                            onIncludeLinkedInJobsChange={setIncludeLinkedInJobs}
                            context="search"
                          />
                        </div>

                        <div className="space-y-4">
                          <div className="space-y-2">
                            <Label className="text-sm font-medium">Posted within: <span className="text-brand tabular-nums">{maxDays} days</span></Label>
                            <Slider value={[maxDays]} onValueChange={(v) => setMaxDays(Array.isArray(v) ? v[0] : v)} min={1} max={30} step={1} />
                          </div>

                          <div className="rounded-xl border border-border-default bg-bg-subtle px-3.5 py-3">
                            <p className="text-sm font-medium text-text-primary">Saved defaults + run overrides</p>
                            <p className="text-xs text-text-muted mt-1 leading-relaxed">
                              This form starts from your profile settings. Changes here affect only this search and are shown in the run log.
                            </p>
                          </div>

                        </div>
                      </div>
                    )}
                  </div>

                  <div className="rounded-xl border border-border-default bg-bg-subtle/50 px-3.5 py-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-text-secondary">Using for this run:</span>
                      <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                        {getWorkplacePreferenceLabel(effectiveWorkplacePreference)}
                      </span>
                      <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                        {maxDays} day window
                      </span>
                      {includeLinkedInJobs && (
                        <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                          LinkedIn enabled
                        </span>
                      )}
                      {locations.map((location) => (
                        <span key={location.label} className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                          {placeLabel(location)}
                        </span>
                      ))}
                      {locations.length === 0 && isRemoteOnly && (
                        <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                          {searchAreaSummary.shortLabel}
                        </span>
                      )}
                      {locations.length === 0 && usesRemoteFallback && (
                        <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                          {searchAreaSummary.shortLabel}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={cn(
                    'rounded-xl border px-3.5 py-3',
                    searchAreaOverridesSavedDefaults
                      ? 'border-amber-200 bg-amber-50/70 dark:border-amber-900/50 dark:bg-amber-950/20'
                      : 'border-border-default bg-bg-subtle/40',
                  )}>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-text-primary">
                          {searchAreaOverridesSavedDefaults ? 'This run is overriding your saved defaults' : 'Search matches your saved defaults'}
                        </p>
                        <p className="mt-1 text-xs text-text-muted leading-relaxed">
                          Saved area: {savedDefaultSummary.shortLabel}
                          {savedSearchAreaDefaults.preferredPlaces.length > 0 ? ` · ${savedDefaultSummary.placesSummary}` : ''}
                          {savedSearchAreaDefaults.maxDaysOld ? ` · ${savedSearchAreaDefaults.maxDaysOld} day window` : ''}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {searchAreaOverridesSavedDefaults && (
                          <Button type="button" variant="outline" size="sm" onClick={applySavedSearchArea}>
                            Use saved defaults
                          </Button>
                        )}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={handleSaveSearchAreaDefaults}
                          disabled={savePreferences.isPending || !searchAreaOverridesSavedDefaults}
                        >
                          {savePreferences.isPending ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : null}
                          Save this as default
                        </Button>
                      </div>
                    </div>
                  </div>

                  {/* Resume status */}
                  <div className={cn(
                    'flex items-center gap-2.5 text-xs rounded-lg px-3.5 py-2.5 border',
                    onboarding?.resume.exists
                      ? 'bg-success/5 border-success/20'
                      : 'bg-bg-muted border-border-default',
                  )}>
                    {onboarding?.resume.exists ? (
                      <>
                        <div className="flex h-7 w-7 items-center justify-center rounded bg-red-500/10 shrink-0">
                          <FileText className="h-3.5 w-3.5 text-red-500" />
                        </div>
                        <span className="text-text-secondary truncate" title={onboarding.resume.filename}>{onboarding.resume.filename}</span>
                        {onboarding.resume.file_size > 0 && (
                          <span className="text-text-muted shrink-0">
                            {onboarding.resume.file_size >= 1_048_576
                              ? `${(onboarding.resume.file_size / 1_048_576).toFixed(1)} MB`
                              : `${Math.round(onboarding.resume.file_size / 1024)} KB`}
                          </span>
                        )}
                        {onboarding.resume.parse_warning && (
                          <span className="truncate text-amber-700 dark:text-amber-300">
                            {onboarding.resume.parse_warning}
                          </span>
                        )}
                      </>
                    ) : (
                      <>
                        <FileText className="h-4 w-4 shrink-0 text-text-muted" />
                        <span className="text-text-muted">No resume uploaded — <a href="/settings" className="text-brand hover:underline">upload in Settings</a></span>
                      </>
                    )}
                  </div>

                  {/* Target companies (AI suggested + user-added) */}
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Label className="text-sm font-medium">Target Companies</Label>
                      {suggestedCompanies.length > 0 && (
                        <span className="text-[10px] bg-brand-light text-brand font-medium rounded-full px-1.5 py-0.5">
                          {suggestedCompanies.length} companies
                        </span>
                      )}
                    </div>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="Add a company — press Enter"
                        className="flex-1 h-8 rounded-md border border-border-default bg-bg-card px-2.5 text-xs placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-brand"
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            const value = (e.target as HTMLInputElement).value.trim();
                            if (value && !suggestedCompanies.some((c) => c.toLowerCase() === value.toLowerCase())) {
                              setSuggestedCompanies((prev) => [...prev, value]);
                              (e.target as HTMLInputElement).value = '';
                            }
                          }
                        }}
                      />
                    </div>
                    {suggestedCompanies.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {suggestedCompanies.map((company) => (
                          <span
                            key={company}
                            className="inline-flex items-center gap-1 text-xs bg-bg-muted rounded-md px-2 py-1 text-text-secondary"
                          >
                            {company}
                            <button
                              type="button"
                              onClick={() => setSuggestedCompanies((prev) => prev.filter((c) => c !== company))}
                              className="text-text-tertiary hover:text-text-primary transition-colors ml-0.5"
                              aria-label={`Remove ${company}`}
                            >
                              <XCircle className="h-3 w-3" />
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="text-xs text-text-muted">
                      {suggestedCompanies.length > 0
                        ? 'Career pages will be searched directly on Greenhouse, Lever, and Ashby. All other jobs come from 14+ job boards regardless.'
                        : 'Optionally add companies to search their career pages directly. AI will auto-fill these when you upload a resume.'}
                    </p>
                  </div>

                  {/* Mode selector */}
                  <div className="space-y-3">
                    <Label className="text-sm font-medium">What should we do?</Label>
                    <div className="grid grid-cols-3 gap-3" role="radiogroup" aria-label="Search mode">
                      {(['search_only', 'search_score', 'full_pipeline'] as const).map((m) => {
                        const info = modeLabels[m];
                        const Icon = info.icon;
                        const isSelected = selectedMode === m;
                        return (
                          <button
                            key={m}
                            type="button"
                            role="radio"
                            aria-checked={isSelected}
                            onClick={() => setSelectedMode(m)}
                            disabled={m === 'full_pipeline' && !llmAvailable}
                            className={cn(
                              'relative rounded-xl border-2 px-3 py-4 text-center transition-all cursor-pointer',
                              'disabled:opacity-40 disabled:cursor-not-allowed',
                              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2',
                              isSelected
                                ? `${info.selectedBorder} ${info.selectedBg} shadow-sm`
                                : 'border-border-default bg-bg-card hover:border-border-hover hover:bg-bg-muted',
                            )}
                          >
                            <div className={cn(
                              'mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-xl transition-colors',
                              isSelected ? info.iconBg : 'bg-bg-muted',
                            )}>
                              <Icon className={cn('h-4.5 w-4.5', isSelected ? info.color : 'text-text-muted')} />
                            </div>
                            <div className={cn('text-sm font-semibold', isSelected ? info.color : 'text-text-primary')}>{info.label}</div>
                            <div className="text-[11px] text-text-muted mt-0.5 leading-tight">{info.desc}</div>
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-xs text-text-tertiary leading-relaxed">
                      {modeLabels[selectedMode].detail}
                    </p>
                    {!llmAvailable && selectedMode === 'search_score' && (
                      <p className="text-xs text-text-muted leading-relaxed">
                        This run will still rank jobs, but it will use keyword and filter matching until you connect AI in Settings.
                      </p>
                    )}
                    {!llmAvailable && selectedMode === 'full_pipeline' && (
                      <p className="text-xs text-text-muted leading-relaxed">
                        Full prepare mode is disabled until AI is connected.
                      </p>
                    )}
                  </div>

                  {/* Start */}
                  <div className="pt-1">
                    <Button onClick={handleStart} disabled={startSearch.isPending || suggest.isPending || missingSearchTerms || missingLocations} size="lg" className="w-full text-sm h-12 text-[15px] font-semibold shadow-lg shadow-brand/20 hover:shadow-xl hover:shadow-brand/25 transition-shadow">
                      {startSearch.isPending ? (
                        <><Loader2 className="h-4.5 w-4.5 mr-2 animate-spin" /> Starting...</>
                      ) : suggest.isPending ? (
                        <><Loader2 className="h-4.5 w-4.5 mr-2 animate-spin" /> Analyzing resume...</>
                      ) : (
                        <><Zap className="h-4.5 w-4.5 mr-2" /> {startLabel}</>
                      )}
                    </Button>
                    {missingSearchTerms && (
                      <p className="text-xs text-text-muted text-center mt-2">Add at least one role or keyword above to start</p>
                    )}
                    {!missingSearchTerms && missingLocations && (
                      <div className="mt-2 space-y-2 text-center">
                        <p className="text-xs text-text-muted">Add a preferred location, or switch this run to a mode that does not require one.</p>
                        <div className="flex flex-wrap items-center justify-center gap-2">
                          <Button type="button" variant="outline" size="sm" onClick={() => setWorkplacePreference('remote_friendly')}>
                            Use Remote + selected places
                          </Button>
                          <Button type="button" variant="outline" size="sm" onClick={() => setWorkplacePreference('remote_only')}>
                            Use Remote only
                          </Button>
                        </div>
                      </div>
                    )}
                    {!missingSearchTerms && !missingLocations && parsedRoles.length === 0 && parsedKeywords.length === 0 && canUseResumeFallback && (
                      <p className="text-xs text-text-muted text-center mt-2">No roles or keywords entered. Launchboard will derive them from your uploaded resume for this run.</p>
                    )}
                    {!missingSearchTerms && !missingLocations && usesRemoteFallback && (
                      <p className="text-xs text-text-muted text-center mt-2">No place selected yet, so this run will keep remote jobs everywhere until you add one.</p>
                    )}
                    {suggestedCompanies.length > 0 && !missingSearchTerms && !missingLocations && (
                      <p className="text-xs text-text-muted text-center mt-2">
                        <Bot className="h-3 w-3 inline mr-1" />
                        Targeting {suggestedCompanies.length} companies from resume analysis
                      </p>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Scheduled Search */}
          {!hostedMode && (
            <Card className="overflow-hidden">
              <CardContent className="p-0">
                <div className="flex items-center justify-between px-5 py-4">
                  <div className="flex items-center gap-3">
                    <div className={cn(
                      'flex h-9 w-9 items-center justify-center rounded-xl transition-colors',
                      schedule?.enabled ? 'bg-emerald-100/80 dark:bg-emerald-950' : 'bg-bg-muted',
                    )}>
                      <Clock className={cn('h-4.5 w-4.5', schedule?.enabled ? 'text-emerald-600' : 'text-text-muted')} />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-text-primary">Scheduled Search</h3>
                      <p className="text-xs text-text-tertiary">Run searches automatically on a schedule</p>
                    </div>
                  </div>
                  <Checkbox
                    id="schedule-enabled"
                    checked={schedule?.enabled ?? false}
                    onCheckedChange={(checked) => {
                      updateSchedule.mutate(
                        { enabled: !!checked, interval_hours: schedule?.interval_hours ?? 6, mode: schedule?.mode ?? 'search_score' },
                        { onSuccess: () => toast.success(checked ? 'Scheduled search enabled' : 'Scheduled search disabled') },
                      );
                    }}
                  />
                </div>
                <div className="px-5 pb-5 space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <Label className="text-xs font-medium text-text-tertiary mb-1.5 block">Frequency</Label>
                      <Select
                        value={String(schedule?.interval_hours ?? 6)}
                        onValueChange={(v) => {
                          updateSchedule.mutate({ enabled: schedule?.enabled ?? false, interval_hours: Number(v), mode: schedule?.mode ?? 'search_score' });
                        }}
                      >
                        <SelectTrigger className="h-9 text-sm">
                          <span className="flex flex-1 text-left">
                            {FREQ_LABELS[schedule?.interval_hours ?? 6] ?? 'Every 6 hours'}
                          </span>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">Every hour</SelectItem>
                          <SelectItem value="2">Every 2 hours</SelectItem>
                          <SelectItem value="4">Every 4 hours</SelectItem>
                          <SelectItem value="6">Every 6 hours</SelectItem>
                          <SelectItem value="12">Every 12 hours</SelectItem>
                          <SelectItem value="24">Once a day</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs font-medium text-text-tertiary mb-1.5 block">Search Type</Label>
                      <Select
                        value={schedule?.mode ?? 'search_score'}
                        onValueChange={(v) => {
                          if (!v) return;
                          updateSchedule.mutate({ enabled: schedule?.enabled ?? false, interval_hours: schedule?.interval_hours ?? 6, mode: v });
                        }}
                      >
                        <SelectTrigger className="h-9 text-sm">
                          <span className="flex flex-1 text-left">
                            {MODE_LABELS[schedule?.mode ?? 'search_score'] ?? 'Find & Rank'}
                          </span>
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="search_only">Find Jobs</SelectItem>
                          <SelectItem value="search_score">Find & Rank</SelectItem>
                          <SelectItem value="full_pipeline">Find, Rank & Prepare</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  {(schedule?.enabled || schedule?.last_run_at) && (
                    <div className="flex items-center gap-3 rounded-xl bg-bg-subtle border border-border-default px-3.5 py-2.5 text-xs">
                      {schedule?.enabled && (
                        <span className="inline-flex items-center gap-1.5 text-emerald-600 font-medium">
                          <RefreshCw className="h-3 w-3 animate-[spin_3s_linear_infinite]" /> Active
                        </span>
                      )}
                      {schedule?.last_run_at && (
                        <span className="text-text-muted">
                          Last run {formatRelativeTime(schedule.last_run_at)}
                          {schedule.last_run_jobs_found > 0 && ` · ${schedule.last_run_jobs_found} jobs found`}
                        </span>
                      )}
                      {schedule?.next_run_at && schedule.enabled && (
                        <span className="text-text-muted ml-auto">Next {formatRelativeTime(schedule.next_run_at)}</span>
                      )}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    );
  }

  // ── Running / Completed / Failed: full-width execution view ────────
  return (
    <div className="flex flex-col" style={{ minHeight: 'calc(100vh - 6rem)' }}>
      <PageHeader title="Run search" description="Search for jobs across multiple sources" />

      <div className="mb-6">
        <PipelineSteps
          llmAvailable={llmAvailable}
          activeStep={state === 'running' ? activeStep : state === 'completed' ? 3 : undefined}
          sourceCount={sourceCount}
        />
      </div>

      {/* Progress bar + stage dots */}
      {state === 'running' && (
        <div className="space-y-3 mb-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" />
              <span className="text-sm font-medium text-text-primary">
                {progress?.stage_label || 'Starting...'}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-text-muted tabular-nums">
              <span>{progress?.percent ?? 0}%</span>
              <span>{formatElapsed(progress?.elapsed ?? 0)}</span>
              <Button onClick={handleReset} variant="ghost" size="sm" className="text-xs h-7 text-text-muted hover:text-danger">
                <XCircle className="h-3 w-3 mr-1" /> Cancel
              </Button>
            </div>
          </div>
          <Progress value={progress?.percent ?? 0} className="h-2" />
          <div className="flex items-center justify-between px-1">
            {getStagesForMode(activeMode).map((s) => {
              const isCurrent = stageForDisplay === s.key;
              const isDone = isStageComplete(s.key, stageForDisplay, activeMode);
              return (
                <div
                  key={s.key}
                  className={cn(
                    'flex items-center gap-1 text-[10px] transition-colors',
                    isCurrent ? 'text-brand font-medium' : isDone ? 'text-success' : 'text-text-muted',
                  )}
                >
                  {isDone ? <CheckCircle2 className="h-3 w-3" /> : isCurrent ? <Loader2 className="h-3 w-3 animate-spin" /> : <Circle className="h-3 w-3" />}
                  {s.label}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Result summary */}
      {result && (
        <div className="rounded-lg border border-success/30 bg-success/10 p-4 mb-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <p className="text-sm font-medium text-success">Search Complete</p>
              <p className="text-xs text-text-secondary">
                Found {result.jobs_found} jobs · Scored {result.jobs_scored} · {result.strong_matches} strong matches · {(result.duration_seconds ?? 0).toFixed(1)}s
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={handleReset} variant="outline" size="sm">New search</Button>
              <Button size="sm" onClick={() => navigate({ to: '/applications', search: { run: runId ?? undefined, scope: undefined } })}>
                View {result.jobs_found} Jobs <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
              </Button>
            </div>
          </div>
          {result.sources && Object.keys(result.sources).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(result.sources)
                .sort(([, a], [, b]) => b - a)
                .map(([source, count]) => (
                  <span key={source} className="inline-flex items-center rounded-md bg-bg-card/70 px-2 py-0.5 text-[11px] text-text-secondary ring-1 ring-border-default">
                    {resolveSourceLabel(source, sourceLabels)}
                    <span className="ml-1 font-semibold tabular-nums">{count}</span>
                  </span>
                ))}
            </div>
          )}
          {snapshot && !snapshot.use_ai && (
            <div className="flex flex-col gap-3 rounded-lg border border-brand/20 bg-bg-card/70 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-medium text-text-primary">This run used basic ranking only.</p>
                <p className="mt-1 text-xs text-text-muted">
                  Connect AI to rerank by resume fit and unlock cover letters, company notes, and application prep.
                </p>
              </div>
              <ConnectAiPopover side="bottom" align="end">
                <Button variant="outline" size="sm" className="shrink-0">
                  <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                  Connect AI
                </Button>
              </ConnectAiPopover>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-danger/30 bg-danger/10 p-4 mb-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-danger">Search Failed</p>
              <p className="text-xs text-text-secondary mt-1">
                {error.toLowerCase().includes('timeout')
                  ? 'The search took too long. Try searching with fewer locations or broader keywords.'
                  : error.toLowerCase().includes('fetch') || error.toLowerCase().includes('network')
                  ? 'We couldn\'t connect to the server. Please try again in a moment.'
                  : error}
              </p>
            </div>
            <Button onClick={handleReset} variant="outline" size="sm">Try Again</Button>
          </div>
        </div>
      )}

      {/* Full-width log — fills remaining viewport */}
      <div className="flex-1 min-h-[300px] rounded-lg border border-border-default bg-bg-card overflow-hidden flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-bg-subtle">
          <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider">Output Log</span>
          <span className="text-[11px] text-text-muted tabular-nums">{messages.length} messages</span>
        </div>
        {snapshot && (
          <div className="border-b border-border-default bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.08),transparent_45%),linear-gradient(to_bottom,rgba(148,163,184,0.08),transparent)] px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-text-muted">Run Settings</p>
                <p className="mt-1 text-sm font-medium text-text-primary">
                  {MODE_LABELS[snapshot.mode]} on profile <span className="text-brand">{snapshot.profile}</span>
                </p>
              </div>
              <div className="flex flex-wrap gap-1.5">
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {snapshot.use_ai ? 'AI enabled' : 'Keyword only'}
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {getWorkplacePreferenceLabel(snapshot.workplace_preference)}
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  {snapshot.max_days_old} day window
                </span>
                <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                  LinkedIn {snapshot.include_linkedin_jobs ? 'enabled' : 'disabled'}
                </span>
              </div>
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-[1.25fr_1fr]">
              <div className="space-y-3">
                <SnapshotList label="Roles" values={snapshot.roles} emptyLabel="No roles provided" />
                <SnapshotList label="Keywords" values={snapshot.keywords} emptyLabel="No keywords provided" />
                <SnapshotList label="Target Companies" values={snapshot.companies ?? []} emptyLabel="No target companies provided" />
                <SnapshotList
                  label="Preferred Locations"
                  values={snapshot.locations}
                  emptyLabel={snapshot.workplace_preference === 'remote_only' ? 'Remote only' : 'No locations provided'}
                />
              </div>

              <div className="space-y-3">
                <div className="grid gap-2 sm:grid-cols-2">
                  <SnapshotField label="Workplace Type" value={getWorkplacePreferenceLabel(snapshot.workplace_preference)} />
                  <SnapshotField label="Current Title" value={snapshot.current_title || 'Not set'} />
                  <SnapshotField label="Current Level" value={snapshot.current_level || 'Not set'} />
                  <SnapshotField label="Comp Period" value={`${snapshot.compensation_currency} · ${snapshot.compensation_period}`} />
                  <SnapshotField label="Current TC" value={formatCurrency(snapshot.current_tc, snapshot.compensation_currency)} />
                  <SnapshotField label="Minimum Base" value={formatCurrency(snapshot.min_base, snapshot.compensation_currency)} />
                  <SnapshotField label="Target TC" value={formatCurrency(snapshot.target_total_comp, snapshot.compensation_currency)} />
                  <SnapshotField label="Hard-floor TC" value={formatCurrency(snapshot.min_acceptable_tc, snapshot.compensation_currency)} />
                </div>

                <div className="flex flex-wrap gap-1.5">
                  <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                    Equity {snapshot.include_equity == null ? 'not set' : snapshot.include_equity ? 'included' : 'excluded'}
                  </span>
                  <span className="inline-flex items-center rounded-full bg-bg-card px-2.5 py-1 text-[11px] text-text-secondary ring-1 ring-border-default">
                    Staffing agencies {snapshot.exclude_staffing_agencies == null ? 'not set' : snapshot.exclude_staffing_agencies ? 'excluded' : 'allowed'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}
        <ScrollArea className="flex-1">
          <div ref={logRef} className="p-4 space-y-0.5 font-mono text-xs">
            {messages.map((msg, i) => (
              <div key={i} className="text-text-secondary py-0.5 leading-relaxed">
                <span className="text-text-muted mr-2 tabular-nums select-none">[{String(i + 1).padStart(2, '0')}]</span>
                {msg}
              </div>
            ))}
            {state === 'running' && (
              <div className="text-brand animate-pulse py-0.5">Waiting for updates...</div>
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}
