import type { ProviderPreset } from '@/types/settings';

export type PopularProviderName = 'gemini' | 'openai-api' | 'anthropic-api' | 'ollama';

export interface PopularProviderChoice {
  name: PopularProviderName;
  title: string;
  badge: string;
  badgeClassName: string;
  description: string;
  detail: string;
  hostedSupported: boolean;
}

export const POPULAR_PROVIDER_ORDER: PopularProviderName[] = [
  'gemini',
  'openai-api',
  'anthropic-api',
  'ollama',
];

export const POPULAR_PROVIDER_CHOICES: Record<PopularProviderName, PopularProviderChoice> = {
  gemini: {
    name: 'gemini',
    title: 'Google Gemini',
    badge: 'Free',
    badgeClassName: 'text-emerald-600 bg-emerald-500/10',
    description: 'Free, fast, and easy. Get an API key from Google AI Studio in 30 seconds — no credit card needed.',
    detail: 'Uses Gemini 2.5 Flash. 250 free requests/day, more than enough for job searching.',
    hostedSupported: true,
  },
  'openai-api': {
    name: 'openai-api',
    title: 'OpenAI',
    badge: 'Paid',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'GPT models via the OpenAI API. Requires a separate API key (not included with ChatGPT Plus).',
    detail: 'Uses GPT-4.1 Mini by default. Requires billing set up on platform.openai.com.',
    hostedSupported: true,
  },
  'anthropic-api': {
    name: 'anthropic-api',
    title: 'Anthropic Claude',
    badge: 'Paid',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'Claude models via the Anthropic API. Requires a separate API key (not included with Claude Pro).',
    detail: 'Uses Claude Sonnet by default. Requires billing set up on console.anthropic.com.',
    hostedSupported: true,
  },
  ollama: {
    name: 'ollama',
    title: 'Ollama (local)',
    badge: 'Private',
    badgeClassName: 'text-blue-600 bg-blue-500/10',
    description: 'Run AI models on your own machine. Nothing leaves your computer. Requires installing Ollama separately.',
    detail: 'Best for privacy. Requires 2GB+ disk space and decent hardware for good speed.',
    hostedSupported: false,
  },
};

export function getPopularProviderNames(hostedMode: boolean): PopularProviderName[] {
  return POPULAR_PROVIDER_ORDER.filter((name) => hostedMode ? POPULAR_PROVIDER_CHOICES[name].hostedSupported : true);
}

export function getPopularProviderPresets(
  presets: ProviderPreset[] | undefined,
  hostedMode: boolean,
): ProviderPreset[] {
  if (!presets) return [];
  const byName = new Map(presets.map((preset) => [preset.name, preset] as const));
  return getPopularProviderNames(hostedMode)
    .map((name) => byName.get(name))
    .filter((preset): preset is ProviderPreset => !!preset);
}

export function isPopularProvider(name: string, hostedMode: boolean): boolean {
  return getPopularProviderNames(hostedMode).includes(name as PopularProviderName);
}
