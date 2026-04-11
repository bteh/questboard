import type { ProviderPreset } from '@/types/settings';

export type PopularProviderName = 'gemini' | 'groq' | 'openai-api' | 'anthropic-api' | 'ollama';

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
  'groq',
  'openai-api',
  'anthropic-api',
  'ollama',
];

export const POPULAR_PROVIDER_CHOICES: Record<PopularProviderName, PopularProviderChoice> = {
  gemini: {
    name: 'gemini',
    title: 'Google Gemini',
    badge: 'Free tier',
    badgeClassName: 'text-emerald-600 bg-emerald-500/10',
    description: 'Google Gemini models. Free tier available — no credit card required.',
    detail: 'Get your key from Google AI Studio. Free tier limits change periodically; check their pricing page for current quotas.',
    hostedSupported: true,
  },
  groq: {
    name: 'groq',
    title: 'Groq',
    badge: 'Free tier',
    badgeClassName: 'text-emerald-600 bg-emerald-500/10',
    description: 'Open-source models (Llama, Mixtral) running on Groq hardware. Free tier available.',
    detail: 'Get your key from console.groq.com. Known for very fast inference. Free tier limits change periodically.',
    hostedSupported: true,
  },
  'openai-api': {
    name: 'openai-api',
    title: 'OpenAI',
    badge: 'Paid',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'GPT models via the OpenAI API. Pay per use — not included with ChatGPT Plus.',
    detail: 'Get your key from platform.openai.com. Requires billing set up separately from ChatGPT Plus.',
    hostedSupported: true,
  },
  'anthropic-api': {
    name: 'anthropic-api',
    title: 'Anthropic Claude',
    badge: 'Paid',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'Claude models via the Anthropic API. Pay per use — not included with Claude Pro.',
    detail: 'Get your key from console.anthropic.com. Requires billing set up separately from Claude Pro.',
    hostedSupported: true,
  },
  ollama: {
    name: 'ollama',
    title: 'Ollama (local)',
    badge: 'Local',
    badgeClassName: 'text-blue-600 bg-blue-500/10',
    description: 'Run AI models on your own machine. Private and free forever.',
    detail: 'Requires installing Ollama and enough disk space + RAM for the model. Fully offline.',
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
