import { createRoute, Link } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { Skeleton } from '@/components/ui/skeleton';
import { ScoreDistributionChart } from '@/components/charts/score-distribution-chart';
import { RecommendationChart } from '@/components/charts/recommendation-chart';
import { FunnelChart } from '@/components/charts/funnel-chart';
import { SourceChart } from '@/components/charts/source-chart';
import { useScoreDistribution, useRecommendations, useFunnel, useSources, useDashboardStats } from '@/hooks/use-analytics';
import type { DashboardStats } from '@/types/analytics';
import '@/components/log/numbers.css';

/* The old Analytics page, whole: the KPI row and the four charts, retitled
   and reskinned in ink and the canon hues. Same hooks, same data. */

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/log/numbers',
  component: NumbersPage,
});

function ChartCard({ title, description, isLoading, isEmpty, children }: {
  title: string;
  description?: string;
  isLoading: boolean;
  isEmpty: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="qb-chartcard">
      <h2 className="qb-charttitle">{title}</h2>
      {description && <p className="qb-chartsub">{description}</p>}
      {isLoading ? (
        <Skeleton className="h-[280px] w-full rounded-lg" />
      ) : isEmpty ? (
        <div className="qb-chart-empty">No data yet</div>
      ) : (
        children
      )}
    </section>
  );
}

function Kpi({ label, value, suffix }: { label: string; value: number | string; suffix?: string }) {
  return (
    <div className="qb-kpi">
      <div className="qb-kpival">
        {value}
        {suffix}
      </div>
      <div className="qb-kpilab">{label}</div>
    </div>
  );
}

function getKpis(stats: DashboardStats) {
  const avgScore = stats.avg_score != null ? Math.round(stats.avg_score) : 'none yet';
  const interviewRate = stats.applied_count > 0
    ? Math.round((stats.interviewing_count / stats.applied_count) * 100)
    : 0;

  return [
    { label: 'jobs found', value: stats.total_jobs },
    { label: 'average keyword score', value: avgScore },
    { label: 'strong matches', value: stats.strong_apply_count },
    { label: 'applied', value: stats.applied_count },
    { label: 'interview rate', value: interviewRate, suffix: '%' },
  ];
}

function NumbersPage() {
  const { data: stats, isLoading: statsLoading } = useDashboardStats();
  const { data: scores, isLoading: l1 } = useScoreDistribution();
  const { data: recs, isLoading: l2 } = useRecommendations();
  const { data: funnel, isLoading: l3 } = useFunnel();
  const { data: sources, isLoading: l4 } = useSources();

  const noData = !stats || stats.total_jobs === 0;
  const kpis = stats ? getKpis(stats) : [];

  return (
    <div style={{ maxWidth: 1120, margin: '0 auto', padding: '0 44px 96px' }}>
      <div className="qb-numbers-head">
        <Link to="/log" className="qb-textlink" style={{ fontSize: 13.5 }}>
          Your log
        </Link>
        <h1>Your numbers</h1>
        <p className="qb-numbers-sub">Every count below comes from your own tracked jobs.</p>
      </div>

      {noData && !statsLoading && !l1 ? (
        <p style={{ fontSize: 14.5, color: 'var(--soft)' }}>
          Nothing to count yet. Once the board finds jobs for you, the charts fill in on their own.
        </p>
      ) : (
        <>
          <div className="qb-kpirow">
            {statsLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <div key={i} className="qb-kpi"><Skeleton className="h-10 w-full" /></div>
                ))
              : kpis.map((kpi) => <Kpi key={kpi.label} {...kpi} />)}
          </div>

          <div className="qb-chartgrid">
            <ChartCard
              title="Keyword scores"
              description="How closely each job matched your roles and keywords, 0 to 100"
              isLoading={l1}
              isEmpty={!scores?.length}
            >
              <ScoreDistributionChart data={scores || []} />
            </ChartCard>

            <ChartCard
              title="Rough verdicts"
              description="Based on keywords and filters, not your resume"
              isLoading={l2}
              isEmpty={!recs?.length}
            >
              <RecommendationChart data={recs || []} />
            </ChartCard>

            <ChartCard
              title="Your progress"
              description="From found to offer, step by step"
              isLoading={l3}
              isEmpty={!funnel?.length}
            >
              <FunnelChart data={funnel || []} />
            </ChartCard>

            <ChartCard
              title="Jobs by source"
              description="Which boards are finding the most"
              isLoading={l4}
              isEmpty={!sources?.length}
            >
              <SourceChart data={sources || []} />
            </ChartCard>
          </div>
        </>
      )}
    </div>
  );
}
