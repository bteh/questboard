import type { RunStatus } from '@/types/search';

// A pull takes 3 to 6 minutes and the backend has no hard run lifetime (a
// worker holds a renewable 120s lease), so this ceiling only exists to stop a
// truly orphaned run from spinning forever. It is measured in wall-clock time
// because timers in a hidden webview are throttled.
export const RECONCILE_CEILING_MS = 20 * 60 * 1000;
export const RECONCILE_INTERVAL_MS = 3000;

export type ReconcileOutcome =
  | { kind: 'completed'; status: RunStatus }
  | { kind: 'failed'; error: string }
  | { kind: 'timeout' }
  | { kind: 'cancelled' };

export function classifyRunStatus(status: RunStatus): ReconcileOutcome | null {
  if (status.status === 'completed') return { kind: 'completed', status };
  if (status.status === 'failed') return { kind: 'failed', error: status.error || 'The run failed' };
  return null;
}

export interface ReconcileHandle {
  done: Promise<ReconcileOutcome>;
  /** Skip the current wait and check the run now. */
  poke: () => void;
  cancel: () => void;
}

interface ReconcileOptions {
  intervalMs?: number;
  ceilingMs?: number;
  now?: () => number;
}

export function startRunReconcile(
  runId: string,
  getStatus: (runId: string) => Promise<RunStatus>,
  { intervalMs = RECONCILE_INTERVAL_MS, ceilingMs = RECONCILE_CEILING_MS, now = Date.now }: ReconcileOptions = {},
): ReconcileHandle {
  let cancelled = false;
  let wake: (() => void) | null = null;

  const wait = () =>
    new Promise<void>((resolve) => {
      const timer = setTimeout(finish, intervalMs);
      function finish() {
        clearTimeout(timer);
        wake = null;
        resolve();
      }
      wake = finish;
    });

  const done = (async (): Promise<ReconcileOutcome> => {
    const startedAt = now();
    while (!cancelled) {
      try {
        const outcome = classifyRunStatus(await getStatus(runId));
        if (cancelled) break;
        if (outcome) return outcome;
      } catch {
        // status not readable yet, retry
      }
      if (now() - startedAt >= ceilingMs) return { kind: 'timeout' };
      await wait();
    }
    return { kind: 'cancelled' };
  })();

  return {
    done,
    poke: () => wake?.(),
    cancel: () => {
      cancelled = true;
      wake?.();
    },
  };
}
