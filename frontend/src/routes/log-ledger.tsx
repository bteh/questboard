import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { createRoute, Link, useNavigate } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import {
  LayoutGrid, List, Search, X, Inbox, SearchX,
  ArrowUpDown, Download, LinkIcon, Loader2, Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { JobCard } from '@/components/jobs/job-card';
import { JobTable } from '@/components/jobs/job-table';
import { EmptyState } from '@/components/shared/empty-state';
import { FilterToggleButton } from '@/components/shared/FilterToggleButton';
import { FilterChips } from '@/components/shared/FilterChips';
import { useQuery } from '@tanstack/react-query';
import { useApplications } from '@/hooks/use-applications';
import { pickLatestCompletedRun, useSearchRuns } from '@/hooks/use-search';
import { useProfile } from '@/contexts/profile-context';
import { useSourceLabels } from '@/hooks/use-scrapers';
import { getSources } from '@/api/analytics';
import { checkUrls, exportApplicationsCsv, purgeAllApplications } from '@/api/applications';
import { STATUS_OPTIONS, STATUS_LABELS, COMPANY_TYPES, SORT_OPTIONS } from '@/utils/constants';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApplicationFilters } from '@/types/application';
import { cn } from '@/lib/utils';
import '@/components/log/ledger.css';

/* The old Applications page, whole, at its new address: both views, the
   filter row, the scope toggle, status editing, pagination, purge, URL
   check, and the detail card. Reskinned to ledger grammar; behavior
   unchanged. New here: the Download CSV button (the endpoint always
   existed, the button never did). */

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/log/ledger',
  component: LedgerPage,
  validateSearch: (search: Record<string, unknown>) => ({
    run: (search.run as string) || undefined,
    scope:
      search.scope === 'all'
        ? 'all'
        : search.scope === 'new'
          ? 'new'
          : undefined,
  }),
});

const WORK_TYPES = [
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'onsite', label: 'Onsite' },
] as const;

const REC_OPTIONS = [
  { value: 'STRONG_APPLY', label: 'Strong Apply' },
  { value: 'APPLY', label: 'Apply' },
  { value: 'MAYBE', label: 'Maybe' },
  { value: 'SKIP', label: 'Skip' },
] as const;

/** Maps raw source values (from DB) to display labels. */
const SOURCE_LABEL_MAP: Record<string, string> = {
  indeed: 'Indeed',
  linkedin: 'LinkedIn',
  glassdoor: 'Glassdoor',
  zip_recruiter: 'ZipRecruiter',
  google: 'Google Jobs',
  remotive: 'Remotive',
  himalayas: 'Himalayas',
  weworkremotely: 'We Work Remotely',
  hackernews: 'Hacker News',
  greenhouse: 'Greenhouse',
  lever: 'Lever',
  remoteok: 'RemoteOK',
  cryptojobslist: 'CryptoJobsList',
  workatastartup: 'YC Work at a Startup',
  arbeitnow: 'Arbeitnow',
  themuse: 'The Muse',
  workday: 'Workday',
};

function LedgerPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { run: searchRunId, scope } = Route.useSearch();
  const { profile } = useProfile();
  const sourceLabels = useSourceLabels();
  const { data: runs } = useSearchRuns(10);
  const latestCompletedRun = useMemo(() => pickLatestCompletedRun(runs), [runs]);
  // Three scopes:
  //   "new"    - only jobs first surfaced in the latest run (first_seen_run_id filter).
  //   "all"    - every tracked job, regardless of which run found it.
  //   default  - jobs the latest run surfaced (search_run_id filter; new + re-discoveries).
  const effectiveRunId =
    scope === 'all' ? undefined : (searchRunId ?? latestCompletedRun?.run_id);
  const firstSeenRunIdFilter = scope === 'new' ? effectiveRunId : undefined;
  const isExplicitRunScope = !!searchRunId;
  const isNewOnly = scope === 'new' && !!effectiveRunId;
  const urlCheck = useMutation({
    mutationFn: () => checkUrls(undefined, 100),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      toast.success(`Checked ${result.checked} URLs: ${result.alive} alive, ${result.dead} expired`);
    },
    onError: () => toast.error('Failed to check URLs'),
  });
  const purgeAll = useMutation({
    mutationFn: () => purgeAllApplications(profile),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      toast.success(`Cleared ${result.purged} applications`);
    },
    onError: () => toast.error('Failed to clear applications'),
  });
  const csvExport = useMutation({
    mutationFn: () => exportApplicationsCsv(profile),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'questboard-ledger.csv';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
    },
    onError: () => toast.error('The export could not be built'),
  });
  const { data: sourcesData } = useQuery({
    queryKey: ['analytics', 'sources', profile ?? 'default', effectiveRunId],
    queryFn: () => getSources(profile, effectiveRunId),
    staleTime: 5 * 60 * 1000,
  });
  const sourceOptions = useMemo(() =>
    (sourcesData || [])
      .filter((s) => s.label && s.label !== 'Unknown')
      .map((s) => ({ value: s.label, label: SOURCE_LABEL_MAP[s.label] || s.label })),
    [sourcesData],
  );
  const [view, setView] = useState<'cards' | 'table'>('cards');
  const [showFilters, setShowFilters] = useState(true);
  const [searchInput, setSearchInput] = useState('');
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Default filter: only Strong Apply (>=70) matches. Career-ops philosophy:
  // When navigating from "View N Jobs" on the search page (explicit run),
  // show ALL jobs from that run; the user expects to see everything they
  // found. When landing on the page normally (no run param), default to
  // strong matches so the user sees a curated list.
  const STRONG_MATCH_THRESHOLD = 70;
  const [filters, setFilters] = useState<ApplicationFilters>({
    sort_by: 'overall_score',
    sort_order: 'desc',
    page: 1,
    page_size: 25,
    min_score: searchRunId ? undefined : STRONG_MATCH_THRESHOLD,
  });

  const { data, isLoading } = useApplications({
    ...filters,
    profile,
    // When scope=new we filter by first_seen_run_id only; searching by
    // search_run_id too would be redundant since first_seen implies search.
    search_run_id: isNewOnly ? undefined : effectiveRunId,
    first_seen_run_id: firstSeenRunIdFilter,
  });

  const updateFilter = useCallback((key: keyof ApplicationFilters, value: unknown) => {
    setFilters((prev) => ({ ...prev, [key]: value, page: 1 }));
  }, []);

  // Debounced search
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => {
      updateFilter('search', searchInput || undefined);
    }, 300);
    return () => {
      if (searchTimer.current) clearTimeout(searchTimer.current);
    };
  }, [searchInput, updateFilter]);

  const clearAllFilters = useCallback(() => {
    setSearchInput('');
    setFilters({
      sort_by: 'overall_score',
      sort_order: 'desc',
      page: 1,
      page_size: 25,
    });
  }, []);

  const isStrongMatchesOnly = filters.min_score === STRONG_MATCH_THRESHOLD;
  const showAllTrackedJobs = useCallback(() => {
    setFilters((prev) => ({ ...prev, min_score: undefined, page: 1 }));
  }, []);
  const focusOnStrongMatches = useCallback(() => {
    setFilters((prev) => ({ ...prev, min_score: STRONG_MATCH_THRESHOLD, page: 1 }));
  }, []);

  const items = data?.items || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / (filters.page_size || 25));

  // Compute active filter chips
  const activeFilters: { key: keyof ApplicationFilters; label: string; display: string }[] = [];
  if (filters.status) activeFilters.push({ key: 'status', label: 'Status', display: STATUS_LABELS[filters.status] || filters.status });
  if (filters.recommendation) {
    const rec = REC_OPTIONS.find((r) => r.value === filters.recommendation);
    activeFilters.push({ key: 'recommendation', label: 'Recommendation', display: rec?.label || filters.recommendation });
  }
  if (filters.company_type) activeFilters.push({ key: 'company_type', label: 'Company', display: filters.company_type });
  if (filters.work_type) {
    const wt = WORK_TYPES.find((w) => w.value === filters.work_type);
    activeFilters.push({ key: 'work_type', label: 'Work', display: wt?.label || filters.work_type });
  }
  if (filters.source) {
    activeFilters.push({ key: 'source', label: 'Source', display: SOURCE_LABEL_MAP[filters.source] || filters.source });
  }
  if (filters.min_score) activeFilters.push({ key: 'min_score', label: 'Score', display: `${filters.min_score}+` });

  const hasActiveFilters = activeFilters.length > 0 || !!searchInput;

  return (
    <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 44px 96px' }}>
      {/* Header */}
      <div className="qb-ledger-head">
        <Link to="/log" className="qb-textlink qb-ledger-back">
          Your log
        </Link>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <h1>The full ledger</h1>
            <p className="qb-ledger-count">
              {total > 0 ? (
                <>
                  {total}{' '}
                  {isNewOnly
                    ? 'new in your latest search'
                    : effectiveRunId
                      ? (isExplicitRunScope ? 'jobs from this search' : 'jobs from your latest search')
                      : 'jobs tracked'}
                  {hasActiveFilters && <span>, {items.length} matching filters</span>}
                </>
              ) : (
                isNewOnly
                  ? 'No new jobs in your latest search'
                  : effectiveRunId
                    ? (isExplicitRunScope ? 'No jobs found in this search' : 'No jobs found in your latest search')
                    : 'No jobs tracked yet'
              )}
            </p>
          </div>
          <div className="qb-ledger-tools">
            <button
              type="button"
              className="qb-ledger-ctl"
              onClick={() => csvExport.mutate()}
              disabled={csvExport.isPending}
              title="Download the tracked jobs as a CSV file"
            >
              {csvExport.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Download className="h-3.5 w-3.5" />
              )}
              Download CSV
            </button>
            <div className="qb-scope" role="group" aria-label="Scope">
              {(['new', 'latest', 'all'] as const).map((value) => {
                const active =
                  value === 'new'
                    ? scope === 'new'
                    : value === 'all'
                      ? scope === 'all'
                      : !!effectiveRunId && !isExplicitRunScope && scope !== 'new';
                const onClick = () =>
                  navigate({
                    to: '/log/ledger',
                    search:
                      value === 'all'
                        ? { scope: 'all', run: undefined }
                        : value === 'new'
                          ? { scope: 'new', run: undefined }
                          : { run: undefined, scope: undefined },
                  });
                const label =
                  value === 'new' ? 'New' : value === 'latest' ? 'Latest search' : 'All tracked';
                const hint =
                  value === 'new'
                    ? 'Jobs first surfaced by your latest search'
                    : value === 'latest'
                      ? 'Every job the latest search returned (new + re-discoveries)'
                      : 'Every tracked job, regardless of which run found it';
                return (
                  <button
                    key={value}
                    type="button"
                    title={hint}
                    onClick={onClick}
                    className={cn(active && 'qb-active')}
                  >
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between gap-3">
        <button
          type="button"
          className="qb-plainbtn"
          style={{ fontSize: 13, padding: 0 }}
          onClick={isStrongMatchesOnly ? showAllTrackedJobs : focusOnStrongMatches}
        >
          {isStrongMatchesOnly ? 'Showing strong matches only. Show everything' : 'Focus on strong matches'}
        </button>
      </div>

      {/* Toolbar: Search + Filters toggle + View toggle */}
      <div className="flex items-center gap-3 mt-4 mb-3">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none" />
          <Input
            placeholder="Search jobs, companies..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9 h-9 text-sm"
          />
          {searchInput && (
            <button
              onClick={() => setSearchInput('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary transition-colors"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Filters toggle */}
        <FilterToggleButton
          open={showFilters}
          count={activeFilters.length}
          onClick={() => setShowFilters((p) => !p)}
        />

        {/* Sort */}
        <Select value={filters.sort_by || 'overall_score'} onValueChange={(v) => updateFilter('sort_by', v)}>
          <SelectTrigger className="h-9 w-auto gap-1.5">
            <ArrowUpDown className="h-3.5 w-3.5 text-text-muted" />
            <SelectValue placeholder="Match Score">
              {SORT_OPTIONS.find((o) => o.value === (filters.sort_by || 'overall_score'))?.label ?? 'Match Score'}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {SORT_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* View toggle */}
        <div className="flex items-center rounded-lg border border-border-default p-0.5 gap-0.5" role="group" aria-label="View mode">
          <button
            onClick={() => setView('cards')}
            aria-label="Card view"
            aria-pressed={view === 'cards'}
            className={`flex items-center justify-center h-7 w-7 rounded-md transition-all focus-ring ${
              view === 'cards'
                ? 'bg-bg-card text-text-primary'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setView('table')}
            aria-label="Table view"
            aria-pressed={view === 'table'}
            className={`flex items-center justify-center h-7 w-7 rounded-md transition-all focus-ring ${
              view === 'table'
                ? 'bg-bg-card text-text-primary'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <List className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Expandable filter row */}
      {showFilters && (
        <div className="flex flex-wrap items-end gap-3 pb-3 mb-1 border-b border-border-default animate-in slide-in-from-top-1 duration-150">
          <FilterSelect
            label="Status"
            value={filters.status}
            onValueChange={(v) => updateFilter('status', v)}
            placeholder="All"
            options={STATUS_OPTIONS.map((s) => ({ value: s, label: STATUS_LABELS[s] || s }))}
          />
          <FilterSelect
            label="Match"
            value={filters.recommendation}
            onValueChange={(v) => updateFilter('recommendation', v)}
            placeholder="All"
            options={REC_OPTIONS.map((r) => ({ value: r.value, label: r.label }))}
          />
          <FilterSelect
            label="Company"
            value={filters.company_type}
            onValueChange={(v) => updateFilter('company_type', v)}
            placeholder="All"
            options={COMPANY_TYPES.map((t) => ({ value: t, label: t }))}
          />
          <FilterSelect
            label="Work"
            value={filters.work_type}
            onValueChange={(v) => updateFilter('work_type', v)}
            placeholder="All"
            options={WORK_TYPES.map((w) => ({ value: w.value, label: w.label }))}
          />
          <FilterSelect
            label="Source"
            value={filters.source}
            onValueChange={(v) => updateFilter('source', v)}
            placeholder="All"
            options={sourceOptions}
          />
          <div className="min-w-[140px]">
            <span className="text-[11px] font-medium text-text-muted mb-1.5 block">
              Min score
            </span>
            <div className="flex items-center gap-2.5 h-8">
              <Slider
                value={[filters.min_score || 0]}
                onValueChange={(v) => updateFilter('min_score', (Array.isArray(v) ? v[0] : v) || undefined)}
                max={100}
                step={5}
                className="flex-1"
              />
              <span className="text-xs font-medium text-text-secondary tabular-nums w-7 text-right">
                {filters.min_score || 0}
              </span>
            </div>
          </div>

          {/* Clean up: check for expired postings */}
          {total > 0 && (
            <div className="ml-auto">
              <span className="text-[11px] font-medium text-text-muted mb-1.5 block">&nbsp;</span>
              <button
                type="button"
                onClick={() => urlCheck.mutate()}
                disabled={urlCheck.isPending}
                title="Check which job postings are still live and hide expired ones"
                className="inline-flex items-center gap-1.5 h-8 px-2.5 text-xs text-text-muted hover:text-text-secondary transition-colors rounded-md hover:bg-bg-muted cursor-pointer disabled:opacity-50"
              >
                {urlCheck.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <LinkIcon className="h-3 w-3" />
                )}
                Remove expired
              </button>
              <button
                type="button"
                onClick={() => {
                  if (window.confirm('Clear all saved applications? This cannot be undone. Personal quests in your log stay.')) {
                    purgeAll.mutate();
                  }
                }}
                disabled={purgeAll.isPending}
                title="Delete all saved applications and start fresh"
                className="inline-flex items-center gap-1.5 h-8 px-2.5 text-xs text-danger/70 hover:text-danger transition-colors rounded-md hover:bg-danger/10 cursor-pointer disabled:opacity-50"
              >
                {purgeAll.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3" />
                )}
                Clear all
              </button>
            </div>
          )}
        </div>
      )}

      {/* Active filter chips */}
      <FilterChips
        items={activeFilters}
        onRemove={(key) => updateFilter(key as keyof ApplicationFilters, undefined)}
        onClearAll={clearAllFilters}
        className="py-2.5"
      />

      {/* Content */}
      <div className="mt-2">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[120px] w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            icon={hasActiveFilters ? SearchX : Inbox}
            title={hasActiveFilters ? 'No matching jobs' : 'Nothing tracked yet'}
            description={
              hasActiveFilters
                ? 'Loosen a filter or clear the search.'
                : 'Run a search and tracked jobs land here.'
            }
          >
            {hasActiveFilters ? (
              <Button variant="outline" onClick={clearAllFilters} className="gap-1.5">
                <X className="h-3.5 w-3.5" />
                Clear all filters
              </Button>
            ) : (
              <Link to="/search" className="qb-textlink">
                Run your first search
              </Link>
            )}
          </EmptyState>
        ) : view === 'cards' ? (
          <div className="space-y-4">
            {items.map((app) => (
              <JobCard
                key={app.id}
                app={app}
                sourceLabels={sourceLabels}
                latestRunId={latestCompletedRun?.run_id ?? null}
              />
            ))}
          </div>
        ) : (
          <>
            <JobTable
              data={items}
              onRowClick={(app) => setSelectedJobId(selectedJobId === app.id ? null : app.id)}
              selectedId={selectedJobId}
            />
            {selectedJobId != null && (() => {
              const selected = items.find((a) => a.id === selectedJobId);
              if (!selected) return null;
              return (
                <div className="mt-4">
                  <JobCard
                    app={selected}
                    sourceLabels={sourceLabels}
                    latestRunId={latestCompletedRun?.run_id ?? null}
                  />
                </div>
              );
            })()}
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="qb-ledger-pages">
          <p className="qb-range">
            {((filters.page || 1) - 1) * (filters.page_size || 25) + 1}
            &ndash;{Math.min((filters.page || 1) * (filters.page_size || 25), total)} of {total}
          </p>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <button
              type="button"
              className="qb-ledger-ctl"
              disabled={filters.page === 1}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) - 1 }))}
            >
              Previous
            </button>
            <div className="qb-pagenums">
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const page = totalPages <= 5
                  ? i + 1
                  : i === 0 ? 1
                  : i === 4 ? totalPages
                  : Math.min(
                    Math.max((filters.page || 1) - 1 + (i - 1), 2),
                    totalPages - 1,
                  );
                return (
                  <button
                    key={page}
                    onClick={() => setFilters((prev) => ({ ...prev, page }))}
                    aria-label={`Page ${page}`}
                    aria-current={page === (filters.page || 1) ? 'page' : undefined}
                    className={cn(page === (filters.page || 1) && 'qb-active')}
                  >
                    {page}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              className="qb-ledger-ctl"
              disabled={(filters.page || 1) >= totalPages}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) + 1 }))}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ---- Reusable filter select ---- */

function FilterSelect({
  label,
  value,
  onValueChange,
  placeholder,
  options,
}: {
  label: string;
  value: string | undefined;
  onValueChange: (v: string | undefined) => void;
  placeholder: string;
  options: { value: string; label: string }[];
}) {
  return (
    <div>
      <span className="text-[11px] font-medium text-text-muted mb-1.5 block">
        {label}
      </span>
      <Select
        value={value || 'all'}
        onValueChange={(v) => onValueChange(!v || v === 'all' ? undefined : v)}
      >
        <SelectTrigger className="h-8 text-xs min-w-[120px]">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{placeholder}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
