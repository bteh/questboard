/**
 * Capability tiers behind "Explain this". The check runs BEFORE any offer
 * ever renders, so a machine that cannot do the work never hears about it.
 *
 *   quiet:   phones, tablets, and weak machines. Quick reads only, and
 *            total silence about the fuller version.
 *   capable: the machine can do the work but has not downloaded it yet;
 *            the one place the consent card may appear.
 *   ready:   full reads run now (weights cached, or a local runtime answers).
 *
 * Decision table, in order:
 *   1. phone/tablet UA or coarse pointer            -> quiet
 *   2. runtime on localhost answers                 -> ready
 *   3. no WebGPU, or requestAdapter gave nothing    -> quiet
 *   4. deviceMemory stated and under 8              -> quiet
 *      (absent deviceMemory: the adapter alone decides)
 *   5. engine cached and loadable                   -> ready, else capable
 */

export type Tier = 'quiet' | 'capable' | 'ready';

export interface TierInputs {
  userAgent: string;
  coarsePointer: boolean;
  /** navigator.gpu exists */
  hasWebGpu: boolean;
  /** requestAdapter() resolved to a real adapter */
  adapter: boolean;
  /** navigator.deviceMemory, absent on most browsers */
  deviceMemory: number | undefined;
  /** localhost runtime answered the probe */
  ollama: boolean;
  /** the in-page engine's weights are stored and loadable */
  engineCached: boolean;
}

export const HANDHELD_UA = /iphone|ipad|ipod|android|mobile|tablet|silk|kindle/i;

export function isHandheld(userAgent: string, coarsePointer: boolean): boolean {
  return HANDHELD_UA.test(userAgent) || coarsePointer;
}

export function decideTier(i: TierInputs): Tier {
  if (isHandheld(i.userAgent, i.coarsePointer)) return 'quiet';
  if (i.ollama) return 'ready';
  if (!i.hasWebGpu || !i.adapter) return 'quiet';
  if (i.deviceMemory !== undefined && i.deviceMemory < 8) return 'quiet';
  return i.engineCached ? 'ready' : 'capable';
}
