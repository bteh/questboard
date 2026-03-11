import { useState, useRef, useEffect, useMemo } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { Search as SearchIcon, Play, CheckCircle2, XCircle, FileText, Loader2, Sparkles, ArrowRight, Circle, Clock, RefreshCw, SlidersHorizontal, ChevronDown, ChevronRight, BarChart3, Bot, Zap, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { ScrollArea } from '@/components/ui/scroll-area';
import { PageHeader } from '@/components/layout/page-header';
import { PipelineSteps } from '@/components/shared/pipeline-steps';
import { useStartSearch, useSearchDefaults, useSuggestSearch } from '@/hooks/use-search';
import { toast } from 'sonner';
import { useResumeStatus } from '@/hooks/use-resume';
import { useLLMStatus } from '@/hooks/use-settings';
import { useProfile } from '@/contexts/profile-context';
import { useSearchContext } from '@/contexts/search-context';
import { cn } from '@/lib/utils';
import type { SearchRequest } from '@/types/search';
import { useScraperSources, buildSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { useSchedule, useUpdateSchedule } from '@/hooks/use-schedule';

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

function SearchPage() {
  const navigate = useNavigate();
  const { profile } = useProfile();
  const { data: searchDefaults, isLoading: configLoading } = useSearchDefaults(profile);
  const { data: llm } = useLLMStatus();
  const { data: resume } = useResumeStatus();
  const startSearch = useStartSearch();
  const suggest = useSuggestSearch();
  const { state, messages, result, error, mode, progress, activate, reset: resetSearch } = useSearchContext();
  const { data: scraperSources } = useScraperSources();
  const sourceLabels = useMemo(() => buildSourceLabels(scraperSources), [scraperSources]);
  const { data: schedule } = useSchedule(profile);
  const updateSchedule = useUpdateSchedule(profile);

  const [roles, setRoles] = useState('');
  const [keywords, setKeywords] = useState('');
  const [locations, setLocations] = useState('');
  const [maxDays, setMaxDays] = useState(14);
  const [includeRemote, setIncludeRemote] = useState(true);
  const [selectedMode, setSelectedMode] = useState<SearchRequest['mode']>(mode);
  const [showFilters, setShowFilters] = useState(false);

  const logRef = useRef<HTMLDivElement>(null);
  const autoSuggestedRef = useRef(false);

  // Pre-fill from search defaults when config loads
  useEffect(() => {
    if (searchDefaults) {
      /* eslint-disable react-hooks/set-state-in-effect -- form initialization from async data */
      if (searchDefaults.roles?.length) setRoles(searchDefaults.roles.join('\n'));
      if (searchDefaults.keywords?.length) setKeywords(searchDefaults.keywords.join('\n'));
      if (searchDefaults.locations?.length) setLocations(searchDefaults.locations.join('\n'));
      if (searchDefaults.max_days_old) setMaxDays(searchDefaults.max_days_old);
      /* eslint-enable react-hooks/set-state-in-effect */
    }
  }, [searchDefaults]);

  // Auto-fill from resume on first visit when fields are empty
  useEffect(() => {
    if (autoSuggestedRef.current) return;
    if (configLoading) return; // wait for defaults to load first
    const hasDefaults = searchDefaults?.roles?.length || searchDefaults?.keywords?.length;
    if (hasDefaults) return; // YAML config already provided values
    if (!llm?.available || !resume?.exists) return;
    if (suggest.isPending) return;
    autoSuggestedRef.current = true;
    suggest.mutate(profile, {
      onSuccess: (data) => {
        setRoles(data.roles.join('\n'));
        setKeywords(data.keywords.join('\n'));
        setLocations(data.locations.join('\n'));
        toast.success('Search configured from your resume', { description: data.summary });
      },
    });
  }, [configLoading, searchDefaults, llm, resume, profile]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [messages]);

  const llmAvailable = llm?.available ?? false;

  const handleStart = () => {
    const request: SearchRequest = {
      roles: roles.split('\n').map((s) => s.trim()).filter(Boolean),
      locations: locations.split('\n').map((s) => s.trim()).filter(Boolean),
      keywords: keywords.split('\n').map((s) => s.trim()).filter(Boolean),
      include_remote: includeRemote,
      max_days_old: maxDays,
      use_ai: selectedMode !== 'search_only',
      profile,
      mode: selectedMode,
    };

    startSearch.mutate(request, {
      onSuccess: (data) => {
        activate(data.run_id, selectedMode);
      },
      onError: () => toast.error('Failed to start search'),
    });
  };

  const handleReset = () => {
    resetSearch();
  };

  const handleSuggest = () => {
    suggest.mutate(profile, {
      onSuccess: (data) => {
        setRoles(data.roles.join('\n'));
        setKeywords(data.keywords.join('\n'));
        setLocations(data.locations.join('\n'));
        toast.success('Search configured from your resume', {
          description: data.summary,
        });
      },
      onError: () => toast.error('Could not analyze resume. Make sure your LLM and resume are set up in Settings.'),
    });
  };

  const canSuggest = llmAvailable && resume?.exists && !suggest.isPending && state !== 'running';

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
      desc: 'Search + rank by how well you match',
      detail: `Searches ${boardsLabel}, then ranks each job by how well your skills and experience match the requirements.`,
      icon: BarChart3,
      color: 'text-violet-600 dark:text-violet-400',
      bg: 'bg-violet-50/60 dark:bg-violet-950/30',
      selectedBg: 'bg-violet-50 dark:bg-violet-950/40',
      selectedBorder: 'border-violet-400 dark:border-violet-500',
      iconBg: 'bg-violet-100 dark:bg-violet-900/50',
    },
    full_pipeline: {
      label: 'Find, Rank & Prepare',
      desc: 'Rank + draft cover letters + company notes',
      detail: `Searches ${boardsLabel}, ranks by resume fit, drafts tailored cover letters, and prepares company background notes. You always review before applying.`,
      icon: Bot,
      color: 'text-amber-600 dark:text-amber-400',
      bg: 'bg-amber-50/60 dark:bg-amber-950/30',
      selectedBg: 'bg-amber-50 dark:bg-amber-950/40',
      selectedBorder: 'border-amber-400 dark:border-amber-500',
      iconBg: 'bg-amber-100 dark:bg-amber-900/50',
    },
  };

  const startLabel = selectedMode === 'search_only' ? 'Start Search'
    : selectedMode === 'search_score' ? 'Search & Rank'
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
                    <CardTitle className="text-base">Search Configuration</CardTitle>
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
                    <div className="w-full rounded-xl border-2 border-dashed border-brand/25 bg-gradient-to-br from-brand-light/40 to-brand-light/20 p-6 text-center">
                      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-brand/10">
                        <Loader2 className="h-5 w-5 text-brand animate-spin" />
                      </div>
                      <p className="text-sm font-semibold text-brand">Analyzing your resume...</p>
                      <p className="text-xs text-text-muted mt-1">Extracting roles, skills, and preferences</p>
                    </div>
                  ) : canSuggest && (
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
                  ))}

                  {/* 2-col form fields */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Target Roles</Label>
                      <Textarea value={roles} onChange={(e) => setRoles(e.target.value)} rows={4} placeholder="Software Engineer&#10;Backend Engineer&#10;Full Stack Developer" />
                      <p className="text-xs text-text-muted">One role per line</p>
                    </div>
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Keywords</Label>
                      <Textarea value={keywords} onChange={(e) => setKeywords(e.target.value)} rows={4} placeholder="Python&#10;React&#10;TypeScript" />
                      <p className="text-xs text-text-muted">One keyword per line</p>
                    </div>
                  </div>

                  {/* Collapsible filters */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowFilters(!showFilters)}
                      className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary transition-colors cursor-pointer"
                    >
                      <SlidersHorizontal className="h-3.5 w-3.5" />
                      <span className="font-medium">Filters</span>
                      {!showFilters && (locations || maxDays !== 14 || !includeRemote) && (
                        <span className="text-[10px] bg-brand-light text-brand font-medium rounded-full px-1.5 py-0.5">
                          {[locations && 'location', maxDays !== 14 && 'recency', !includeRemote && 'on-site only'].filter(Boolean).join(', ')}
                        </span>
                      )}
                      <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showFilters && 'rotate-180')} />
                    </button>
                    {showFilters && (
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 mt-4 pt-4 border-t border-border-default">
                        <div className="space-y-2">
                          <Label className="text-sm font-medium">Locations</Label>
                          <Textarea value={locations} onChange={(e) => setLocations(e.target.value)} rows={2} placeholder="San Francisco, CA&#10;Remote" />
                          <p className="text-xs text-text-muted">One location per line</p>
                        </div>
                        <div className="space-y-4">
                          <div className="space-y-2">
                            <Label className="text-sm font-medium">Posted within: <span className="text-brand tabular-nums">{maxDays} days</span></Label>
                            <Slider value={[maxDays]} onValueChange={(v) => setMaxDays(Array.isArray(v) ? v[0] : v)} min={1} max={30} step={1} />
                          </div>
                          <div className="flex items-center gap-2">
                            <Checkbox id="remote" checked={includeRemote} onCheckedChange={(c) => setIncludeRemote(!!c)} />
                            <Label htmlFor="remote" className="text-sm font-normal">Include remote jobs</Label>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Resume status */}
                  <div className={cn(
                    'flex items-center gap-2.5 text-xs rounded-lg px-3.5 py-2.5 border',
                    resume?.exists
                      ? 'bg-success/5 border-success/20'
                      : 'bg-bg-muted border-border-default',
                  )}>
                    {resume?.exists ? (
                      <>
                        <div className="flex h-7 w-7 items-center justify-center rounded bg-red-500/10 shrink-0">
                          <FileText className="h-3.5 w-3.5 text-red-500" />
                        </div>
                        <span className="text-text-secondary truncate" title={resume.filename}>{resume.filename}</span>
                        {resume.file_size > 0 && (
                          <span className="text-text-muted shrink-0">
                            {resume.file_size >= 1_048_576
                              ? `${(resume.file_size / 1_048_576).toFixed(1)} MB`
                              : `${Math.round(resume.file_size / 1024)} KB`}
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
                  </div>

                  {/* Start */}
                  <div className="pt-1">
                    <Button onClick={handleStart} disabled={startSearch.isPending || (!roles && !keywords)} size="lg" className="w-full text-sm h-12 text-[15px] font-semibold shadow-lg shadow-brand/20 hover:shadow-xl hover:shadow-brand/25 transition-shadow">
                      {startSearch.isPending ? (
                        <><Loader2 className="h-4.5 w-4.5 mr-2 animate-spin" /> Starting...</>
                      ) : (
                        <><Zap className="h-4.5 w-4.5 mr-2" /> {startLabel}</>
                      )}
                    </Button>
                    {!roles && !keywords && (
                      <p className="text-xs text-text-muted text-center mt-2">Add at least one role or keyword above to start</p>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Scheduled Search */}
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
        </div>
      </div>
    );
  }

  // ── Running / Completed / Failed: full-width execution view ────────
  return (
    <div className="flex flex-col" style={{ minHeight: 'calc(100vh - 6rem)' }}>
      <PageHeader title="Run Search" description="Search for jobs across multiple sources" />

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
              const isCurrent = progress?.stage === s.key;
              const isDone = isStageComplete(s.key, progress?.stage, activeMode);
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
                Found {result.jobs_found} jobs · Scored {result.jobs_scored} · {result.strong_matches} strong matches · {result.duration_seconds.toFixed(1)}s
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button onClick={handleReset} variant="outline" size="sm">New Search</Button>
              <Button size="sm" onClick={() => navigate({ to: '/applications' })}>
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
