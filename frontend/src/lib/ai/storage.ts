/** Tiny key-value seam so the consent flow and fake engine test in node. */

export interface KeyStore {
  get(key: string): string | null;
  set(key: string, value: string): void;
  del(key: string): void;
}

/** localStorage-backed, silent when storage is unavailable (private mode). */
export const localKeyStore: KeyStore = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* nothing to do; the flow degrades to session-only memory */
    }
  },
  del(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* same */
    }
  },
};

/** In-memory store for tests. */
export function memoryKeyStore(): KeyStore {
  const map = new Map<string, string>();
  return {
    get: (k) => map.get(k) ?? null,
    set: (k, v) => void map.set(k, v),
    del: (k) => void map.delete(k),
  };
}
