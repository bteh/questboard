import { describe, expect, it } from 'vitest';

import {
  completeSourceCoverage,
  refreshAwareSinceLine,
  refreshReceiptCopy,
} from './refresh-receipt';
import type { SourceCoverage } from '@/types/search';

const complete: SourceCoverage = {
  total: 3,
  ok: 2,
  zero: 1,
  partial: 0,
  failed: 0,
  sources: [
    { source: 'linkedin', display_name: 'LinkedIn', state: 'ok', rows_found: 90, attempts: 3, failed_attempts: 0, error: '' },
    { source: 'indeed', display_name: 'Indeed', state: 'ok', rows_found: 80, attempts: 3, failed_attempts: 0, error: '' },
    { source: 'remoteok', display_name: 'RemoteOK', state: 'zero', rows_found: 0, attempts: 1, failed_attempts: 0, error: '' },
  ],
};

describe('refresh receipt copy', () => {
  it('permits a no-new conclusion only after every source completed', () => {
    const copy = refreshReceiptCopy({
      status: 'completed',
      jobs_found: 0,
      new_jobs: 0,
      error: null,
      source_coverage: complete,
    });
    expect(copy.text).toBe('No new jobs found. 3 sources checked successfully.');
    expect(copy.provesNoNewJobs).toBe(true);
  });

  it('turns a partial zero into an explicit non-conclusion', () => {
    const coverage: SourceCoverage = {
      ...complete,
      ok: 1,
      partial: 1,
      sources: complete.sources.map((source) =>
        source.source === 'linkedin' ? { ...source, state: 'partial' as const, failed_attempts: 1 } : source,
      ),
    };
    const copy = refreshReceiptCopy({
      status: 'completed',
      jobs_found: 0,
      new_jobs: 0,
      error: null,
      source_coverage: coverage,
    });
    expect(copy.text).toContain('LinkedIn was partial');
    expect(copy.text).toContain('not an all-clear');
    expect(copy.provesNoNewJobs).toBe(false);
  });

  it('names useful results and the partial source together', () => {
    const coverage: SourceCoverage = {
      ...complete,
      ok: 1,
      partial: 1,
      sources: complete.sources.map((source) =>
        source.source === 'linkedin' ? { ...source, state: 'partial' as const, failed_attempts: 1 } : source,
      ),
    };
    expect(
      refreshReceiptCopy({
        status: 'completed',
        jobs_found: 530,
        new_jobs: 265,
        error: null,
        source_coverage: coverage,
      }).text,
    ).toBe('Board updated with 265 new jobs. 3 sources checked; 2 returned jobs; LinkedIn was partial.');
  });

  it('fails closed when an older backend has no coverage receipt', () => {
    const copy = refreshReceiptCopy({
      status: 'completed',
      jobs_found: 0,
      new_jobs: 0,
      error: null,
      source_coverage: null,
    });
    expect(copy.text).toContain('coverage could not be verified');
    expect(copy.provesNoNewJobs).toBe(false);
  });
});

describe('refresh-aware new-since line', () => {
  it('never leaves the old nothing-new line visible during a run', () => {
    expect(
      refreshAwareSinceLine('No jobs added since your last visit', {
        status: 'running',
        jobs_found: 0,
        new_jobs: 0,
        error: null,
        source_coverage: null,
      }),
    ).toContain('Checking sources now');
  });

  it('replaces a false zero after incomplete coverage', () => {
    expect(
      refreshAwareSinceLine('No jobs added since your last visit', {
        status: 'completed',
        jobs_found: 0,
        new_jobs: 0,
        error: null,
        source_coverage: { ...complete, ok: 1, partial: 1 },
      }),
    ).toContain('cannot confirm');
  });

  it('keeps the board-local line after a fully verified refresh', () => {
    expect(
      refreshAwareSinceLine('No jobs added since your last visit', {
        status: 'completed',
        jobs_found: 0,
        new_jobs: 0,
        error: null,
        source_coverage: complete,
      }),
    ).toBe('No jobs added since your last visit');
    expect(completeSourceCoverage(complete)).toBe(true);
  });
});
