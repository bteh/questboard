import { createRoute } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { BarChart3, Target, TrendingUp, Briefcase, Star, Send } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/page-header';
import { EmptyState } from '@/components/shared/empty-state';
import { ScoreDistributionChart } from '@/components/charts/score-distribution-chart';
import { RecommendationChart } from '@/components/charts/recommendation-chart';
import { FunnelChart } from '@/components/charts/funnel-chart';
import { SourceChart } from '@/components/charts/source-chart';
import { useScoreDistribution, useRecommendations, useFunnel, useSources, useDashboardStats } from '@/hooks/use-analytics';
import type { DashboardStats } from '@/types/analytics';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/analytics',
  component: AnalyticsPage,
});

function ChartCard({ title, description, isLoading, isEmpty, children, className }: {
  title: string;
  description?: string;
  isLoading: boolean;
  isEmpty: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-text-primary">{title}</CardTitle>
        {description && <p className="text-xs text-text-muted">{description}</p>}
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[280px] w-full rounded-lg" />
        ) : isEmpty ? (
          <div className="h-[280px] flex items-center justify-center text-sm text-text-muted">No data available</div>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

function KpiCard({ label, value, icon: Icon, bg, fg, suffix, isLoading }: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  bg: string;
  fg: string;
  suffix?: string;
  isLoading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        {isLoading ? (
          <Skeleton className="h-10 w-full" />
        ) : (
          <>
            <div className={`flex h-9 w-9 items-center justify-center rounded-lg shrink-0 ${bg}`}>
              <Icon className={`h-4 w-4 ${fg}`} />
            </div>
            <div className="min-w-0">
              <p className="text-xl font-bold text-text-primary tabular-nums leading-none">
                {value}{suffix}
              </p>
              <p className="text-[11px] text-text-muted font-medium mt-1">{label}</p>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function getKpis(stats: DashboardStats) {
  const avgScore = stats.avg_score != null ? Math.round(stats.avg_score) : '—';
  const interviewRate = stats.applied_count > 0
    ? Math.round((stats.interviewing_count / stats.applied_count) * 100)
    : 0;

  return [
    { label: 'Jobs Found', value: stats.total_jobs, icon: Briefcase, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Avg Match Score', value: avgScore, icon: Target, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Strong Matches', value: stats.strong_apply_count, icon: Star, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Applied', value: stats.applied_count, icon: Send, bg: 'bg-brand-light', fg: 'text-brand' },
    { label: 'Interview Rate', value: interviewRate, icon: TrendingUp, bg: 'bg-brand-light', fg: 'text-brand' },
  ] as const;
}

function AnalyticsPage() {
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: scores, isLoading: l1 } = useScoreDistribution();
  const { data: recs, isLoading: l2 } = useRecommendations();
  const { data: funnel, isLoading: l3 } = useFunnel();
  const { data: sources, isLoading: l4 } = useSources();

  const noData = !stats || stats.total_jobs === 0;

  if (noData && !statsLoading && !l1) {
    return (
      <div>
        <PageHeader title="Analytics" description="Insights and trends from your job search" />
        <EmptyState icon={BarChart3} title="No analytics data" description="Run a search to start seeing insights about your job market." />
      </div>
    );
  }

  const kpis = stats ? getKpis(stats) : [];

  return (
    <div>
      <PageHeader title="Analytics" description="Insights and trends from your job search" />

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-8">
        {statsLoading
          ? Array.from({ length: 5 }).map((_, i) => (
              <Card key={i}><CardContent className="p-4"><Skeleton className="h-10 w-full" /></CardContent></Card>
            ))
          : kpis.map((kpi) => (
              <KpiCard key={kpi.label} {...kpi} />
            ))
        }
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ChartCard
          title="Match Scores"
          description="How well jobs match your resume on a 0–100 scale"
          isLoading={l1}
          isEmpty={!scores?.length}
        >
          <ScoreDistributionChart data={scores || []} />
        </ChartCard>

        <ChartCard
          title="Recommendations"
          description="How many jobs are worth applying to"
          isLoading={l2}
          isEmpty={!recs?.length}
        >
          <RecommendationChart data={recs || []} />
        </ChartCard>

        <ChartCard
          title="Your Progress"
          description="Track your journey from discovery to offer"
          isLoading={l3}
          isEmpty={!funnel?.length}
        >
          <FunnelChart data={funnel || []} />
        </ChartCard>

        <ChartCard
          title="Jobs by Source"
          description="Which job boards are finding the most results"
          isLoading={l4}
          isEmpty={!sources?.length}
        >
          <SourceChart data={sources || []} />
        </ChartCard>
      </div>
    </div>
  );
}
