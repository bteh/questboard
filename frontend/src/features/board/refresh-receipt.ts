import type { CareerRefreshReceipt } from '@/api/board';
import type { RunResult, SourceCoverage } from '@/types/search';

export type RefreshReceiptTone = 'good' | 'warn' | 'bad' | 'quiet';

export interface RefreshReceiptCopy {
  text: string;
  tone: RefreshReceiptTone;
  provesNoNewJobs: boolean;
}

export type RefreshReceiptLike = Pick<
  CareerRefreshReceipt,
  'status' | 'jobs_found' | 'new_jobs' | 'error' | 'source_coverage'
>;

export function receiptFromRunResult(result: RunResult): RefreshReceiptLike {
  return {
    status: result.status === 'failed' ? 'failed' : 'completed',
    jobs_found: result.jobs_found,
    new_jobs: result.new_jobs ?? 0,
    error: result.error,
    source_coverage: result.source_coverage ?? null,
  };
}

export function completeSourceCoverage(coverage: SourceCoverage | null | undefined): boolean {
  return Boolean(
    coverage &&
      coverage.total > 0 &&
      coverage.partial === 0 &&
      coverage.failed === 0 &&
      coverage.ok + coverage.zero === coverage.total,
  );
}

function jobsLabel(count: number): string {
  return `${count} new job${count === 1 ? '' : 's'}`;
}

function problemSources(coverage: SourceCoverage): string {
  const problems = coverage.sources.filter(
    (source) => source.state === 'partial' || source.state === 'failed',
  );
  const named = problems.slice(0, 3).map((source) =>
    source.state === 'partial'
      ? `${source.display_name} was partial`
      : `${source.display_name} did not respond`,
  );
  const remaining = problems.length - named.length;
  if (remaining > 0) named.push(`${remaining} more unavailable`);
  if (named.length > 0) return named.join(', ');

  const generic: string[] = [];
  if (coverage.partial > 0) {
    generic.push(`${coverage.partial} partial`);
  }
  if (coverage.failed > 0) {
    generic.push(`${coverage.failed} unavailable`);
  }
  return generic.join(', ') || 'source coverage was incomplete';
}

export function refreshReceiptCopy(receipt: RefreshReceiptLike): RefreshReceiptCopy {
  if (receipt.status === 'pending' || receipt.status === 'running') {
    return {
      text: 'Checking sources now. The board will update after the results are saved.',
      tone: 'quiet',
      provesNoNewJobs: false,
    };
  }
  if (receipt.status === 'failed') {
    return {
      text: `Refresh did not finish${receipt.error ? `: ${receipt.error}` : ''}. This is not an all-clear.`,
      tone: 'bad',
      provesNoNewJobs: false,
    };
  }

  const coverage = receipt.source_coverage;
  const newJobs = Math.max(0, receipt.new_jobs || 0);
  if (!coverage || coverage.total === 0) {
    return {
      text:
        newJobs > 0
          ? `Board updated with ${jobsLabel(newJobs)}, but source coverage could not be verified.`
          : 'Refresh finished, but source coverage could not be verified. This is not an all-clear.',
      tone: 'warn',
      provesNoNewJobs: false,
    };
  }

  const complete = completeSourceCoverage(coverage);
  const withResults = coverage.ok + coverage.partial;
  const coverageText = `${coverage.total} sources checked; ${withResults} returned jobs`;

  if (newJobs === 0 && !complete) {
    return {
      text: `Refresh incomplete: no new jobs were saved, but ${problemSources(coverage)}. This is not an all-clear.`,
      tone: 'warn',
      provesNoNewJobs: false,
    };
  }
  if (newJobs === 0) {
    return {
      text: `No new jobs found. ${coverage.total} sources checked successfully.`,
      tone: 'quiet',
      provesNoNewJobs: true,
    };
  }
  if (!complete) {
    return {
      text: `Board updated with ${jobsLabel(newJobs)}. ${coverageText}; ${problemSources(coverage)}.`,
      tone: 'warn',
      provesNoNewJobs: false,
    };
  }
  return {
    text: `Board updated with ${jobsLabel(newJobs)}. ${coverageText}.`,
    tone: 'good',
    provesNoNewJobs: false,
  };
}

export function refreshAwareSinceLine(
  normalLine: string | null,
  receipt: RefreshReceiptLike | null | undefined,
): string | null {
  if (!receipt) return normalLine;
  if (receipt.status === 'pending' || receipt.status === 'running') {
    return 'Checking sources now. New jobs will appear after the refresh finishes.';
  }
  if (receipt.status === 'failed') {
    return 'The refresh did not finish. Questboard cannot confirm there were no new jobs.';
  }
  if ((receipt.new_jobs || 0) === 0 && !completeSourceCoverage(receipt.source_coverage)) {
    return 'Source coverage was incomplete. Questboard cannot confirm there were no new jobs.';
  }
  return normalLine;
}
