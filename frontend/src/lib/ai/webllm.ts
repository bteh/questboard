/**
 * In-page engine: MLC WebLLM running in a Web Worker.
 *
 * Model: Qwen3-1.7B q4f16 (Apache-2.0). Weights land in Cache API storage,
 * so a second visit never downloads again and an interrupted download picks
 * up at the shards it already has. We ask for persistent storage before the
 * first byte so the browser does not evict the weights under pressure.
 */

import {
  CreateWebWorkerMLCEngine,
  deleteModelAllInfoInCache,
  hasModelInCache,
  type MLCEngineInterface,
} from '@mlc-ai/web-llm';
import type { Engine, EngineStatus } from './engine';
import { localKeyStore, type KeyStore } from './storage';

export const WEBLLM_MODEL_ID = 'Qwen3-1.7B-q4f16_1-MLC';

/** Smallest chat model in the prebuilt list; used only by the dev smoke hook. */
export const WEBLLM_SMOKE_MODEL_ID = 'SmolLM2-135M-Instruct-q0f16-MLC';

const pctKey = (modelId: string) => `qb-ai-fetch-pct:${modelId}`;

export class WebLlmEngine implements Engine {
  private engine: MLCEngineInterface | null = null;
  private loading: Promise<MLCEngineInterface> | null = null;
  private modelId: string;
  private store: KeyStore;

  constructor(modelId: string = WEBLLM_MODEL_ID, store: KeyStore = localKeyStore) {
    this.modelId = modelId;
    this.store = store;
  }

  private load(onProgress?: (pct: number) => void): Promise<MLCEngineInterface> {
    if (this.engine) return Promise.resolve(this.engine);
    if (!this.loading) {
      this.loading = (async () => {
        try {
          await navigator.storage?.persist?.();
        } catch {
          /* best effort; eviction just means a re-download later */
        }
        const worker = new Worker(new URL('./webllm.worker.ts', import.meta.url), {
          type: 'module',
        });
        const engine = await CreateWebWorkerMLCEngine(worker, this.modelId, {
          initProgressCallback: (report) => {
            const pct = Math.max(0, Math.min(100, Math.round(report.progress * 100)));
            this.store.set(pctKey(this.modelId), String(pct));
            onProgress?.(pct);
          },
        });
        this.engine = engine;
        return engine;
      })();
      this.loading.catch(() => {
        this.loading = null;
      });
    }
    return this.loading;
  }

  async generate(prompt: string, onToken?: (token: string) => void): Promise<string> {
    const engine = await this.load();
    const stream = await engine.chat.completions.create({
      messages: [{ role: 'user', content: prompt }],
      stream: true,
      max_tokens: 220,
      extra_body: { enable_thinking: false },
    });
    let text = '';
    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content ?? '';
      if (delta) {
        text += delta;
        onToken?.(delta);
      }
    }
    return text;
  }

  async status(): Promise<EngineStatus> {
    if (this.engine) return { availability: 'ready' };
    let cached = false;
    try {
      cached = await hasModelInCache(this.modelId);
    } catch {
      cached = false;
    }
    if (cached) return { availability: 'ready' };
    const pct = Number(this.store.get(pctKey(this.modelId)));
    if (Number.isFinite(pct) && pct > 0 && pct < 100) {
      return { availability: 'partial', pct };
    }
    return { availability: 'absent' };
  }

  async download(onProgress?: (pct: number) => void): Promise<void> {
    await this.load(onProgress);
  }

  async remove(): Promise<void> {
    try {
      await this.engine?.unload();
    } catch {
      /* an engine that will not unload still gets its cache deleted */
    }
    this.engine = null;
    this.loading = null;
    await deleteModelAllInfoInCache(this.modelId);
    this.store.del(pctKey(this.modelId));
  }
}
