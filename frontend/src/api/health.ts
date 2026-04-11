export type SubsystemStatus = 'ok' | 'warn' | 'error';

export interface Subsystem {
  status: SubsystemStatus;
  summary: string;
  detail: string;
  fix_action: { kind: string; label: string; [key: string]: string } | null;
}

export interface SystemHealth {
  overall: SubsystemStatus;
  subsystems: {
    backend: Subsystem;
    ai: Subsystem;
    resume: Subsystem;
    search: Subsystem;
    keychain: Subsystem;
  };
}

/**
 * /api/health/system is mounted at the root of the backend (no /api/v1
 * prefix). Derive the root URL from VITE_API_URL so it works in both
 * web dev mode (/api/v1 proxy) and desktop mode (http://127.0.0.1:8765/api/v1).
 */
function healthUrl(): string {
  const apiUrl = import.meta.env.VITE_API_URL || '/api/v1';
  // Strip the trailing /v1 to get the /api root, then append /health/system
  const apiRoot = apiUrl.replace(/\/v1\/?$/, '');
  return `${apiRoot}/health/system`;
}

export async function getSystemHealth(): Promise<SystemHealth> {
  const resp = await fetch(healthUrl(), { credentials: 'include' });
  if (!resp.ok) {
    throw new Error(`Health check failed: ${resp.status}`);
  }
  return resp.json();
}
