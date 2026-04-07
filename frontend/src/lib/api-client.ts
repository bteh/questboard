const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';
let accessToken: string | null = null;
let localWorkspaceSessionToken: string | null = null;
let localWorkspaceCsrfToken: string | null = null;
const DESKTOP_LOCAL_API_PATTERN = /^https?:\/\/(127\.0\.0\.1|localhost):8765\/api\/v1$/;
const LOCAL_WORKSPACE_STORAGE_KEY = `launchboard-local-workspace-session:${BASE_URL}`;

function shouldPersistLocalWorkspaceSession(): boolean {
  return DESKTOP_LOCAL_API_PATTERN.test(BASE_URL);
}

function restoreLocalWorkspaceSession(): void {
  if (!shouldPersistLocalWorkspaceSession() || typeof window === 'undefined') return;
  try {
    const raw = window.localStorage.getItem(LOCAL_WORKSPACE_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as { sessionToken?: unknown; csrfToken?: unknown };
    if (typeof parsed.sessionToken === 'string' && parsed.sessionToken.trim()) {
      localWorkspaceSessionToken = parsed.sessionToken;
      localWorkspaceCsrfToken = typeof parsed.csrfToken === 'string' ? parsed.csrfToken : null;
    }
  } catch {
    // Ignore corrupted local desktop session state.
  }
}

function persistLocalWorkspaceSession(): void {
  if (!shouldPersistLocalWorkspaceSession() || typeof window === 'undefined') return;
  try {
    if (localWorkspaceSessionToken) {
      window.localStorage.setItem(
        LOCAL_WORKSPACE_STORAGE_KEY,
        JSON.stringify({
          sessionToken: localWorkspaceSessionToken,
          csrfToken: localWorkspaceCsrfToken,
        }),
      );
      return;
    }
    window.localStorage.removeItem(LOCAL_WORKSPACE_STORAGE_KEY);
  } catch {
    // localStorage unavailable — in-memory session still works.
  }
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function parseErrorMessage(body: string, fallback: string): string {
  if (!body) return fallback;
  try {
    const parsed = JSON.parse(body);
    if (typeof parsed === 'string' && parsed.trim()) return parsed.trim();
    if (parsed && typeof parsed === 'object') {
      const detail = (parsed as Record<string, unknown>).detail;
      if (typeof detail === 'string' && detail.trim()) return detail.trim();
      if (Array.isArray(detail)) {
        const joined = detail
          .map((item) => {
            if (typeof item === 'string') return item;
            if (item && typeof item === 'object' && 'msg' in item && typeof item.msg === 'string') return item.msg;
            return '';
          })
          .filter(Boolean)
          .join('; ');
        if (joined) return joined;
      }
      const message = (parsed as Record<string, unknown>).message;
      if (typeof message === 'string' && message.trim()) return message.trim();
      const error = (parsed as Record<string, unknown>).error;
      if (typeof error === 'string' && error.trim()) return error.trim();
    }
  } catch {
    // Fall back to plain text below.
  }
  return body.trim() || fallback;
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, parseErrorMessage(body, response.statusText));
  }
  return response.json() as Promise<T>;
}

function getCsrfToken(): string {
  if (localWorkspaceCsrfToken) return localWorkspaceCsrfToken;
  if (typeof document === 'undefined') return '';
  const match = document.cookie.match(/(?:^|;\s*)lb_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : '';
}

function authHeaders(): Record<string, string> {
  if (accessToken) {
    return { Authorization: `Bearer ${accessToken}` };
  }
  if (localWorkspaceSessionToken) {
    return { 'X-Launchboard-Session': localWorkspaceSessionToken };
  }
  return {};
}

function requestCredentials(): RequestCredentials {
  return accessToken || localWorkspaceSessionToken ? 'omit' : 'include';
}

function jsonHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...authHeaders(),
  };
  const csrf = getCsrfToken();
  if (csrf && !accessToken) headers['X-CSRF-Token'] = csrf;
  return headers;
}

function uploadHeaders(): Record<string, string> {
  const headers: Record<string, string> = { ...authHeaders() };
  const csrf = getCsrfToken();
  if (csrf && !accessToken) headers['X-CSRF-Token'] = csrf;
  return headers;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  let url = `${BASE_URL}${path}`;
  if (params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        searchParams.set(key, String(value));
      }
    });
    const qs = searchParams.toString();
    if (qs) url += `?${qs}`;
  }
  const response = await fetch(url, {
    credentials: requestCredentials(),
    headers: authHeaders(),
  });
  return handleResponse<T>(response);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    credentials: requestCredentials(),
    headers: jsonHeaders(),
    body: body ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(response);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    credentials: requestCredentials(),
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<T>(response);
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    credentials: requestCredentials(),
    headers: jsonHeaders(),
    body: JSON.stringify(body),
  });
  return handleResponse<T>(response);
}

export async function apiDelete<T = void>(path: string): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    credentials: requestCredentials(),
    headers: uploadHeaders(),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ApiError(response.status, parseErrorMessage(body, response.statusText));
  }
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    credentials: requestCredentials(),
    headers: uploadHeaders(),
    body: formData,
  });
  return handleResponse<T>(response);
}

export function sseUrl(path: string): string {
  return `${BASE_URL}${path}`;
}

export function setApiAccessToken(token: string | null) {
  accessToken = token;
  if (token) {
    localWorkspaceSessionToken = null;
    localWorkspaceCsrfToken = null;
    persistLocalWorkspaceSession();
  }
}

export function getApiAccessToken(): string | null {
  return accessToken;
}

export function setLocalWorkspaceSession(sessionToken: string | null, csrfToken: string | null) {
  localWorkspaceSessionToken = sessionToken;
  localWorkspaceCsrfToken = csrfToken;
  if (sessionToken) {
    accessToken = null;
  }
  persistLocalWorkspaceSession();
}

restoreLocalWorkspaceSession();

export async function streamSse(
  path: string,
  handlers: {
    onEvent: (event: string, data: string) => void;
    onClose?: () => void;
  },
  signal?: AbortSignal,
) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: 'GET',
    credentials: requestCredentials(),
    headers: {
      Accept: 'text/event-stream',
      ...authHeaders(),
    },
    signal,
  });

  if (!response.ok || !response.body) {
    const body = await response.text();
    throw new ApiError(response.status, parseErrorMessage(body, response.statusText));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';
  let currentData: string[] = [];

  const flush = () => {
    if (currentData.length === 0) return;
    handlers.onEvent(currentEvent, currentData.join('\n'));
    currentEvent = 'message';
    currentData = [];
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      flush();
      handlers.onClose?.();
      return;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line) {
        flush();
        continue;
      }
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim() || 'message';
        continue;
      }
      if (line.startsWith('data:')) {
        currentData.push(line.slice(5).trimStart());
      }
    }
  }
}

export { ApiError };
