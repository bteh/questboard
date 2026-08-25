/* The fetch layer's network failures must reach the user as plain
   sentences, not WKWebView's raw "Load failed". A thrown fetch becomes a
   NetworkError whose message names the real situation (offline vs the
   local service not answering), aborts pass through untouched, and HTTP
   errors keep the ApiError shape callers already branch on. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type ApiClient = typeof import('./api-client');

async function freshClient(): Promise<ApiClient> {
  vi.resetModules();
  return import('./api-client');
}

function stubFetchReject(error: unknown) {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(error));
}

beforeEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe('network failures in the api client', () => {
  it('says you are offline when the browser knows it is offline', async () => {
    stubFetchReject(new TypeError('Load failed'));
    vi.stubGlobal('navigator', { onLine: false });
    const api = await freshClient();

    await expect(api.apiGet('/board')).rejects.toMatchObject({
      name: 'NetworkError',
      message:
        "You're offline. Questboard needs the internet to check sources; your board still works.",
    });
  });

  it('blames the unreachable server, not the network, when online on the web', async () => {
    stubFetchReject(new TypeError('Load failed'));
    vi.stubGlobal('navigator', { onLine: true });
    const api = await freshClient();

    await expect(api.apiGet('/board')).rejects.toMatchObject({
      name: 'NetworkError',
      message: 'Questboard could not reach the server. Check your connection and try again.',
    });
  });

  it('names the background service in the desktop app', async () => {
    vi.stubEnv('VITE_API_URL', 'http://127.0.0.1:8765/api/v1');
    stubFetchReject(new TypeError('Load failed'));
    vi.stubGlobal('navigator', { onLine: true });
    const api = await freshClient();

    await expect(api.apiGet('/board')).rejects.toMatchObject({
      name: 'NetworkError',
      message:
        'Questboard could not reach its background service. Quit and reopen the app if this keeps happening.',
    });
  });

  it('wraps every write verb the same way', async () => {
    stubFetchReject(new TypeError('Load failed'));
    vi.stubGlobal('navigator', { onLine: false });
    const api = await freshClient();

    for (const call of [
      () => api.apiPost('/x'),
      () => api.apiPut('/x', {}),
      () => api.apiPatch('/x', {}),
      () => api.apiDelete('/x'),
      () => api.apiUpload('/x', new FormData()),
      () => api.apiGetBlob('/x'),
    ]) {
      await expect(call()).rejects.toMatchObject({ name: 'NetworkError' });
    }
  });

  it('is not an ApiError, so status-code branches never fire on it', async () => {
    stubFetchReject(new TypeError('Load failed'));
    vi.stubGlobal('navigator', { onLine: false });
    const api = await freshClient();

    const error = await api.apiGet('/board').catch((err: unknown) => err);
    expect(error).toBeInstanceOf(Error);
    expect(error).not.toBeInstanceOf(api.ApiError);
  });

  it('lets an abort through untouched', async () => {
    stubFetchReject(new DOMException('The user aborted a request.', 'AbortError'));
    vi.stubGlobal('navigator', { onLine: false });
    const api = await freshClient();

    await expect(api.apiGet('/board')).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('keeps HTTP errors as ApiError with status and parsed detail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'bad request' }), { status: 400 }),
      ),
    );
    const api = await freshClient();

    const error = await api.apiGet('/board').catch((err: unknown) => err);
    expect(error).toBeInstanceOf(api.ApiError);
    expect((error as InstanceType<ApiClient['ApiError']>).status).toBe(400);
    expect((error as Error).message).toBe('bad request');
  });
});
