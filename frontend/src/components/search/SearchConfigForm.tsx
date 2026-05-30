import { Search as SearchIcon, XCircle, FileText, Loader2, Sparkles, SlidersHorizontal, ChevronDown, ChevronRight, Bot, Zap, Globe } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SearchAreaSection } from '@/components/shared/search-area-section';
import { JobBoardOptionsSection } from '@/components/shared/job-board-options-section';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/page-header';
import { PipelineSteps } from '@/components/shared/pipeline-steps';
import { ConnectAiPopover } from '@/components/onboarding/connect-ai-popover';
import { cn } from '@/lib/utils';
import type { MatchStrictness, SearchRequest } from '@/types/search';
import type { OnboardingState, PlaceSelection } from '@/types/workspace';
import type { WorkplacePreference } from '@/lib/profile-preferences';
import type { ScraperSource } from '@/api/scrapers';
import {
  MatchStrictnessControl,
  SuggestLoadingState,
  CATEGORY_COLORS,
  CATEGORY_DOTS,
} from './search-leaf';

type ModeInfo = {
  label: string; desc: string; detail: string; icon: typeof SearchIcon;
  color: string; bg: string; selectedBg: string; selectedBorder: string; iconBg: string;
};

type SourceCategoryGroup = { label: string; cat: string; sources: ScraperSource[] };

interface SearchConfigFormProps {
  sourceCount: number;
  llmAvailable: boolean;
  showSources: boolean;
  setShowSources: (value: boolean) => void;
  sourcesByCategory: SourceCategoryGroup[];
  canSuggest: boolean | '' | undefined;
  roles: string;
  setRoles: (value: string) => void;
  keywords: string;
  setKeywords: (value: string) => void;
  handleSuggest: () => void;
  suggestPending: boolean;
  configLoading: boolean;
  filtersExpanded: boolean;
  setShowFilters: (value: boolean) => void;
  filterSummary: (string | null)[];
  locations: PlaceSelection[];
  setLocations: (places: PlaceSelection[]) => void;
  workplacePreference: WorkplacePreference;
  setWorkplacePreference: (value: WorkplacePreference) => void;
  includeLinkedInJobs: boolean;
  setIncludeLinkedInJobs: (value: boolean) => void;
  matchStrictness: MatchStrictness;
  setMatchStrictness: (value: MatchStrictness) => void;
  maxDays: number;
  setMaxDays: (value: number) => void;
  searchAreaOverridesSavedDefaults: boolean;
  applySavedSearchArea: () => void;
  handleSaveSearchAreaDefaults: () => void;
  savePreferencesPending: boolean;
  onboarding: OnboardingState | undefined;
  canUseResumeFallback: boolean;
  suggestedCompanies: string[];
  setSuggestedCompanies: (updater: (prev: string[]) => string[]) => void;
  selectedMode: SearchRequest['mode'];
  setSelectedMode: (value: SearchRequest['mode']) => void;
  modeLabels: Record<SearchRequest['mode'], ModeInfo>;
  handleStart: () => void;
  startSearchPending: boolean;
  missingSearchTerms: boolean;
  missingLocations: boolean;
  parsedRoles: string[];
  parsedKeywords: string[];
  usesRemoteFallback: boolean;
  startLabel: string;
}

