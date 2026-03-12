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
import { useDashboardStats } from '@/hooks/use-analytics';
import { useApplications } from '@/hooks/use-applications';
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
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: appData, isLoading: appsLoading } = useApplications({
    sort_by: 'overall_score',
    sort_order: 'desc',
    page_size: 5,
    profile,
  });

  const { data: recentData, isLoading: recentLoading } = useApplications({
    sort_by: 'date_found',
    sort_order: 'desc',
    page_size: 5,
    profile,
  });

  const topJobs = appData?.items || [];
  const recentActivity = useMemo(() => recentData?.items?.slice(0, 5) || [], [recentData?.items]);

  const metrics = [
    { label: 'Total Found', value: stats?.total_jobs ?? 0, icon: Briefcase, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Strong Matches', value: stats?.strong_apply_count ?? 0, icon: Star, bg: 'bg-brand-light', fg: 'text-brand' },
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
            <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Searching...</>
          ) : (
            <><Search className="h-4 w-4 mr-2" /> New Search</>
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

      {topJobs.length > 0 && (
        <p className="text-xs text-text-muted mb-4">
          Showing top opportunities from {stats?.total_jobs ?? 0} tracked jobs
        </p>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Top Opportunities */}
        <div className="lg:col-span-2">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-text-primary">Top Opportunities</h2>
            {topJobs.length > 0 && (
              <Link to="/applications" className="text-sm text-brand hover:text-brand-hover transition-colors inline-flex items-center gap-1">
                View all <ArrowRight className="h-3.5 w-3.5" />
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
              <h3 className="text-base font-semibold text-text-primary mb-1.5">Welcome to Launchboard</h3>
              <p className="text-sm text-text-tertiary mb-5 max-w-sm leading-relaxed">
                Search multiple job boards at once, see which jobs match your skills and experience, and track your applications — all in one place.
              </p>
              <Button onClick={() => navigate({ to: '/search' })} size="sm">
                <Search className="h-4 w-4 mr-2" /> Start Your First Search
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {topJobs.map((app) => (
                <JobCard key={app.id} app={app} sourceLabels={sourceLabels} />
              ))}
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <div>
          <h2 className="text-lg font-semibold text-text-primary mb-4">Recent Activity</h2>
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
