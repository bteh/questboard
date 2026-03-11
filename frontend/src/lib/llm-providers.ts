/** LLM provider definitions — model options and provider groups.
 *
 * This file is the single source of truth for all provider/model metadata.
 * To add a new provider: add entries to the models array and PROVIDER_GROUPS.
 *
 * Internal/proxy groups are only shown when dev mode is enabled:
 *   localStorage.setItem('launchboard-dev-mode', 'true')
 */

export interface ModelOption {
  id: string;       // sent to the API
  name: string;     // friendly display name
  tag?: string;     // optional tag like "recommended"
}

export interface ProviderGroup {
  id: string;
  label: string;
  description: string;
  badge: 'free' | 'local' | 'api-key' | 'internal';
  badgeLabel: string;
  presetNames: string[]; // backend preset names that map to this group
  models: ModelOption[];
  apiKeyPlaceholder?: string; // hint for the API key input
  internal?: boolean;    // hidden unless dev mode is on
}

// ── Model lists ──

const GEMINI_MODELS: ModelOption[] = [
  { id: 'gemini-2.5-flash', name: '2.5 Flash', tag: 'recommended' },
  { id: 'gemini-2.5-flash-lite', name: '2.5 Flash Lite', tag: 'highest free limit' },
  { id: 'gemini-2.5-pro', name: '2.5 Pro' },
];

