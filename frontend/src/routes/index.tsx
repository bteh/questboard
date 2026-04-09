import { useMemo } from 'react';
import { createRoute, Link, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { Briefcase, Star, Send, Phone, Inbox, ArrowRight, Search, Loader2 } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/page-header';
import { JobCard } from '@/components/jobs/job-card';
import { ActivityItem } from '@/components/shared/activity-item';
import { FirstRunHero } from '@/components/onboarding/first-run-hero';
import { ReadyToLaunchHero } from '@/components/onboarding/ready-to-launch-hero';
import { useDashboardStats } from '@/hooks/use-analytics';
import { useApplications } from '@/hooks/use-applications';
import { pickLatestCompletedRun, useSearchRuns } from '@/hooks/use-search';
import { useOnboardingState } from '@/hooks/use-workspace';
import { useProfile } from '@/contexts/profile-context';
import { useSearchContext } from '@/contexts/search-context';
import { useSourceLabels } from '@/hooks/use-scrapers';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
});

function DashboardPage() {
  const navigate = useNavigate();
  const { profile } = useProfile();
  const { state: searchState } = useSearchContext();
  const sourceLabels = useSourceLabels();
  const { data: runs, isLoading: runsLoading } = useSearchRuns(10);
  const { data: onboarding, isLoading: onboardingLoading } = useOnboardingState();
  const latestCompletedRun = useMemo(() => pickLatestCompletedRun(runs), [runs]);
  const latestRunId = latestCompletedRun?.run_id;
  const { data: stats, isLoading: statsLoading } = useDashboardStats(latestRunId);
  const { data: appData, isLoading: appsLoading } = useApplications({
    sort_by: 'overall_score',
    sort_order: 'desc',
    page_size: 5,
    profile,
    search_run_id: latestRunId,
  });

  const { data: recentData, isLoading: recentLoading } = useApplications({
    sort_by: 'date_found',
    sort_order: 'desc',
    page_size: 5,
    profile,
    search_run_id: latestRunId,
  });

  const topJobs = appData?.items || [];
  const recentActivity = useMemo(() => recentData?.items?.slice(0, 5) || [], [recentData?.items]);

  // Two pre-search empty states, both ahead of the populated dashboard:
  //   1. true first run — no resume, no roles, no preferences saved → upload hero
  //   2. ready to launch — wizard finished, preferences saved, but Start
  //      hasn't been clicked yet → "you're ready" review hero
  // Once a search has actually started, fall through to the populated
  // dashboard layout below. NB: this branch must come AFTER all hooks above
  // to keep hook ordering stable.
  const dataReady = !runsLoading && !onboardingLoading && onboarding != null;
  const noRunStarted = dataReady && !onboarding.has_started_search && (!runs || runs.length === 0);
  const hasAnyPreferences =
    dataReady &&
    (onboarding.resume.exists ||
      onboarding.preferences.roles.length > 0 ||
      onboarding.preferences.keywords.length > 0);

  if (noRunStarted && searchState === 'idle') {
    if (hasAnyPreferences) {
      return <ReadyToLaunchHero />;
    }
    return <FirstRunHero />;
  }

  const metrics = [
    { label: 'Total found', value: stats?.total_jobs ?? 0, icon: Briefcase, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Strong matches', value: stats?.strong_apply_count ?? 0, icon: Star, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Applied', value: stats?.applied_count ?? 0, icon: Send, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Interviewing', value: stats?.interviewing_count ?? 0, icon: Phone, bg: 'bg-brand-light', fg: 'text-brand' },
  ];

  return (
    <div>
      <PageHeader title="Dashboard" description="Your job search at a glance">
        <Button
          onClick={() => navigate({ to: '/search' })}
          size="sm"
        >
          {searchState === 'running' ? (
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Searching…</>
          ) : (
            <><Search className="h-4 w-4 mr-2" /> New search</>
          )}
        </Button>
      </PageHeader>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {metrics.map((m) => (
          <Card key={m.label} className="card-interactive">
            <CardContent className="flex items-center gap-4 p-5">
              {statsLoading ? (
                <Skeleton className="h-12 w-full" />
              ) : (
                <>
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg shrink-0 ${m.bg}`}>
                    <m.icon className={`h-4 w-4 ${m.fg}`} />
                  </div>
                  <div>
                    <p className="text-xl font-semibold text-text-primary tabular-nums">{m.value}</p>
                    <p className="text-xs text-text-muted">{m.label}</p>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="mb-4 flex items-center justify-between gap-4">
        <p className="text-xs text-text-muted">
          {latestRunId
            ? `Showing your latest completed search${stats?.total_jobs != null ? ` · ${stats.total_jobs} jobs in scope` : ''}`
            : (topJobs.length > 0 ? `Showing top opportunities from ${stats?.total_jobs ?? 0} tracked jobs` : 'No completed search yet. Your dashboard will populate after the first run.')}
        </p>
        {latestRunId ? (
          <Link to="/applications" search={{ scope: 'all', run: undefined }} className="text-xs text-brand hover:text-brand-hover transition-colors inline-flex items-center gap-1">
            Browse all tracked jobs <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : null}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Top opportunities */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-text-primary">
              {latestRunId ? 'Top matches from your latest search' : 'Top opportunities'}
            </h2>
            {topJobs.length > 0 && (
              <Link to="/applications" search={{ run: latestRunId ?? undefined, scope: latestRunId ? undefined : 'all' }} className="text-sm text-brand hover:text-brand-hover transition-colors inline-flex items-center gap-1">
                {latestRunId ? 'View latest search' : 'View all'} <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
          {appsLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-32 w-full rounded-lg" />
              ))}
            </div>
          ) : topJobs.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mb-5">
                <Inbox className="h-7 w-7 text-brand" />
              </div>
              {latestRunId ? (
                <>
                  <h3 className="text-base font-semibold text-text-primary mb-1.5">No matches in your latest search</h3>
                  <p className="text-sm text-text-tertiary mb-5 max-w-sm leading-relaxed">
                    Your most recent run did not keep any jobs after filtering. You can adjust your search criteria or browse older tracked jobs.
                  </p>
                  <div className="flex items-center gap-3">
                    <Button onClick={() => navigate({ to: '/search' })} size="sm">
                      <Search className="h-4 w-4 mr-2" /> Refine search
                    </Button>
                    <Button onClick={() => navigate({ to: '/applications', search: { scope: 'all', run: undefined } })} variant="outline" size="sm">
                      Browse history
                    </Button>
                  </div>
                </>
              ) : (
                <>
                  <h3 className="text-base font-semibold text-text-primary mb-1.5">Welcome to Launchboard</h3>
                  <p className="text-sm text-text-tertiary mb-5 max-w-sm leading-relaxed">
                    Search multiple job boards at once, see which jobs match your skills and experience, and track your applications — all in one place.
                  </p>
                  <Button onClick={() => navigate({ to: '/search' })} size="sm">
                    <Search className="h-4 w-4 mr-2" /> Start your first search
                  </Button>
                </>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              {topJobs.map((app) => (
                <JobCard key={app.id} app={app} sourceLabels={sourceLabels} />
              ))}
            </div>
          )}
        </div>

        {/* Recent activity */}
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-4">
            {latestRunId ? 'Recent matches' : 'Recent activity'}
          </h2>
          <Card>
            <CardContent className="p-4">
              {recentLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : recentActivity.length === 0 ? (
                <p className="text-sm text-text-tertiary py-8 text-center">Activity will appear here as you track jobs.</p>
              ) : (
                <div className="divide-y divide-border-default">
                  {recentActivity.map((app) => (
                    <ActivityItem key={app.id} app={app} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
