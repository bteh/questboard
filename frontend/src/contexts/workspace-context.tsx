import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { getDevHostedPersonas, registerDevHostedAccount, signInAsDevHostedPersona } from '@/api/dev-auth';
import { bootstrapWorkspaceSession, getHostedBootstrap } from '@/api/workspace';
import { setApiAccessToken, setLocalWorkspaceSession } from '@/lib/api-client';
import {
  clearDevHostedSession,
  devHostedAuth,
  loadDevHostedSession,
  saveDevHostedSession,
} from '@/lib/dev-hosted-auth';
import { hostedMode as hostedModeEnv, supabase } from '@/lib/supabase';
import type {
  DevHostedPersona,
  HostedBootstrap,
  HostedFeatureFlags,
  HostedUserProfile,
  WorkspaceSession,
} from '@/types/workspace';

type WorkspaceSessionValue = WorkspaceSession | HostedBootstrap;

let localBootstrapInFlight: Promise<WorkspaceSession> | null = null;

function requestLocalBootstrap(): Promise<WorkspaceSession> {
  if (!localBootstrapInFlight) {
    localBootstrapInFlight = bootstrapWorkspaceSession().finally(() => {
      localBootstrapInFlight = null;
    });
  }
  return localBootstrapInFlight;
}

interface WorkspaceContextValue {
  session: WorkspaceSessionValue | null;
  isLoading: boolean;
  error: string | null;
  hostedMode: boolean;
  authMode: 'local' | 'hosted-supabase' | 'hosted-dev';
  devHostedAuth: boolean;
  isAuthenticated: boolean;
  user: HostedUserProfile | null;
  features: HostedFeatureFlags | null;
  workspaceId: string | null;
  personas: DevHostedPersona[];
  currentPersona: DevHostedPersona | null;
  signInWithTestAccount: (email: string, fullName: string, reset?: boolean) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  sendMagicLink: (email: string) => Promise<void>;
  signInAsPersona: (personaId: string, reset?: boolean) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue>({
  session: null,
  isLoading: true,
  error: null,
  hostedMode: hostedModeEnv,
  authMode: hostedModeEnv ? (devHostedAuth ? 'hosted-dev' : 'hosted-supabase') : 'local',
  devHostedAuth,
  isAuthenticated: false,
  user: null,
  features: null,
  workspaceId: null,
  personas: [],
  currentPersona: null,
  signInWithTestAccount: async () => {},
  signInWithGoogle: async () => {},
  sendMagicLink: async () => {},
  signInAsPersona: async () => {},
  signOut: async () => {},
  refresh: async () => {},
});

function isHostedBootstrap(session: WorkspaceSessionValue | null): session is HostedBootstrap {
  return Boolean(session && 'user' in session);
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<WorkspaceSessionValue | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [personas, setPersonas] = useState<DevHostedPersona[]>([]);

  useEffect(() => {
    let active = true;

    async function loadLocal() {
      setIsLoading(true);
      try {
        const result = await requestLocalBootstrap();
        if (!active) return;
        setLocalWorkspaceSession(result.session_token ?? null, result.csrf_token ?? null);
        setSession(result);
        setError(null);
      } catch (err) {
        if (!active) return;
        setLocalWorkspaceSession(null, null);
        setError(err instanceof Error ? err.message : 'Failed to initialize workspace');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    async function loadHostedDev() {
      setIsLoading(true);
      try {
        const personaList = await getDevHostedPersonas();
        if (!active) return;
        setPersonas(personaList);

        const stored = loadDevHostedSession();
        const token = stored?.accessToken ?? null;
        setLocalWorkspaceSession(null, null);
        setApiAccessToken(token);
        if (!token) {
          setSession(null);
          setError(null);
          return;
        }

        const result = await getHostedBootstrap();
        if (!active) return;
        setSession(result);
        setError(null);
      } catch (err) {
        if (!active) return;
        clearDevHostedSession();
        setLocalWorkspaceSession(null, null);
        setApiAccessToken(null);
        setSession(null);
        setError(err instanceof Error ? err.message : 'Failed to initialize local hosted sandbox');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    async function loadHosted() {
      if (!supabase) {
        setError('Hosted auth is not configured');
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      try {
        const {
          data: { session: authSession },
        } = await supabase.auth.getSession();
        const token = authSession?.access_token ?? null;
        setLocalWorkspaceSession(null, null);
        setApiAccessToken(token);
        if (!token) {
          if (!active) return;
          setSession(null);
          setError(null);
          return;
        }
        const result = await getHostedBootstrap();
        if (!active) return;
        setSession(result);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : 'Failed to initialize hosted session');
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    if (!hostedModeEnv) {
      void loadLocal();
      return () => {
        active = false;
      };
    }

    if (devHostedAuth) {
      void loadHostedDev();
      return () => {
        active = false;
      };
    }

    void loadHosted();
    const subscription = supabase?.auth.onAuthStateChange((_event, authSession) => {
      setLocalWorkspaceSession(null, null);
      setApiAccessToken(authSession?.access_token ?? null);
      if (!authSession?.access_token) {
        if (!active) return;
        setSession(null);
        setError(null);
        setIsLoading(false);
        return;
      }
      void loadHosted();
    });

    return () => {
      active = false;
      subscription?.data.subscription.unsubscribe();
    };
  }, []);

  async function signInWithGoogle() {
    if (devHostedAuth) return;
    if (!supabase) return;
    const { error: authError } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    });
    if (authError) {
      throw authError;
    }
  }

  async function sendMagicLink(email: string) {
    if (devHostedAuth) return;
    if (!supabase) return;
    const { error: authError } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    if (authError) {
      throw authError;
    }
  }

  async function signInAsPersona(personaId: string, reset = false) {
    const result = await signInAsDevHostedPersona(personaId, reset);
    saveDevHostedSession(result.access_token, personaId);
    setLocalWorkspaceSession(null, null);
    setApiAccessToken(result.access_token);
    const bootstrap = await getHostedBootstrap();
    setSession(bootstrap);
    setError(null);
  }

  async function signInWithTestAccount(email: string, fullName: string, reset = false) {
    const result = await registerDevHostedAccount(email, fullName, reset);
    saveDevHostedSession(result.access_token, result.user.id);
    setLocalWorkspaceSession(null, null);
    setApiAccessToken(result.access_token);
    const bootstrap = await getHostedBootstrap();
    setSession(bootstrap);
    setError(null);
  }

  async function signOut() {
    setLocalWorkspaceSession(null, null);
    setApiAccessToken(null);
    setSession(null);
    if (devHostedAuth) {
      clearDevHostedSession();
      setError(null);
      return;
    }
    if (supabase) {
      await supabase.auth.signOut();
    }
  }

  async function refresh() {
    if (!hostedModeEnv) {
      const result = await requestLocalBootstrap();
      setLocalWorkspaceSession(result.session_token ?? null, result.csrf_token ?? null);
      setSession(result);
      return;
    }
    if (devHostedAuth) {
      const personaList = await getDevHostedPersonas();
      setPersonas(personaList);
      const stored = loadDevHostedSession();
      setLocalWorkspaceSession(null, null);
      setApiAccessToken(stored?.accessToken ?? null);
      if (!stored?.accessToken) {
        setSession(null);
        return;
      }
    }
    const result = await getHostedBootstrap();
    setSession(result);
  }

  const currentPersona = useMemo(
    () => (isHostedBootstrap(session) ? personas.find((persona) => persona.id === session.user.id) ?? null : null),
    [personas, session],
  );

  const value = useMemo<WorkspaceContextValue>(() => ({
    session,
    isLoading,
    error,
    hostedMode: hostedModeEnv || Boolean(session?.hosted_mode),
    authMode: hostedModeEnv ? (devHostedAuth ? 'hosted-dev' : 'hosted-supabase') : 'local',
    devHostedAuth,
    isAuthenticated: isHostedBootstrap(session),
    user: isHostedBootstrap(session) ? session.user : null,
    features: isHostedBootstrap(session) ? session.features : null,
    workspaceId: isHostedBootstrap(session) ? session.workspace.id : session?.workspace_id ?? null,
    personas,
    currentPersona,
    signInWithTestAccount,
    signInWithGoogle,
    sendMagicLink,
    signInAsPersona,
    signOut,
    refresh,
  }), [session, isLoading, error, personas, currentPersona]);

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
