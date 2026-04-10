import { type ReactElement, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { CheckCircle2, ExternalLink, Loader2, Monitor, Shield, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useWorkspace } from '@/contexts/workspace-context';
import {
  useDetectOllama,
  useLLMPresets,
  useLLMStatus,
  useTestConnection,
  useUpdateLLM,
} from '@/hooks/use-settings';
import {
  POPULAR_PROVIDER_CHOICES,
  getPopularProviderNames,
  type PopularProviderName,
} from '@/lib/llm-choice';
import { cn } from '@/lib/utils';

interface ConnectAiPopoverProps {
  /**
   * The element that opens the popover. Pass any single React element —
   * it'll be wired up via base-ui's render-prop so the popover state
   * (aria-expanded, click handlers) attaches to your element directly.
   *
   * Examples:
   *   <ConnectAiPopover><Button>Connect AI</Button></ConnectAiPopover>
   *   <ConnectAiPopover><button className="...">…</button></ConnectAiPopover>
   */
  children: ReactElement;
  /** Where to anchor the popover relative to the trigger. */
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
}

const KEY_URLS: Record<PopularProviderName, string> = {
  gemini: 'https://aistudio.google.com/apikey',
  groq: 'https://console.groq.com/keys',
  'openai-api': 'https://platform.openai.com/api-keys',
  'anthropic-api': 'https://console.anthropic.com/settings/keys',
  ollama: 'https://ollama.com/download',
};

const KEY_LABELS: Record<PopularProviderName, string> = {
  gemini: 'Get a free Gemini key',
  groq: 'Get a free Groq key',
  'openai-api': 'Get an OpenAI key',
  'anthropic-api': 'Get an Anthropic key',
  ollama: 'Install Ollama',
};

const PASTE_PLACEHOLDERS: Record<PopularProviderName, string> = {
  gemini: 'Paste Gemini key',
  groq: 'Paste Groq key',
  'openai-api': 'Paste OpenAI key',
  'anthropic-api': 'Paste Anthropic key',
  ollama: 'No key needed',
};

/**
 * Inline AI connect flow. Lives in the sidebar pill, the dashboard
 * "ready to launch" hero, and any "Connect AI" affordance on the
 * search page.
 *
 * The goal is that no "Connect AI" button anywhere in the app should
 * navigate the user to a separate Settings page just to paste a key.
 * Settings is still the home for advanced provider tweaks (custom
 * endpoints, model picking, dev presets) but the 80% case — pick a
 * provider, paste a key, click Connect — happens in this popover.
 */
export function ConnectAiPopover({ children, side = 'top', align = 'start' }: ConnectAiPopoverProps) {
  const navigate = useNavigate();
  const { hostedMode } = useWorkspace();
  const { data: llm } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();
  const { data: ollamaDetect } = useDetectOllama(!llm?.configured && !hostedMode);

  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState<PopularProviderName>('gemini');
  const [apiKey, setApiKey] = useState('');

  const openFullSettings = () => {
    setOpen(false);
    navigate({ to: '/settings', search: { tab: 'ai' } });
  };

  const isConnected = !!llm?.available;
  const isWorking = updateLLM.isPending || testConnection.isPending;
  const availableProviders = getPopularProviderNames(hostedMode);
  const isOllama = provider === 'ollama';
  const ollamaReady = !!ollamaDetect?.detected;

  const connect = () => {
    const trimmed = apiKey.trim();
    if (!isOllama && !trimmed) {
      toast.error('Paste an API key first.');
      return;
    }

    const preset = presets?.find((item) => item.name === provider);
    if (!preset) {
      toast.error(`${POPULAR_PROVIDER_CHOICES[provider].title} preset is unavailable.`);
      return;
    }

    const config = isOllama
      ? {
          provider,
          base_url: 'http://localhost:11434/v1',
          api_key: 'ollama',
          model: ollamaDetect?.recommended_model || 'llama3.1',
        }
      : { provider, base_url: preset.base_url, api_key: trimmed, model: preset.model };

    updateLLM.mutate(config, {
      onSuccess: () => {
        testConnection.mutate(undefined, {
          onSuccess: (result) => {
            if (result.success) {
              toast.success(`Connected to ${POPULAR_PROVIDER_CHOICES[provider].title}`);
              setApiKey('');
              setOpen(false);
            } else {
              toast.error(result.message || 'Connection failed — check your key');
            }
          },
          onError: (error) =>
            toast.error(error instanceof Error ? error.message : 'Connection test failed'),
        });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Failed to save settings'),
    });
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={children} />
      <PopoverContent align={align} side={side} sideOffset={10} className="w-[340px]">
        {isConnected ? (
          <ConnectedView
            label={llm?.label ?? 'Provider connected'}
            onOpenSettings={openFullSettings}
          />
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-light">
                <Sparkles className="h-4 w-4 text-brand" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-text-primary">Connect AI</p>
                <p className="text-[11px] text-text-muted">
                  Unlocks resume-fit ranking and tailored drafts
                </p>
              </div>
            </div>

            {/* Provider tabs */}
            <div
              role="tablist"
              aria-label="AI provider"
              className="flex gap-1 rounded-lg border border-border-default bg-bg-subtle p-0.5"
            >
              {availableProviders.map((name) => {
                const active = provider === name;
                return (
                  <button
                    key={name}
                    role="tab"
                    type="button"
                    aria-selected={active}
                    onClick={() => {
                      setProvider(name);
                      setApiKey('');
                    }}
                    className={cn(
                      'flex-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors',
                      active
                        ? 'bg-bg-card text-text-primary shadow-sm'
                        : 'text-text-muted hover:text-text-secondary',
                    )}
                  >
                    {name === 'gemini'
                      ? 'Gemini ★'
                      : name === 'groq'
                        ? 'Groq'
                        : name === 'openai-api'
                          ? 'OpenAI'
                          : name === 'anthropic-api'
                            ? 'Claude'
                            : 'Local'}
                  </button>
                );
              })}
            </div>

            {/* Provider-specific helper line */}
            <div className="space-y-1">
              <p className="text-[11px] text-text-muted leading-relaxed">
                {POPULAR_PROVIDER_CHOICES[provider].description}
              </p>
              <a
                href={KEY_URLS[provider]}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[11px] font-medium text-brand hover:underline"
              >
                {KEY_LABELS[provider]}
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>

            {/* Paste field — Ollama variant has no key */}
            {isOllama ? (
              <div className="rounded-lg border border-border-default bg-bg-subtle/40 px-3 py-2.5 text-[11px] text-text-muted">
                {ollamaReady ? (
                  <span className="inline-flex items-center gap-1.5 font-medium text-success">
                    <Monitor className="h-3.5 w-3.5" />
                    Detected on localhost ({ollamaDetect?.recommended_model})
                  </span>
                ) : (
                  <>
                    Install Ollama and run <code className="rounded bg-bg-muted px-1 py-0.5 text-[10px]">ollama pull llama3.2:3b</code>, then click Connect.
                  </>
                )}
              </div>
            ) : (
              <Input
                type="password"
                placeholder={PASTE_PLACEHOLDERS[provider]}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && apiKey.trim() && !isWorking) connect();
                }}
                className="h-8 text-xs"
                autoFocus
              />
            )}

            <Button
              size="sm"
              className="w-full"
              onClick={connect}
              disabled={isWorking || (!isOllama && !apiKey.trim())}
            >
              {isWorking ? (
                <>
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                  Connecting…
                </>
              ) : (
                'Connect'
              )}
            </Button>

            <div className="flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
              <Shield className="h-3 w-3 shrink-0 text-emerald-500 mt-0.5" />
              <p>
                {hostedMode
                  ? 'Your key is encrypted on Launchboard and only sent to that provider.'
                  : 'Your key is stored on this computer and only sent to that provider.'}
              </p>
            </div>

            <div className="border-t border-border-default pt-2">
              <button
                type="button"
                onClick={openFullSettings}
                className="text-[10px] text-text-muted transition-colors hover:text-text-secondary"
              >
                Need a custom provider or model? Open full settings →
              </button>
            </div>
          </div>
        )}
      </PopoverContent>
    </Popover>
  );
}

interface ConnectedViewProps {
  label: string;
  onOpenSettings: () => void;
}

function ConnectedView({ label, onOpenSettings }: ConnectedViewProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2.5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-success/10">
          <CheckCircle2 className="h-4 w-4 text-success" />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text-primary">AI is connected</p>
          <p className="truncate text-[11px] text-text-muted">{label}</p>
        </div>
      </div>
      <p className="text-[11px] leading-relaxed text-text-muted">
        Resume-fit ranking, search suggestions, cover letters, and company notes are all unlocked.
      </p>
      <Button variant="outline" size="sm" className="w-full" onClick={onOpenSettings}>
        Switch provider or model
      </Button>
    </div>
  );
}
