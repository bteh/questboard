/**
 * The consent flow behind "Explain this", as a framework-free state machine.
 *
 * The locked rules it enforces:
 * - ANSWER BEFORE ASK: the quick read is set synchronously in the
 *   constructor; every later state only ever adds to or upgrades it.
 * - One block that upgrades in place: the full read is buffered and swapped
 *   in only when generation completes, so a mid-generation failure quietly
 *   leaves the quick read and its method line untouched.
 * - "Not now" is respected forever: one flag, never re-asked; the Settings
 *   row is the only way back.
 * - The download keeps going when the sheet closes and across cards; a
 *   second open mid-download shows the same quiet progress line.
 */

import type { Engine } from './engine';
import type { Tier } from './tier';
import { localKeyStore, type KeyStore } from './storage';

export const NOT_NOW_KEY = 'qb-ai-notnow';

export const METHOD_QUICK = "Pulled from the posting's own words.";
export const METHOD_FULL = 'Read from the whole posting.';

export type ConsentView =
  /** nothing under the answer: quiet tier, declined, or full reads just work */
  | 'none'
  /** the first-time card, under an already-delivered answer */
  | 'offer'
  /** the unobtrusive progress line */
  | 'progress'
  /** the one-time completion note */
  | 'done'
  /** the one-time quiet pointer shown right after "Not now" */
  | 'settings-note';

export interface ExplainViewState {
  body: string;
  method: string;
  view: ConsentView;
  pct: number;
  /** bumps when the block upgrades in place, to retrigger the swap animation */
  swap: number;
}

/** Strip thinking traces some models emit; a read is only its plain text. */
export function cleanRead(text: string): string {
  return text
    .replace(/<think>[\s\S]*?<\/think>/g, '')
    .replace(/^\s*<think>[\s\S]*$/g, '')
    .trim();
}

type Listener = () => void;

/**
 * One download for the whole app. Progress is monotonic so the line never
 * runs backwards when the engine reports a second loading phase.
 */
export class DownloadManager {
  running = false;
  done = false;
  failed = false;
  pct = 0;
  private listeners = new Set<Listener>();
  private promise: Promise<void> | null = null;

  start(engine: Engine): Promise<void> {
    if (this.done) return Promise.resolve();
    if (this.running && this.promise) return this.promise;
    this.running = true;
    this.failed = false;
    this.promise = engine
      .download((pct) => {
        this.pct = Math.max(this.pct, pct);
        this.emit();
      })
      .then(() => {
        this.done = true;
        this.pct = 100;
      })
      .catch(() => {
        this.failed = true;
      })
      .then(() => {
        this.running = false;
        this.emit();
      });
    this.emit();
    return this.promise;
  }

  /** Resolves when the current download settles; immediately when none runs. */
  settled(): Promise<void> {
    return this.promise ?? Promise.resolve();
  }

  reset(): void {
    this.running = false;
    this.done = false;
    this.failed = false;
    this.pct = 0;
    this.promise = null;
    this.emit();
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    for (const l of this.listeners) l();
  }
}

/** The app-wide download, shared by the sheet and the Settings row. */
export const downloads = new DownloadManager();

export interface ExplainInputs {
  quickBody: string;
  /** null when there is nothing to read fully; the quick read stands */
  fullPrompt: string | null;
}

export class ExplainController {
  private state: ExplainViewState;
  private listeners = new Set<Listener>();
  private unsubscribe: (() => void) | null = null;
  private fullStarted = false;
  private settledPromise: Promise<void> | null = null;
  private inputs: ExplainInputs;
  private engine: Engine | Promise<Engine>;
  private tier: Tier | Promise<Tier>;
  private store: KeyStore;
  private manager: DownloadManager;

  constructor(
    inputs: ExplainInputs,
    engine: Engine | Promise<Engine>,
    tier: Tier | Promise<Tier>,
    store: KeyStore = localKeyStore,
    manager: DownloadManager = downloads,
  ) {
    this.inputs = inputs;
    this.engine = engine;
    this.tier = tier;
    this.store = store;
    this.manager = manager;
    /* the answer, before anything else exists; construction is side-effect
       free so React may build a controller during render */
    this.state = {
      body: inputs.quickBody,
      method: METHOD_QUICK,
      view: 'none',
      pct: 0,
      swap: 0,
    };
  }

  /** Kick off the tier decision; idempotent. */
  start(): Promise<void> {
    this.settledPromise ??= Promise.all([this.engine, this.tier]).then(([e, t]) =>
      this.decide(e, t),
    );
    return this.settledPromise;
  }

  getState(): ExplainViewState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  /** Resolves once the initial decision (and any full read it ran) settles. */
  settled(): Promise<void> {
    return this.start();
  }

  /** Test helper: resolves when everything in flight has landed. */
  async idle(): Promise<void> {
    await this.start();
    await this.manager.settled();
    await this.lastFullRead;
  }

  private lastFullRead: Promise<void> | null = null;

  private engineRef: Engine | null = null;

  private async decide(engine: Engine, tier: Tier): Promise<void> {
    this.engineRef = engine;
    if (tier === 'quiet') return;

    if (this.manager.running) {
      this.watchDownload(engine);
      return;
    }
    if (tier === 'ready' || this.manager.done) {
      await this.runFullRead(engine);
      return;
    }
    /* capable */
    if (this.store.get(NOT_NOW_KEY)) return;
    this.patch({ view: 'offer' });
  }

  /** "Not now", respected forever. */
  notNow(): void {
    this.store.set(NOT_NOW_KEY, '1');
    this.patch({ view: 'settings-note' });
  }

  startDownload(): Promise<void> {
    const engine = this.engineRef;
    if (!engine) return Promise.resolve();
    const run = this.manager.start(engine);
    this.watchDownload(engine);
    return run;
  }

  private watchDownload(engine: Engine): void {
    this.patch({ view: 'progress', pct: this.manager.pct });
    this.unsubscribe?.();
    this.unsubscribe = this.manager.subscribe(() => {
      if (this.manager.done) {
        this.unsubscribe?.();
        this.unsubscribe = null;
        this.patch({ view: 'done', pct: 100 });
        this.lastFullRead = this.runFullRead(engine);
      } else if (this.manager.failed) {
        /* the answer already on screen stands; nothing to announce */
        this.unsubscribe?.();
        this.unsubscribe = null;
        this.patch({ view: 'none' });
      } else {
        this.patch({ pct: this.manager.pct });
      }
    });
  }

  /**
   * Buffered, not streamed to the screen: the block swaps once, when the
   * fuller text is whole. Any failure leaves the quick read untouched.
   */
  private async runFullRead(engine: Engine): Promise<void> {
    if (this.fullStarted || !this.inputs.fullPrompt) return;
    this.fullStarted = true;
    try {
      const raw = await engine.generate(this.inputs.fullPrompt);
      const text = cleanRead(raw);
      if (!text) return;
      this.patch({ body: text, method: METHOD_FULL, swap: this.state.swap + 1 });
    } catch {
      /* the request always completes: quick read and method line stand */
    }
  }

  dispose(): void {
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.listeners.clear();
  }

  private patch(next: Partial<ExplainViewState>): void {
    this.state = { ...this.state, ...next };
    for (const l of this.listeners) l();
  }
}
