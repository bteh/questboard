/**
 * The tier decision table, pinned. The one rule that matters most: phones
 * and weak machines land in 'quiet' before anything else is even probed,
 * so no offer can ever render there.
 */

import { describe, expect, it } from 'vitest';
import { decideTier, type TierInputs } from './tier';

const DESKTOP_UA =
  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const IPHONE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';
const ANDROID_UA =
  'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Mobile Safari/537.36';
const IPAD_UA =
  'Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1';

function inputs(overrides: Partial<TierInputs>): TierInputs {
  return {
    userAgent: DESKTOP_UA,
    coarsePointer: false,
    hasWebGpu: true,
    adapter: true,
    deviceMemory: undefined,
    ollama: false,
    engineCached: false,
    ...overrides,
  };
}

describe('decideTier', () => {
  it('phone UA is quiet, even with a capable adapter', () => {
    expect(decideTier(inputs({ userAgent: IPHONE_UA }))).toBe('quiet');
    expect(decideTier(inputs({ userAgent: ANDROID_UA }))).toBe('quiet');
    expect(decideTier(inputs({ userAgent: IPAD_UA }))).toBe('quiet');
  });

  it('coarse pointer is quiet, even with a capable adapter', () => {
    expect(decideTier(inputs({ coarsePointer: true }))).toBe('quiet');
  });

  it('a phone stays quiet even when a localhost runtime answers', () => {
    expect(decideTier(inputs({ userAgent: IPHONE_UA, ollama: true }))).toBe('quiet');
  });

  it('a localhost runtime makes a desktop ready with no download flow', () => {
    expect(decideTier(inputs({ ollama: true, hasWebGpu: false, adapter: false }))).toBe('ready');
  });

  it('no WebGPU at all is quiet', () => {
    expect(decideTier(inputs({ hasWebGpu: false, adapter: false }))).toBe('quiet');
  });

  it('WebGPU present but no adapter is quiet', () => {
    expect(decideTier(inputs({ adapter: false }))).toBe('quiet');
  });

  it('deviceMemory under 8 is quiet even with an adapter', () => {
    expect(decideTier(inputs({ deviceMemory: 4 }))).toBe('quiet');
  });

  it('deviceMemory of 8 or more with an adapter is capable', () => {
    expect(decideTier(inputs({ deviceMemory: 8 }))).toBe('capable');
    expect(decideTier(inputs({ deviceMemory: 16 }))).toBe('capable');
  });

  it('absent deviceMemory lets the adapter alone decide', () => {
    expect(decideTier(inputs({ deviceMemory: undefined }))).toBe('capable');
  });

  it('a cached loadable engine is ready', () => {
    expect(decideTier(inputs({ engineCached: true }))).toBe('ready');
  });

  it('a cached engine on a phone is still quiet', () => {
    expect(decideTier(inputs({ userAgent: IPHONE_UA, engineCached: true }))).toBe('quiet');
  });
});