const GROQ_MODELS: ModelOption[] = [
  { id: 'meta-llama/llama-4-maverick-17b-128e-instruct', name: 'Llama 4 Maverick', tag: 'recommended' },
  { id: 'meta-llama/llama-4-scout-17b-16e-instruct', name: 'Llama 4 Scout' },
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B' },
  { id: 'qwen/qwen3-32b', name: 'Qwen 3 32B' },
  { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B', tag: 'fast' },
  { id: 'deepseek-r1-distill-llama-70b', name: 'DeepSeek R1 Distill 70B' },
];

const OPENROUTER_MODELS: ModelOption[] = [
  { id: 'meta-llama/llama-4-maverick:free', name: 'Llama 4 Maverick', tag: 'recommended' },
  { id: 'meta-llama/llama-4-scout:free', name: 'Llama 4 Scout' },
  { id: 'meta-llama/llama-3.3-70b-instruct:free', name: 'Llama 3.3 70B' },
  { id: 'deepseek/deepseek-chat-v3-0324:free', name: 'DeepSeek V3' },
  { id: 'deepseek/deepseek-r1:free', name: 'DeepSeek R1' },
  { id: 'qwen/qwen3-235b-a22b:free', name: 'Qwen 3 235B' },
  { id: 'mistralai/mistral-small-3.1-24b-instruct:free', name: 'Mistral Small 3.1' },
  { id: 'openrouter/auto', name: 'Auto (best available)' },
];

const CEREBRAS_MODELS: ModelOption[] = [
  { id: 'llama-4-scout-17b-16e', name: 'Llama 4 Scout', tag: 'recommended' },
  { id: 'llama3.3-70b', name: 'Llama 3.3 70B' },
  { id: 'qwen-3-235b-a22b-instruct', name: 'Qwen 3 235B' },
  { id: 'qwen3-32b', name: 'Qwen 3 32B' },
];

const SAMBANOVA_MODELS: ModelOption[] = [
  { id: 'Meta-Llama-3.3-70B-Instruct', name: 'Llama 3.3 70B', tag: 'recommended' },
  { id: 'Meta-Llama-3.1-405B-Instruct', name: 'Llama 3.1 405B' },
  { id: 'Meta-Llama-3.1-8B-Instruct', name: 'Llama 3.1 8B', tag: 'fast' },
];

const CLAUDE_MODELS: ModelOption[] = [
  { id: 'claude-sonnet-4-6', name: 'Sonnet 4.6', tag: 'recommended' },
  { id: 'claude-opus-4-6', name: 'Opus 4.6' },
  { id: 'claude-haiku-4-5-20251001', name: 'Haiku 4.5', tag: 'fast' },
  { id: 'claude-sonnet-4-20250514', name: 'Sonnet 4' },
];

const OPENAI_MODELS: ModelOption[] = [
  { id: 'gpt-5.4', name: 'GPT-5.4', tag: 'recommended' },
  { id: 'gpt-5-mini', name: 'GPT-5 Mini' },
  { id: 'gpt-4.1', name: 'GPT-4.1' },
  { id: 'gpt-4.1-mini', name: 'GPT-4.1 Mini' },
  { id: 'gpt-4o', name: 'GPT-4o' },
  { id: 'o3', name: 'o3' },
  { id: 'o3-pro', name: 'o3 Pro' },
  { id: 'o4-mini', name: 'o4 Mini' },
];

const MISTRAL_MODELS: ModelOption[] = [
  { id: 'mistral-small-latest', name: 'Mistral Small 3.1', tag: 'recommended' },
  { id: 'mistral-medium-latest', name: 'Mistral Medium 3' },
  { id: 'mistral-large-latest', name: 'Mistral Large 3' },
  { id: 'open-mistral-nemo', name: 'Mistral Nemo' },
];

const DEEPSEEK_MODELS: ModelOption[] = [
  { id: 'deepseek-chat', name: 'DeepSeek V3.2', tag: 'recommended' },
  { id: 'deepseek-reasoner', name: 'DeepSeek R1' },
];

const OLLAMA_MODELS: ModelOption[] = [
  { id: 'llama4', name: 'Llama 4' },
  { id: 'llama3.3', name: 'Llama 3.3' },
  { id: 'qwen3', name: 'Qwen 3' },
  { id: 'gemma3', name: 'Gemma 3' },
  { id: 'mistral', name: 'Mistral' },
  { id: 'deepseek-r1', name: 'DeepSeek R1' },
  { id: 'phi4', name: 'Phi-4' },
];

// ── Provider groups ──

export const PROVIDER_GROUPS: ProviderGroup[] = [
  // ── Free cloud (recommended) ──
  {
    id: 'gemini',
    label: 'Google Gemini',
    description: 'Free tier — 250 req/day (Flash), up to 1,000/day (Flash Lite). No credit card needed.',
    badge: 'free',
    badgeLabel: 'Free tier',
    presetNames: ['gemini'],
    models: GEMINI_MODELS,
    apiKeyPlaceholder: 'AIza...',
  },
  {
    id: 'groq',
    label: 'Groq',
    description: 'Blazing fast inference — 1,000 req/day free. Llama 4, Qwen 3, and more.',
    badge: 'free',
    badgeLabel: 'Free tier',
    presetNames: ['groq'],
    models: GROQ_MODELS,
    apiKeyPlaceholder: 'gsk_...',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    description: '27+ free models — 200 req/day. Routes across multiple providers automatically.',
    badge: 'free',
    badgeLabel: 'Free models',
    presetNames: ['openrouter'],
    models: OPENROUTER_MODELS,
    apiKeyPlaceholder: 'sk-or-...',
  },
  {
    id: 'cerebras',
    label: 'Cerebras',
    description: '1M tokens/day free. Ultra-fast inference with Llama 4 and Qwen models.',
    badge: 'free',
    badgeLabel: 'Free tier',
    presetNames: ['cerebras'],
    models: CEREBRAS_MODELS,
    apiKeyPlaceholder: 'csk-...',
  },
  {
    id: 'sambanova',
    label: 'SambaNova',
    description: 'Free access to large Llama models including 405B. No credit card needed.',
    badge: 'free',
    badgeLabel: 'Free tier',
    presetNames: ['sambanova'],
    models: SAMBANOVA_MODELS,
    apiKeyPlaceholder: 'sn-...',
  },
  // ── Paid API ──
  {
    id: 'anthropic-api',
    label: 'Anthropic API',
    description: 'Direct API access to Claude models — pay-per-token. Get your key at console.anthropic.com.',
    badge: 'api-key',
    badgeLabel: 'API Key',
    presetNames: ['anthropic-api'],
    models: CLAUDE_MODELS,
    apiKeyPlaceholder: 'sk-ant-...',
  },
  {
    id: 'openai-api',
    label: 'OpenAI API',
    description: 'Direct API access to GPT models — pay-per-token. Get your key at platform.openai.com.',
    badge: 'api-key',
    badgeLabel: 'API Key',
    presetNames: ['openai-api'],
    models: OPENAI_MODELS,
    apiKeyPlaceholder: 'sk-...',
  },
  {
    id: 'mistral',
    label: 'Mistral',
    description: 'Free experiment tier — up to 1B tokens/month. European provider with strong models.',
    badge: 'free',
    badgeLabel: 'Free experiment tier',
    presetNames: ['mistral'],
    models: MISTRAL_MODELS,
    apiKeyPlaceholder: 'mis-...',
  },
  {
    id: 'deepseek',
    label: 'DeepSeek',
    description: '5M free tokens on signup, then $0.28/M tokens. Strong reasoning and chat models.',
    badge: 'free',
    badgeLabel: 'Free + cheap',
    presetNames: ['deepseek'],
    models: DEEPSEEK_MODELS,
    apiKeyPlaceholder: 'sk-...',
  },
  // ── Local ──
  {
    id: 'ollama',
    label: 'Ollama (local)',
    description: 'Run open-source models on your own machine. Free, private, no API key needed.',
    badge: 'local',
    badgeLabel: 'Local',
    presetNames: ['ollama'],
    models: OLLAMA_MODELS,
  },
  // ── Internal (hidden unless dev mode) ──
  {
    id: 'claude-subscription',
    label: 'Claude (via subscription proxy)',
    description: 'Use your existing Claude Pro/Max subscription. Requires a local proxy running.',
    badge: 'internal',
    badgeLabel: 'Internal',
    presetNames: ['claude-proxy', 'claude-proxy-alt'],
    models: CLAUDE_MODELS,
    internal: true,
  },
  {
    id: 'openai-subscription',
    label: 'OpenAI (via Codex proxy)',
    description: 'Use your existing ChatGPT Plus subscription. Requires Codex proxy running locally.',
    badge: 'internal',
    badgeLabel: 'Internal',
    presetNames: ['openai-proxy'],
    models: OPENAI_MODELS,
    internal: true,
  },
];

/** Look up friendly model name from all provider groups. */
export function getModelDisplayName(modelId: string): string {
  for (const group of PROVIDER_GROUPS) {
    const match = group.models.find((m) => m.id === modelId);
    if (match) return match.name;
  }
  return modelId;
}

/** Get provider groups filtered by dev mode. */
export function getVisibleProviderGroups(devMode = false): ProviderGroup[] {
  if (devMode) return PROVIDER_GROUPS;
  return PROVIDER_GROUPS.filter((g) => !g.internal);
}
