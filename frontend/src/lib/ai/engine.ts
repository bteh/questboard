/**
 * The injectable engine interface behind "Explain this".
 *
 * Three implementations: webllm.ts (in-page worker, downloads weights once),
 * ollama.ts (a runtime already on the machine, nothing to download), and
 * fake.ts (deterministic, for tests and VITE_AI_FAKE walks). Callers never
 * know which one they hold.
 */

export type EngineAvailability = 'absent' | 'partial' | 'ready';

export interface EngineStatus {
  availability: EngineAvailability;
  /** Last known download progress, 0..100, when availability is 'partial'. */
  pct?: number;
}

export interface Engine {
  /** Stream a completion; onToken gets each delta. Resolves with the full text. */
  generate(prompt: string, onToken?: (token: string) => void): Promise<string>;
  status(): Promise<EngineStatus>;
  /** Fetch and prepare everything; resolves once generation can run. */
  download(onProgress?: (pct: number) => void): Promise<void>;
  /** Delete whatever the engine stored on this machine. */
  remove(): Promise<void>;
}
