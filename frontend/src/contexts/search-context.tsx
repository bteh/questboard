import { createContext, useContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { sseUrl, streamSse } from '@/lib/api-client';
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
  activate: (runId: string, mode: SearchRequest['mode'], snapshot: SearchRunSnapshot) => void;
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

  const activate = useCallback((id: string, m: SearchRequest['mode'], runSnapshot: SearchRunSnapshot) => {
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
              queryClient.invalidateQueries({ queryKey: ['analytics'] });
              return;
            }

            if (event === 'error') {
              setError(data || 'Connection lost');
              setState('failed');
              abortRef.current = null;
              queryClient.invalidateQueries({ queryKey: ['applications'] });
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
      queryClient.invalidateQueries({ queryKey: ['analytics'] });
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
      }
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        // Connection closed permanently — mark failed only if we
        // haven't already completed or received a server error.
        setState((prev) => (prev === 'running' ? 'failed' : prev));
        setError((prev) => prev || 'Connection lost');
        esRef.current = null;
      }
      // readyState === CONNECTING means EventSource is auto-reconnecting
      // — don't interfere, let it retry.
    };

    return () => {
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
