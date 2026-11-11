import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RunStatus } from '@/types/search';
import { RECONCILE_CEILING_MS, startRunReconcile } from './reconcile-run';

function status(s: RunStatus['status'], extra: Partial<RunStatus> = {}): RunStatus {
  return {
    run_id: 'run1',
    status: s,
    started_at: null,
    completed_at: null,
    progress_messages: [],
    jobs_found: 0,
    jobs_scored: 0,
    error: null,
    ...extra,
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('startRunReconcile', () => {
  it('follows a run that stays running for six minutes until it completes', async () => {
    const started = Date.now();
    const getStatus = vi.fn(async () =>
      Date.now() - started < 6 * 60 * 1000 ? status('running') : status('completed', { jobs_found: 9 }),
    );
    const handle = startRunReconcile('run1', getStatus);

    await vi.advanceTimersByTimeAsync(7 * 60 * 1000);

    await expect(handle.done).resolves.toMatchObject({ kind: 'completed', status: { jobs_found: 9 } });
  });

  it('treats pending as still going', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce(status('pending'))
      .mockResolvedValueOnce(status('completed'));
    const handle = startRunReconcile('run1', getStatus);

    await vi.advanceTimersByTimeAsync(3000);

    await expect(handle.done).resolves.toMatchObject({ kind: 'completed' });
  });

  it('reports a terminal failure with the server error', async () => {
    const handle = startRunReconcile('run1', async () => status('failed', { error: 'scraper crashed' }));

    await expect(handle.done).resolves.toEqual({ kind: 'failed', error: 'scraper crashed' });
  });

  it('retries through unreadable status responses', async () => {
    const getStatus = vi
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(status('completed'));
    const handle = startRunReconcile('run1', getStatus);

    await vi.advanceTimersByTimeAsync(3000);

    await expect(handle.done).resolves.toMatchObject({ kind: 'completed' });
  });

  it('gives up only after the wall-clock ceiling', async () => {
    const handle = startRunReconcile('run1', async () => status('running'));
    let settled = false;
    void handle.done.then(() => {
      settled = true;
    });

    await vi.advanceTimersByTimeAsync(RECONCILE_CEILING_MS - 10_000);
    expect(settled).toBe(false);

    await vi.advanceTimersByTimeAsync(20_000);
    await expect(handle.done).resolves.toEqual({ kind: 'timeout' });
  });

  it('poke checks the run immediately instead of waiting out the interval', async () => {
    const getStatus = vi
      .fn()
      .mockResolvedValueOnce(status('running'))
      .mockResolvedValueOnce(status('completed'));
    const handle = startRunReconcile('run1', getStatus, { intervalMs: 60_000 });
    await vi.advanceTimersByTimeAsync(0);

    handle.poke();
    await vi.advanceTimersByTimeAsync(0);

    expect(getStatus).toHaveBeenCalledTimes(2);
    await expect(handle.done).resolves.toMatchObject({ kind: 'completed' });
  });

  it('stops polling once cancelled', async () => {
    const getStatus = vi.fn(async () => status('running'));
    const handle = startRunReconcile('run1', getStatus);
    await vi.advanceTimersByTimeAsync(0);

    handle.cancel();
    await expect(handle.done).resolves.toEqual({ kind: 'cancelled' });
    const calls = getStatus.mock.calls.length;

    await vi.advanceTimersByTimeAsync(60_000);
    expect(getStatus).toHaveBeenCalledTimes(calls);
  });
});
