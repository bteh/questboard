import { afterEach, describe, expect, it } from 'vitest';
import {
  ENTERED_KEY,
  entryRedirectTarget,
  erasePersonalBrowserState,
  hasEntered,
  markEntered,
} from './entry';

type MutableGlobal = Record<string, unknown>;

function stubStorage(initial: Record<string, string> = {}): Map<string, string> {
  const store = new Map(Object.entries(initial));
  (globalThis as MutableGlobal).window = {
    localStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, value);
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      key: (index: number) => Array.from(store.keys())[index] ?? null,
      get length() {
        return store.size;
      },
    },
  };
  return store;
}

function stubBrokenStorage(): void {
  (globalThis as MutableGlobal).window = {
    localStorage: {
      getItem: () => {
        throw new Error('storage refused');
      },
      setItem: () => {
        throw new Error('storage refused');
      },
    },
  };
}

afterEach(() => {
  delete (globalThis as MutableGlobal).window;
});

describe('the entered flag', () => {
  it('is off for a stranger', () => {
    stubStorage();
    expect(hasEntered()).toBe(false);
  });

  it('is on once the flag is stored', () => {
    stubStorage({ [ENTERED_KEY]: '1' });
    expect(hasEntered()).toBe(true);
  });

  it('markEntered writes the flag', () => {
    const store = stubStorage();
    markEntered();
    expect(store.get(ENTERED_KEY)).toBe('1');
    expect(hasEntered()).toBe(true);
  });

  it('survives a browser that refuses storage', () => {
    stubBrokenStorage();
    expect(hasEntered()).toBe(false);
    expect(() => markEntered()).not.toThrow();
  });

  it('survives a missing window entirely', () => {
    expect(hasEntered()).toBe(false);
    expect(() => markEntered()).not.toThrow();
  });
});

describe('the entry switch at /', () => {
  it('lets a stranger see the landing', () => {
    stubStorage();
    expect(entryRedirectTarget()).toBeNull();
  });

  it('sends a returner to the masthead home', () => {
    stubStorage({ [ENTERED_KEY]: '1' });
    expect(entryRedirectTarget()).toBe('/home');
  });
});

describe('privacy reset', () => {
  it('removes Questboard user state but preserves active sessions', () => {
    const store = stubStorage({
      'questboard:entered': '1',
      'questboard:board.v1': '{"place":"Los Angeles"}',
      'questboard-theme': 'dark',
      'qb-ai-fake': 'private state',
      'questboard-local-workspace-session:http://127.0.0.1:8765/api/v1': 'session',
      'questboard-dev-hosted-session': 'auth',
      'unrelated-app': 'keep',
    });

    erasePersonalBrowserState();

    expect(store.get('questboard:entered')).toBeUndefined();
    expect(store.get('questboard:board.v1')).toBeUndefined();
    expect(store.get('questboard-theme')).toBeUndefined();
    expect(store.get('qb-ai-fake')).toBeUndefined();
    expect(store.get('questboard-local-workspace-session:http://127.0.0.1:8765/api/v1')).toBe('session');
    expect(store.get('questboard-dev-hosted-session')).toBe('auth');
    expect(store.get('unrelated-app')).toBe('keep');
  });
});
