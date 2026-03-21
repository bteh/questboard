import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { bootstrapWorkspaceSession } from '@/api/workspace';
import type { WorkspaceSession } from '@/types/workspace';

interface WorkspaceContextValue {
  session: WorkspaceSession | null;
  isLoading: boolean;
  error: string | null;
  hostedMode: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  session: null,
  isLoading: true,
  error: null,
  hostedMode: true,
});

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<WorkspaceSession | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    bootstrapWorkspaceSession()
      .then((result) => {
        if (!active) return;
        setSession(result);
        setError(null);
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to initialize workspace');
      })
      .finally(() => {
        if (!active) return;
        setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<WorkspaceContextValue>(() => ({
    session,
    isLoading,
    error,
    hostedMode: session?.hosted_mode ?? true,
  }), [session, isLoading, error]);

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useWorkspace() {
  return useContext(WorkspaceContext);
}
