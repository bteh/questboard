/**
 * Entry point for the machinery behind "Explain this". It has no name in the
 * app; callers get an engine and a tier and never learn which implementation
 * answered.
 *
 * Pick order: the deterministic fake when VITE_AI_FAKE is set, a localhost
 * runtime when it answers (nothing to download), else the in-page engine.
 */

import type { Engine } from './engine';
import { FakeEngine } from './fake';
import { detectOllama, OllamaEngine } from './ollama';
import { decideTier, isHandheld, type Tier, type TierInputs } from './tier';
import { localKeyStore } from './storage';
import { downloads, NOT_NOW_KEY } from './consent';

export type { Engine, EngineStatus } from './engine';
export type { Tier } from './tier';
export {
  ExplainController,
  downloads,
  METHOD_FULL,
  METHOD_QUICK,
  NOT_NOW_KEY,
  type ConsentView,
  type ExplainViewState,
} from './consent';
export { quickRead } from './quick-read';
export { buildFullReadPrompt } from './prompt';

function isFake(): boolean {
  return Boolean(import.meta.env.VITE_AI_FAKE);
}

type EngineKind = 'fake' | 'ollama' | 'webllm';

let pickedPromise: Promise<{ engine: Engine; kind: EngineKind }> | null = null;

async function pick(): Promise<{ engine: Engine; kind: EngineKind }> {
  if (isFake()) return { engine: new FakeEngine(), kind: 'fake' };
  const ollama = await detectOllama();
  if (ollama) return { engine: new OllamaEngine(ollama.model), kind: 'ollama' };
  const { WebLlmEngine } = await import('./webllm');
  return { engine: new WebLlmEngine(), kind: 'webllm' };
}

export function getEngine(): Promise<Engine> {
  pickedPromise ??= pick();
  return pickedPromise.then((p) => p.engine);
}

async function gatherTierInputs(): Promise<TierInputs> {
  const nav = navigator as Navigator & {
    deviceMemory?: number;
    gpu?: { requestAdapter(): Promise<unknown | null> };
  };
  const userAgent = nav.userAgent ?? '';
  const coarsePointer =
    typeof window.matchMedia === 'function' && window.matchMedia('(pointer: coarse)').matches;
  const base: TierInputs = {
    userAgent,
    coarsePointer,
    hasWebGpu: false,
    adapter: false,
    deviceMemory: nav.deviceMemory,
    ollama: false,
    engineCached: false,
  };
  /* handhelds need no further probing, and must never see an offer */
  if (isHandheld(userAgent, coarsePointer)) return base;

  const picked = await pickedPromise!;
  base.ollama = picked.kind === 'ollama';
  if (base.ollama) return base;

  const gpu = nav.gpu;
  base.hasWebGpu = Boolean(gpu);
  if (gpu?.requestAdapter) {
    try {
      base.adapter = (await gpu.requestAdapter()) != null;
    } catch {
      base.adapter = false;
    }
  }
  if (base.adapter) {
    const status = await picked.engine.status();
    base.engineCached = status.availability === 'ready';
  }
  return base;
}

let tierPromise: Promise<Tier> | null = null;

/** The capability tier, probed once per page load (and after removal). */
export function currentTier(): Promise<Tier> {
  tierPromise ??= (async () => {
    const engine = await getEngine();
    if (isFake()) {
      const status = await engine.status();
      return status.availability === 'ready' ? 'ready' : 'capable';
    }
    return decideTier(await gatherTierInputs());
  })();
  return tierPromise;
}

/**
 * The engine whose stored weights the Settings row manages, or null when
 * there is nothing to manage on this machine (handheld or weak: silence;
 * localhost runtime: full reads already work and we installed nothing).
 */
export async function managedDownload(): Promise<Engine | null> {
  const picked = await (pickedPromise ??= pick());
  if (picked.kind === 'ollama') return null;
  if (picked.kind === 'fake') return picked.engine;
  const tier = await currentTier();
  return tier === 'quiet' ? null : picked.engine;
}

/** One-click removal; the flow will not re-ask, the Settings row is the way back. */
export async function removeDownload(engine: Engine): Promise<void> {
  await engine.remove();
  downloads.reset();
  localKeyStore.set(NOT_NOW_KEY, '1');
  tierPromise = null;
}

/* Dev-only smoke hook: proves the worker + in-page engine path executes on
   real WebGPU with the smallest prebuilt model. Never part of the app UI. */
if (import.meta.env.DEV && typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).__qbAiSmoke = async (modelId?: string) => {
    const { WebLlmEngine, WEBLLM_SMOKE_MODEL_ID } = await import('./webllm');
    const id = modelId || WEBLLM_SMOKE_MODEL_ID;
    const engine = new WebLlmEngine(id);
    let tokens = 0;
    const hook = window as unknown as Record<string, unknown>;
    await engine.download((pct) => {
      hook.__qbAiSmokePct = pct;
    });
    const text = await engine.generate('Reply with one short friendly sentence.', () => {
      tokens += 1;
    });
    return { model: id, tokens, text };
  };
}
