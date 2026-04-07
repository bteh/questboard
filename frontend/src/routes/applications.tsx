import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { createRoute, Link, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import {
  LayoutGrid, List, Search, X, SlidersHorizontal, Inbox, SearchX,
  ArrowUpDown, ChevronLeft, ChevronRight, Rocket, LinkIcon, Loader2, Trash2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Slider } from '@/components/ui/slider';
import { JobCard } from '@/components/jobs/job-card';
import { JobTable } from '@/components/jobs/job-table';
import { useQuery } from '@tanstack/react-query';
import { useApplications } from '@/hooks/use-applications';
import { pickLatestCompletedRun, useSearchRuns } from '@/hooks/use-search';
import { useProfile } from '@/contexts/profile-context';
import { useSourceLabels } from '@/hooks/use-scrapers';
import { getSources } from '@/api/analytics';
import { checkUrls, purgeAllApplications } from '@/api/applications';
import { STATUS_OPTIONS, STATUS_LABELS, COMPANY_TYPES, SORT_OPTIONS } from '@/utils/constants';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { ApplicationFilters } from '@/types/application';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/applications',
  component: ApplicationsPage,
  validateSearch: (search: Record<string, unknown>) => ({
    run: (search.run as string) || undefined,
    scope: search.scope === 'all' ? 'all' : undefined,
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

function ApplicationsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { run: searchRunId, scope } = Route.useSearch();
  const { profile } = useProfile();
  const sourceLabels = useSourceLabels();
  const { data: runs } = useSearchRuns(10);
  const latestCompletedRun = useMemo(() => pickLatestCompletedRun(runs), [runs]);
  const effectiveRunId = scope === 'all' ? undefined : (searchRunId ?? latestCompletedRun?.run_id);
  const isExplicitRunScope = !!searchRunId;
  const urlCheck = useMutation({
    mutationFn: () => checkUrls(undefined, 100),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      toast.success(`Checked ${result.checked} URLs — ${result.alive} alive, ${result.dead} expired`);
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
  const [filters, setFilters] = useState<ApplicationFilters>({
    sort_by: 'overall_score',
    sort_order: 'desc',
    page: 1,
    page_size: 25,
  });

  const { data, isLoading } = useApplications({ ...filters, profile, search_run_id: effectiveRunId });

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
    <div>
      {/* Header */}
      <div className="flex items-start justify-between pb-2">
        <div>
          <h1 className="text-2xl font-semibold text-text-primary tracking-tight">Applications</h1>
          <p className="mt-0.5 text-sm text-text-tertiary tabular-nums">
            {total > 0 ? (
              <>
                {total} {effectiveRunId ? (isExplicitRunScope ? 'jobs from this search' : 'jobs from your latest search') : 'jobs tracked'}
                {hasActiveFilters && <span> · {items.length} matching filters</span>}
              </>
            ) : (
              effectiveRunId ? (isExplicitRunScope ? 'No jobs found in this search' : 'No jobs found in your latest search') : 'No jobs tracked yet'
            )}
          </p>
          {effectiveRunId && (
            <div className="mt-1 flex items-center gap-3">
              <button
                type="button"
                className="text-xs text-brand hover:text-brand-dark font-medium cursor-pointer"
                onClick={() => navigate({ to: '/applications', search: { scope: 'all', run: undefined } })}
              >
                Show all jobs
              </button>
              {scope === 'all' && latestCompletedRun && (
                <button
                  type="button"
                  className="text-xs text-text-muted hover:text-text-secondary font-medium cursor-pointer"
                  onClick={() => navigate({ to: '/applications', search: { run: undefined, scope: undefined } })}
                >
                  Back to latest search
                </button>
              )}
            </div>
          )}
          {!effectiveRunId && scope === 'all' && latestCompletedRun && (
            <button
              type="button"
              className="mt-1 text-xs text-brand hover:text-brand-dark font-medium cursor-pointer"
              onClick={() => navigate({ to: '/applications', search: { run: undefined, scope: undefined } })}
            >
              Back to latest search
            </button>
          )}
        </div>
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
        <Button
          variant={showFilters ? 'secondary' : 'outline'}
          size="default"
          onClick={() => setShowFilters((p) => !p)}
          className="gap-1.5"
        >
          <SlidersHorizontal className="h-4 w-4" />
          Filters
          {activeFilters.length > 0 && (
            <span className="flex items-center justify-center h-5 w-5 rounded-full bg-brand text-white text-[10px] font-semibold ml-0.5">
              {activeFilters.length}
            </span>
          )}
        </Button>

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
                ? 'bg-bg-card shadow-sm text-text-primary'
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
                ? 'bg-bg-card shadow-sm text-text-primary'
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
            <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">
              Min Score
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

          {/* Clean up — check for expired postings */}
          {total > 0 && (
            <div className="ml-auto">
              <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">&nbsp;</span>
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
                  if (window.confirm('Clear all saved applications? This cannot be undone.')) {
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
      {activeFilters.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 py-2.5">
          {activeFilters.map((f) => (
            <button
              key={f.key}
              onClick={() => updateFilter(f.key, undefined)}
              className="group inline-flex items-center gap-1 rounded-md bg-bg-muted hover:bg-danger/10 border border-transparent hover:border-danger/30 px-2 py-0.5 text-xs font-medium text-text-secondary hover:text-danger transition-all"
            >
              <span className="text-text-muted group-hover:text-red-400">{f.label}:</span>
              {f.display}
              <X className="h-3 w-3 ml-0.5 opacity-40 group-hover:opacity-100 transition-opacity" />
            </button>
          ))}
          <button
            onClick={clearAllFilters}
            className="text-xs text-text-muted hover:text-brand font-medium ml-1 transition-colors"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Content */}
      <div className="mt-2">
        {isLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[120px] w-full rounded-xl" />
            ))}
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mb-5">
              {hasActiveFilters ? (
                <SearchX className="h-7 w-7 text-brand" />
              ) : (
                <Inbox className="h-7 w-7 text-brand" />
              )}
            </div>
            <h3 className="text-lg font-semibold text-text-primary mb-1.5">
              {hasActiveFilters ? 'No matching jobs' : 'No applications yet'}
            </h3>
            <p className="text-sm text-text-tertiary max-w-md mb-5">
              {hasActiveFilters
                ? 'Try adjusting your filters or broadening your search criteria.'
                : 'Run a search to discover and track job opportunities.'}
            </p>
            {hasActiveFilters ? (
              <Button variant="outline" onClick={clearAllFilters} className="gap-1.5">
                <X className="h-3.5 w-3.5" />
                Clear all filters
              </Button>
            ) : (
              <Button render={<Link to="/search" />} className="gap-1.5">
                <Rocket className="h-3.5 w-3.5" />
                Run your first search
              </Button>
            )}
          </div>
        ) : view === 'cards' ? (
          <div className="space-y-4">
            {items.map((app) => (
              <JobCard key={app.id} app={app} sourceLabels={sourceLabels} />
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
                  <JobCard app={selected} sourceLabels={sourceLabels} />
                </div>
              );
            })()}
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-8 pt-4 border-t border-border-default">
          <p className="text-sm text-text-tertiary tabular-nums">
            Showing {((filters.page || 1) - 1) * (filters.page_size || 25) + 1}
            &ndash;{Math.min((filters.page || 1) * (filters.page_size || 25), total)} of {total}
          </p>
          <div className="flex items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page === 1}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) - 1 }))}
              className="gap-1"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Previous
            </Button>
            <div className="flex items-center gap-0.5">
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
                    className={`flex items-center justify-center h-7 min-w-[28px] rounded-md text-xs font-medium tabular-nums transition-all focus-ring ${
                      page === (filters.page || 1)
                        ? 'bg-brand text-white shadow-sm'
                        : 'text-text-secondary hover:bg-bg-muted'
                    }`}
                  >
                    {page}
                  </button>
                );
              })}
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={(filters.page || 1) >= totalPages}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) + 1 }))}
              className="gap-1"
            >
              Next
              <ChevronRight className="h-3.5 w-3.5" />
            </Button>
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
      <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider mb-1.5 block">
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
