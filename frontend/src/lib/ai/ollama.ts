/**
 * Runtime-on-the-machine engine: Ollama on localhost:11434.
 *
 * Detection mirrors backend settings_service.detect_ollama: /api/version must
 * answer with a version AND /api/tags must list at least one model, because
 * port 11434 can be squatted by something that is not Ollama. When it answers,
 * this engine wins silently over the in-page one and there is no download
 * flow at all; the machine already holds a model.
 */

import type { Engine, EngineStatus } from './engine';

const BASE = 'http://localhost:11434';

async function fetchJson(url: string, timeoutMs: number): Promise<unknown> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctl.signal });
    if (!res.ok) return null;
    return (await res.json()) as unknown;
  } finally {
    clearTimeout(timer);
  }
}

export interface OllamaProbe {
  model: string;
}

export async function detectOllama(timeoutMs = 1500): Promise<OllamaProbe | null> {
  try {
    const version = (await fetchJson(`${BASE}/api/version`, timeoutMs)) as {
      version?: unknown;
    } | null;
    if (!version || typeof version.version !== 'string') return null;
    const tags = (await fetchJson(`${BASE}/api/tags`, timeoutMs)) as {
      models?: Array<{ name?: unknown }>;
    } | null;
    const names = (Array.isArray(tags?.models) ? tags.models : [])
      .map((m) => String(m?.name ?? ''))
      .filter(Boolean);
    if (!names.length) return null;
    const pick =
      names.find((n) => /qwen3/i.test(n)) ??
      names.find((n) => /qwen|llama|mistral|phi|gemma/i.test(n)) ??
      names[0];
    return { model: pick };
  } catch {
    return null;
  }
}

export class OllamaEngine implements Engine {
  private model: string;

  constructor(model: string) {
    this.model = model;
  }

  async status(): Promise<EngineStatus> {
    return { availability: 'ready' };
  }

  async download(): Promise<void> {
    /* nothing to fetch; the machine already runs it */
  }

  async remove(): Promise<void> {
    /* not ours to remove; we never installed anything */
  }

  async generate(prompt: string, onToken?: (token: string) => void): Promise<string> {
    const res = await fetch(`${BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: this.model,
        messages: [{ role: 'user', content: prompt }],
        stream: true,
      }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`ollama answered ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let text = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let nl: number;
      while ((nl = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, nl).trim();
        buffer = buffer.slice(nl + 1);
        if (!line) continue;
        const msg = JSON.parse(line) as { message?: { content?: string }; error?: string };
        if (msg.error) throw new Error(msg.error);
        const delta = msg.message?.content ?? '';
        if (delta) {
          text += delta;
          onToken?.(delta);
        }
      }
    }
    return text;
  }
}
