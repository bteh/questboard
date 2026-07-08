/**
 * Deterministic engine for tests and VITE_AI_FAKE live walks.
 *
 * State persists through the injected store (localStorage in the browser),
 * so a route change mid-walk keeps the downloaded state. Setting the
 * FAKE_FAIL_KEY makes the next generate() die mid-stream, which is how the
 * keep-the-quick-read failure path gets exercised.
 */

import type { Engine, EngineStatus } from './engine';
import { localKeyStore, type KeyStore } from './storage';

const STATE_KEY = 'qb-ai-fake';
export const FAKE_FAIL_KEY = 'qb-ai-fake-fail';

export const FAKE_FULL_READ =
  'They want a steady hand who has shipped this kind of work before and can ' +
  'talk it through plainly. The one thing applicants likely miss: the posting ' +
  'asks twice for examples of past work, so a short specific sample up front ' +
  'counts as much as anything else you send.';

const sleep = (ms: number) =>
  ms > 0 ? new Promise<void>((r) => setTimeout(r, ms)) : Promise.resolve();

export class FakeEngine implements Engine {
  private store: KeyStore;
  private tickMs: number;

  constructor(store: KeyStore = localKeyStore, tickMs = 150) {
    this.store = store;
    this.tickMs = tickMs;
  }

  async status(): Promise<EngineStatus> {
    const v = this.store.get(STATE_KEY);
    if (v === 'ready') return { availability: 'ready' };
    const pct = Number(v);
    if (Number.isFinite(pct) && pct > 0) return { availability: 'partial', pct };
    return { availability: 'absent' };
  }

  async download(onProgress?: (pct: number) => void): Promise<void> {
    const from = await this.status();
    let pct = from.availability === 'partial' ? (from.pct ?? 0) : 0;
    while (pct < 100) {
      pct = Math.min(100, pct + 8);
      this.store.set(STATE_KEY, String(pct));
      onProgress?.(pct);
      await sleep(this.tickMs);
    }
    this.store.set(STATE_KEY, 'ready');
  }

  async generate(prompt: string, onToken?: (token: string) => void): Promise<string> {
    void prompt;
    if (this.store.get(FAKE_FAIL_KEY)) {
      this.store.del(FAKE_FAIL_KEY);
      onToken?.('They want');
      throw new Error('fake engine failure mid-generation');
    }
    let text = '';
    for (const word of FAKE_FULL_READ.split(' ')) {
      const token = (text ? ' ' : '') + word;
      text += token;
      onToken?.(token);
      await sleep(Math.min(this.tickMs, 15));
    }
    return text;
  }

  async remove(): Promise<void> {
    this.store.del(STATE_KEY);
  }
}
