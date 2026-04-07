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
    title: 'Gemini',
    badge: 'Free',
    badgeClassName: 'text-emerald-600 bg-emerald-500/10',
    description: 'Best default if you do not want to pay for user AI usage.',
    detail: 'Uses Google Gemini. You still need a free Gemini API key from Google AI Studio.',
    hostedSupported: true,
  },
  'openai-api': {
    name: 'openai-api',
    title: 'ChatGPT by OpenAI',
    badge: 'API key',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'Supported path today for GPT models in Launchboard.',
    detail: 'Requires an OpenAI API key. ChatGPT Plus is separate and does not include direct app access here.',
    hostedSupported: true,
  },
  'anthropic-api': {
    name: 'anthropic-api',
    title: 'Claude by Anthropic',
    badge: 'API key',
    badgeClassName: 'text-amber-600 bg-amber-500/10',
    description: 'Supported path today for Claude models in Launchboard.',
    detail: 'Requires an Anthropic API key. Claude Pro/Max is separate and does not include direct app access here.',
    hostedSupported: true,
  },
  ollama: {
    name: 'ollama',
    title: 'Local / private',
    badge: 'No account',
    badgeClassName: 'text-blue-600 bg-blue-500/10',
    description: 'Run models on your own machine.',
    detail: 'Best for privacy-minded self-host users. Not available in hosted mode.',
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
