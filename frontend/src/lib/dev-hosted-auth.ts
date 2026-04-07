const DEV_HOSTED_AUTH_STORAGE_KEY = 'launchboard-dev-hosted-session';

export const devHostedAuth = import.meta.env.VITE_DEV_HOSTED_AUTH === 'true';

interface StoredDevHostedSession {
  accessToken: string;
  personaId: string;
}

export function loadDevHostedSession(): StoredDevHostedSession | null {
  if (typeof window === 'undefined') return null;
  const raw = window.localStorage.getItem(DEV_HOSTED_AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as StoredDevHostedSession;
    if (!parsed.accessToken || !parsed.personaId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveDevHostedSession(accessToken: string, personaId: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(
    DEV_HOSTED_AUTH_STORAGE_KEY,
    JSON.stringify({ accessToken, personaId }),
  );
}

export function clearDevHostedSession() {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(DEV_HOSTED_AUTH_STORAGE_KEY);
}