export function SearchConfigForm({
  sourceCount,
  llmAvailable,
  showSources,
  setShowSources,
  sourcesByCategory,
  canSuggest,
  roles,
  setRoles,
  keywords,
  setKeywords,
  handleSuggest,
  suggestPending,
  configLoading,
  filtersExpanded,
  setShowFilters,
  filterSummary,
  locations,
  setLocations,
  workplacePreference,
  setWorkplacePreference,
  includeLinkedInJobs,
  setIncludeLinkedInJobs,
  matchStrictness,
  setMatchStrictness,
  maxDays,
  setMaxDays,
  searchAreaOverridesSavedDefaults,
  applySavedSearchArea,
  handleSaveSearchAreaDefaults,
  savePreferencesPending,
  onboarding,
  canUseResumeFallback,
  suggestedCompanies,
  setSuggestedCompanies,
  selectedMode,
  setSelectedMode,
  modeLabels,
  handleStart,
  startSearchPending,
  missingSearchTerms,
  missingLocations,
  parsedRoles,
  parsedKeywords,
  usesRemoteFallback,
  startLabel,
}: SearchConfigFormProps) {
  return (
    <div>
      <PageHeader title="Search" description={sourceCount > 0 ? `${sourceCount} sources, ranked by fit` : 'Multi-source search, ranked by fit'} />

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
                <Button variant="outline" size="sm" onClick={handleSuggest} disabled={suggestPending} className="text-xs">
                  {suggestPending ? (
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
                {/* Suggest CTA when fields are empty or sparse (1 role = fallback from resume title).
                    The keyword extractor gives ~15 terms even without AI, so we can't just check
                    emptiness — we check if the roles look like a minimal fallback. */}
                {((!roles && !keywords) || (roles && roles.length <= 1 && canSuggest)) && (suggestPending ? (
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
                    className={cn(
                      'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium transition-all cursor-pointer',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2',
                      filtersExpanded
                        ? 'border-brand bg-brand-light/40 text-brand hover:bg-brand-light/60'
                        : 'border-border-default bg-bg-card text-text-primary hover:border-brand/60 hover:bg-bg-subtle',
                    )}
                  >
                    <SlidersHorizontal className="h-4 w-4" />
                    <span>Filters</span>
                    {!filtersExpanded && filterSummary.length > 0 && (
                      <span className="ml-1 inline-flex items-center rounded-full bg-brand px-2 py-0.5 text-[11px] font-semibold text-white">
                        {filterSummary.join(', ')}
                      </span>
                    )}
                    <ChevronDown className={cn('h-4 w-4 transition-transform', filtersExpanded && 'rotate-180')} />
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
                        <div className="space-y-1.5">
                          <Label className="text-sm font-medium">Match strictness</Label>
                          <MatchStrictnessControl value={matchStrictness} onChange={setMatchStrictness} />
                        </div>

                        <div className="space-y-2">
                          <Label className="text-sm font-medium">Posted within: <span className="text-brand tabular-nums">{maxDays} days</span></Label>
                          <Slider value={[maxDays]} onValueChange={(v) => setMaxDays(Array.isArray(v) ? v[0] : v)} min={1} max={60} step={1} />
                        </div>

                      </div>
                    </div>
                  )}
                </div>

                {searchAreaOverridesSavedDefaults && (
                  <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-text-muted px-1">
                    <span>Overriding saved defaults</span>
                    <div className="flex gap-3">
                      <button type="button" className="text-text-secondary hover:text-text-primary underline-offset-2 hover:underline" onClick={applySavedSearchArea}>
                        Reset
                      </button>
                      <button
                        type="button"
                        className="text-brand underline-offset-2 hover:underline disabled:opacity-50 disabled:cursor-not-allowed disabled:no-underline"
                        onClick={handleSaveSearchAreaDefaults}
                        disabled={savePreferencesPending}
                      >
                        {savePreferencesPending ? 'Saving…' : 'Save as default'}
                      </button>
                    </div>
                  </div>
                )}

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
                    <Label
                      className="text-sm font-medium"
                      title="Searches these companies' ATS career pages (Greenhouse, Lever, Ashby, Workday) directly. AI suggests from your resume."
                    >
                      Target companies
                    </Label>
                    {suggestedCompanies.length > 0 && (
                      <span className="text-[10px] bg-brand-light text-brand font-medium rounded-full px-1.5 py-0.5">
                        {suggestedCompanies.length}
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
                  <Button onClick={handleStart} disabled={startSearchPending || suggestPending || missingSearchTerms || missingLocations} size="lg" className="w-full text-sm h-12 text-[15px] font-semibold shadow-lg shadow-brand/20 hover:shadow-xl hover:shadow-brand/25 transition-shadow">
                    {startSearchPending ? (
                      <><Loader2 className="h-4.5 w-4.5 mr-2 animate-spin" /> Starting...</>
                    ) : suggestPending ? (
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

      </div>
    </div>
  );
}
