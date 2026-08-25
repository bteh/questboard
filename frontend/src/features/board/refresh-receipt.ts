import type { CareerRefreshReceipt } from '@/api/board';
import type { RunResult, SourceCoverage } from '@/types/search';

export type RefreshReceiptTone = 'good' | 'warn' | 'bad' | 'quiet';

export interface RefreshReceiptCopy {
  text: string;
  tone: RefreshReceiptTone;
  provesNoNewJobs: boolean;
  /* Raw backend error text, present only when the sentence had to
     summarize it. For a renderer's "details" affordance; never for the
     main line. */
  detail?: string;
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

/* receipt.error is either one of the backend's own fixed interruption
   sentences (workspace_service.py) or str(e) of an arbitrary exception
   from the pipeline. The fixed ones map to plain sentences; raw exception
   text never reaches the receipt line, only the detail field. */
const KNOWN_FAILURES: [RegExp, string][] = [
  [/superseded by a newer/i, 'A newer refresh took over before this one finished.'],
  [/interrupted and exhausted/i, 'The refresh was interrupted and gave up after several tries.'],
  [/interrupted/i, 'The refresh was interrupted partway.'],
];
const RATE_LIMIT_SHAPE = /(\b429\b|rate.?limit|too many requests)/i;
const NETWORK_SHAPE =
  /(timed?[\s-]?out|timeout|connection|network|unreachable|refused|resolve|dns|ssl|certificate|proxy|offline|reach|max retries|econn|enotfound)/i;

function plainRefreshFailure(raw: string | null | undefined): { sentence: string; detail?: string } | null {
  const text = raw?.trim();
  if (!text) return null;
  for (const [shape, sentence] of KNOWN_FAILURES) {
    if (shape.test(text)) return { sentence };
  }
  if (RATE_LIMIT_SHAPE.test(text)) {
    return { sentence: 'A source rate-limited the refresh.', detail: text };
  }
  if (NETWORK_SHAPE.test(text)) {
    return { sentence: 'A source could not be reached.', detail: text };
  }
  return { sentence: 'A source failed.', detail: text };
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
    const failure = plainRefreshFailure(receipt.error);
    return {
      text: failure
        ? `Refresh did not finish. ${failure.sentence} This is not an all-clear.`
        : 'Refresh did not finish. This is not an all-clear.',
      tone: 'bad',
      provesNoNewJobs: false,
      ...(failure?.detail ? { detail: failure.detail } : {}),
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
