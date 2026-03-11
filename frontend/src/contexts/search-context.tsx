import { createContext, useContext, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { sseUrl } from '@/lib/api-client';
import type { RunResult, SearchRequest, ProgressUpdate } from '@/types/search';

type SearchState = 'idle' | 'running' | 'completed' | 'failed';

interface SearchContextValue {
  state: SearchState;
  runId: string | null;
  messages: string[];
  result: RunResult | null;
  error: string | null;
  mode: SearchRequest['mode'];
  progress: ProgressUpdate | null;
  /** Called after the backend returns a run_id from POST /search/run */
  activate: (runId: string, mode: SearchRequest['mode']) => void;
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
  activate: () => {},
  reset: () => {},
});

export function SearchProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<SearchState>('idle');
  const [runId, setRunId] = useState<string | null>(null);
  const [mode, setMode] = useState<SearchRequest['mode']>('search_score');
  const [messages, setMessages] = useState<string[]>([]);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState<ProgressUpdate | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const cleanup = useCallback(() => {
    if (esRef.current) {
      esRef.current.close();
      esRef.current = null;
    }
  }, []);

  const activate = useCallback((id: string, m: SearchRequest['mode']) => {
    cleanup();
    setRunId(id);
    setMode(m);
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
  }, [cleanup]);

  // SSE connection — runs whenever runId changes, independent of which page is mounted
  useEffect(() => {
    if (!runId || state !== 'running') return;

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

    es.addEventListener('error', (e) => {
      const errorEvent = e as MessageEvent;
      const errorMsg = errorEvent.data || 'Connection lost';
      setError(errorMsg);
      setState('failed');
      es.close();
      esRef.current = null;
      queryClient.invalidateQueries({ queryKey: ['applications'] });
    });

    es.onerror = () => {
      if (es.readyState === EventSource.CLOSED) {
        // Only mark failed if we haven't already completed
        setState((prev) => (prev === 'running' ? 'failed' : prev));
        esRef.current = null;
      }
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [runId, state, queryClient]);

  return (
    <SearchContext.Provider value={{ state, runId, messages, result, error, mode, progress, activate, reset }}>
      {children}
    </SearchContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useSearchContext() {
  return useContext(SearchContext);
}
