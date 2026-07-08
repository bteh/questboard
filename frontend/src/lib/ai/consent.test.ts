/**
 * The consent-flow state machine, driven by the deterministic fake engine.
 * Pins the locked rules: answer before ask, not-now respected forever,
 * upgrade in place only when the full read is whole, quiet failure, and
 * removal reverting to quick reads.
 */

import { describe, expect, it } from 'vitest';
import {
  cleanRead,
  DownloadManager,
  ExplainController,
  METHOD_FULL,
  METHOD_QUICK,
  NOT_NOW_KEY,
} from './consent';
import { FakeEngine, FAKE_FAIL_KEY, FAKE_FULL_READ } from './fake';
import { memoryKeyStore } from './storage';
import type { Tier } from './tier';

const QUICK = 'Pays $19 an hour. Remote. From greenhouse.';
const PROMPT = 'Explain this posting in plain words.';

function setup(tier: Tier, opts: { store?: ReturnType<typeof memoryKeyStore>; prompt?: string | null } = {}) {
  const store = opts.store ?? memoryKeyStore();
  const engine = new FakeEngine(store, 0);
  const manager = new DownloadManager();
  const controller = new ExplainController(
    { quickBody: QUICK, fullPrompt: opts.prompt === undefined ? PROMPT : opts.prompt },
    engine,
    tier,
    store,
    manager,
  );
  return { controller, engine, manager, store };
}

describe('answer before ask', () => {
  it('the quick read is on screen synchronously, before any engine resolves', () => {
    const { controller } = setup('capable');
    const state = controller.getState();
    expect(state.body).toBe(QUICK);
    expect(state.method).toBe(METHOD_QUICK);
  });

  it('a capable machine gets the offer under the answer, never instead of it', async () => {
    const { controller } = setup('capable');
    await controller.settled();
    const state = controller.getState();
    expect(state.view).toBe('offer');
    expect(state.body).toBe(QUICK);
  });

  it('a quiet machine gets the answer and total silence', async () => {
    const { controller } = setup('quiet');
    await controller.idle();
    const state = controller.getState();
    expect(state.view).toBe('none');
    expect(state.body).toBe(QUICK);
    expect(state.method).toBe(METHOD_QUICK);
  });
});

describe('not now, respected forever', () => {
  it('declining stores the flag and shows the one-time settings pointer', async () => {
    const { controller, store } = setup('capable');
    await controller.settled();
    controller.notNow();
    expect(store.get(NOT_NOW_KEY)).toBe('1');
    expect(controller.getState().view).toBe('settings-note');
  });

  it('a later open on the same machine never re-asks', async () => {
    const store = memoryKeyStore();
    store.set(NOT_NOW_KEY, '1');
    const { controller } = setup('capable', { store });
    await controller.settled();
    expect(controller.getState().view).toBe('none');
  });
});

describe('download and upgrade in place', () => {
  it('progress climbs to done, then the block upgrades once, in place', async () => {
    const { controller } = setup('capable');
    await controller.settled();
    const seen: string[] = [];
    controller.subscribe(() => seen.push(controller.getState().view));
    await controller.startDownload();
    await controller.idle();
    const state = controller.getState();
    expect(seen).toContain('progress');
    expect(state.view).toBe('done');
    expect(state.body).toBe(FAKE_FULL_READ);
    expect(state.method).toBe(METHOD_FULL);
    expect(state.swap).toBe(1);
  });

  it('progress resumes from where a prior visit stopped', async () => {
    const store = memoryKeyStore();
    store.set('qb-ai-fake', '40');
    const engine = new FakeEngine(store, 0);
    const pcts: number[] = [];
    await engine.download((pct) => pcts.push(pct));
    expect(pcts[0]).toBeGreaterThan(40);
    expect(pcts[pcts.length - 1]).toBe(100);
  });

  it('a ready machine upgrades silently with no card at all', async () => {
    const { controller } = setup('ready');
    await controller.idle();
    const state = controller.getState();
    expect(state.view).toBe('none');
    expect(state.body).toBe(FAKE_FULL_READ);
    expect(state.method).toBe(METHOD_FULL);
  });

  it('a second controller during the download shows the same quiet progress', async () => {
    const store = memoryKeyStore();
    const engine = new FakeEngine(store, 0);
    const manager = new DownloadManager();
    const first = new ExplainController(
      { quickBody: QUICK, fullPrompt: PROMPT },
      engine,
      'capable',
      store,
      manager,
    );
    await first.settled();
    const run = first.startDownload();
    const second = new ExplainController(
      { quickBody: QUICK, fullPrompt: PROMPT },
      engine,
      'capable',
      store,
      manager,
    );
    await second.settled();
    expect(second.getState().view).toBe('progress');
    await run;
    await first.idle();
    await second.idle();
    expect(second.getState().view).toBe('done');
    expect(second.getState().body).toBe(FAKE_FULL_READ);
  });
});

describe('the request always completes', () => {
  it('an engine failure mid-generation quietly keeps the quick read', async () => {
    const store = memoryKeyStore();
    store.set(FAKE_FAIL_KEY, '1');
    const { controller } = setup('ready', { store });
    await controller.idle();
    const state = controller.getState();
    expect(state.body).toBe(QUICK);
    expect(state.method).toBe(METHOD_QUICK);
    expect(state.swap).toBe(0);
  });

  it('a record with nothing to read fully keeps the quick read on a ready machine', async () => {
    const { controller } = setup('ready', { prompt: null });
    await controller.idle();
    const state = controller.getState();
    expect(state.body).toBe(QUICK);
    expect(state.method).toBe(METHOD_QUICK);
  });
});

describe('removal', () => {
  it('remove clears the stored engine so the next open is quick-read only', async () => {
    const store = memoryKeyStore();
    const engine = new FakeEngine(store, 0);
    await engine.download();
    expect((await engine.status()).availability).toBe('ready');
    await engine.remove();
    expect((await engine.status()).availability).toBe('absent');
  });

  it('a fresh manager after reset holds no finished download', async () => {
    const store = memoryKeyStore();
    const engine = new FakeEngine(store, 0);
    const manager = new DownloadManager();
    await manager.start(engine);
    expect(manager.done).toBe(true);
    manager.reset();
    expect(manager.done).toBe(false);
    expect(manager.pct).toBe(0);
  });
});

describe('cleanRead', () => {
  it('strips thinking traces so a read is only its plain text', () => {
    expect(cleanRead('<think>hm, pay is unstated</think>They want a cook.')).toBe(
      'They want a cook.',
    );
    expect(cleanRead('They want a cook.')).toBe('They want a cook.');
  });

  it('an all-thinking answer becomes empty, which keeps the quick read', () => {
    expect(cleanRead('<think>never finished')).toBe('');
  });
});
