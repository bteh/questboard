import { createContext, useContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { sseUrl, streamSse } from '@/lib/api-client';
import { getRunStatus } from '@/api/search';
import { classifyRunStatus, startRunReconcile, type ReconcileHandle, type ReconcileOutcome } from '@/contexts/reconcile-run';
import { useWorkspace } from '@/contexts/workspace-context';
import type { RunResult, SearchRequest, ProgressUpdate, SearchRunSnapshot } from '@/types/search';

type SearchState = 'idle' | 'running' | 'completed' | 'failed';

interface SearchContextValue {
  state: SearchState;
  runId: string | null;
  messages: string[];
  result: RunResult | null;
  error: string | null;
  mode: SearchRequest['mode'];
  progress: ProgressUpdate | null;
  snapshot: SearchRunSnapshot | null;
  /** Called after the backend returns a run_id from POST /search/run */
  activate: (runId: string, mode: SearchRequest['mode'], snapshot?: SearchRunSnapshot | null) => void;
  reset: () => void;
}

const SearchContext = createContext<SearchContextValue>({
  state: 'idle',
  runId: null,
  messages: [],
  result: null,
  error: null,
  mode: 'search_score',
  progress: null,
  snapshot: null,
  activate: () => {},
  reset: () => {},
});

export function SearchProvider({ children }: { children: ReactNode }) {
  const { hostedMode } = useWorkspace();
  const queryClient = useQueryClient();
  const [state, setState] = useState<SearchState>('idle');
  const [runId, setRunId] = useState<string | null>(null);
  const [mode, setMode] = useState<SearchRequest['mode']>('search_score');
  const [messages, setMessages] = useState<string[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const [snapshot, setSnapshot] = useState<SearchRunSnapshot | null>(null);
  const esRef = useRef<EventSource | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cleanup = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const activate = useCallback((id: string, m: SearchRequest['mode'], runSnapshot: SearchRunSnapshot | null = null) => {
    cleanup();
    setRunId(id);
    setMode(m);
    setSnapshot(runSnapshot);
    setState('running');
    setMessages([]);
    setResult(null);
    setError(null);
    setProgress(null);
  }, [cleanup]);

  const reset = useCallback(() => {
    cleanup();
    setState('idle');
    setRunId(null);
    setMessages([]);
    setResult(null);
    setError(null);
    setProgress(null);
    setSnapshot(null);
  }, [cleanup]);

  // SSE connection — runs whenever runId changes, independent of which page is mounted
  useEffect(() => {
    if (!runId || state !== 'running') return;

    if (hostedMode) {
      const controller = new AbortController();
      abortRef.current = controller;

      void streamSse(
        `/search/runs/${runId}/progress`,
        {
          onEvent: (event, data) => {
            if (event === 'progress') {
              setMessages((prev) => [...prev, data]);
              return;
            }

            if (event === 'stage') {
              try {
                setProgress(JSON.parse(data) as ProgressUpdate);
              } catch {
                // ignore malformed stage payloads
              }
              return;
            }

            if (event === 'complete') {
              try {
                const r = JSON.parse(data) as RunResult;
                setResult(r);
              } catch {
                setResult({
                  run_id: runId,
                  status: 'completed',
                  jobs_found: 0,
                  jobs_scored: 0,
                  strong_matches: 0,
                  duration_seconds: 0,
                  error: null,
                });
              }
              setState('completed');
              abortRef.current = null;
              queryClient.invalidateQueries({ queryKey: ['applications'] });
              queryClient.invalidateQueries({ queryKey: ['profile-work'] });
              queryClient.invalidateQueries({ queryKey: ['analytics'] });
              // Refresh the "sources checked" freshness so it stops showing a
              // stale "6h ago" the moment a fresh run finishes.
              queryClient.invalidateQueries({ queryKey: ['board-summary'] });
              return;
            }

            if (event === 'error') {
              setError(data || 'Connection lost');
              setState('failed');
              abortRef.current = null;
              queryClient.invalidateQueries({ queryKey: ['applications'] });
              queryClient.invalidateQueries({ queryKey: ['profile-work'] });
              queryClient.invalidateQueries({ queryKey: ['board-summary'] });
            }
          },
        },
        controller.signal,
      ).catch((err) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Connection lost');
        setState('failed');
        abortRef.current = null;
      });

      return () => {
        controller.abort();
        abortRef.current = null;
      };
    }

    const es = new EventSource(sseUrl(`/search/runs/${runId}/progress`));
    esRef.current = es;

    es.addEventListener('progress', (e) => {
      setMessages((prev) => [...prev, e.data]);
    });

    es.addEventListener('stage', (e) => {
      try {
        setProgress(JSON.parse(e.data) as ProgressUpdate);
      } catch { /* ignore malformed */ }
    });

    es.addEventListener('complete', (e) => {
      try {
        const r = JSON.parse(e.data) as RunResult;
        setResult(r);
      } catch {
        setResult({
          run_id: runId,
          status: 'completed',
          jobs_found: 0,
          jobs_scored: 0,
          strong_matches: 0,
          duration_seconds: 0,
          error: null,
        });
      }
      setState('completed');
      es.close();
      esRef.current = null;
      queryClient.invalidateQueries({ queryKey: ['applications'] });
      queryClient.invalidateQueries({ queryKey: ['profile-work'] });
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
      queryClient.invalidateQueries({ queryKey: ['board-summary'] });
    });

    // Server-sent error events have data; native connection errors don't.
    // Only handle server-sent errors here — connection drops are handled
    // by onerror below.
    es.addEventListener('error', (e) => {
      const errorEvent = e as MessageEvent;
      if (errorEvent.data) {
        setError(errorEvent.data);
        setState('failed');
        es.close();
        esRef.current = null;
        queryClient.invalidateQueries({ queryKey: ['applications'] });
        queryClient.invalidateQueries({ queryKey: ['profile-work'] });
        queryClient.invalidateQueries({ queryKey: ['board-summary'] });
      }
    });

    let reconcile: ReconcileHandle | null = null;

    const applyOutcome = (outcome: ReconcileOutcome) => {
      if (outcome.kind === 'cancelled') return;
      if (outcome.kind === 'completed') {
        const s = outcome.status;
        setResult({
          run_id: runId,
          status: 'completed',
          jobs_found: s.jobs_found ?? 0,
          new_jobs: s.new_jobs ?? 0,
          jobs_scored: s.jobs_scored ?? 0,
          strong_matches: 0,
          duration_seconds: 0,
          error: null,
          source_coverage: s.source_coverage ?? null,
        });
        setState('completed');
        queryClient.invalidateQueries({ queryKey: ['applications'] });
        queryClient.invalidateQueries({ queryKey: ['profile-work'] });
        queryClient.invalidateQueries({ queryKey: ['board-summary'] });
        return;
      }
      if (outcome.kind === 'failed') {
        setError(outcome.error);
        setState('failed');
        return;
      }
      setState((prev) => (prev === 'running' ? 'failed' : prev));
      setError((prev) => prev || 'Lost contact with the run. Your board may still have updated');
    };

    es.onerror = () => {
      if (es.readyState !== EventSource.CLOSED || reconcile) return;
      esRef.current = null;
      // The stream dropped (a minimized desktop window lets macOS suspend the
      // webview), but the run almost always keeps going server-side. Follow the
      // real run status until it is terminal instead of guessing from silence.
      reconcile = startRunReconcile(runId, getRunStatus);
      void reconcile.done.then(applyOutcome);
    };

    // Timers in a hidden webview are throttled, so check the run as soon as the
    // window is back instead of waiting out a sleeping poll.
    let disposed = false;
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (reconcile) {
        reconcile.poke();
        return;
      }
      void getRunStatus(runId)
        .then((s) => {
          const outcome = classifyRunStatus(s);
          if (disposed || reconcile || !outcome) return;
          es.close();
          esRef.current = null;
          applyOutcome(outcome);
        })
        .catch(() => {});
    };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onVisible);

    return () => {
      disposed = true;
      reconcile?.cancel();
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onVisible);
      es.close();
      esRef.current = null;
    };
  }, [hostedMode, runId, state, queryClient]);

  return (
    <SearchContext.Provider value={{ state, runId, messages, result, error, mode, progress, snapshot, activate, reset }}>
      {children}
    </SearchContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSearchContext() {
  return useContext(SearchContext);
}
