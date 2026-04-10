import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  Monitor,
  Shield,
  Sparkles,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useWorkspace } from '@/contexts/workspace-context';
import {
  useDetectOllama,
  useLLMPresets,
  useLLMStatus,
  useTestConnection,
  useUpdateLLM,
} from '@/hooks/use-settings';
import { POPULAR_PROVIDER_CHOICES, type PopularProviderName } from '@/lib/llm-choice';
import { cn } from '@/lib/utils';

/**
 * Inline AI connection card for the ReadyToLaunchHero.
 *
 * Replaces the old hidden-in-a-popover approach with a prominent,
 * always-visible section that guides non-technical users through
 * connecting Gemini (free, 30 seconds) as the recommended default.
 *
 * Design informed by research on Cursor, Jan.ai, AnythingLLM, Raycast:
 *   - Never gate core functionality behind "go get an API key"
 *   - Lead with the easiest free option
 *   - Make skipping obvious and guilt-free
 *   - Show the value prop (7-dimension scoring vs keyword-only)
 */
export function InlineAiConnect() {
  const navigate = useNavigate();
  const { hostedMode } = useWorkspace();
  const { data: llm } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();
  const { data: ollamaDetect } = useDetectOllama(!llm?.configured && !hostedMode);

  const [apiKey, setApiKey] = useState('');
  const [showOtherProviders, setShowOtherProviders] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<PopularProviderName>('gemini');
  const [justConnected, setJustConnected] = useState(false);

  const isWorking = updateLLM.isPending || testConnection.isPending;
  const ollamaReady = !!ollamaDetect?.detected;
  const isOllama = selectedProvider === 'ollama';

  // If AI just got connected, show success state
  if (justConnected || llm?.available) {
    return (
      <div className="rounded-2xl border border-success/30 bg-success/5 p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/15">
            <CheckCircle2 className="h-5 w-5 text-success" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-text-primary">AI scoring is ready</p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              Every job will be scored across 7 dimensions against your resume.
              You'll see fit scores, strengths, and gaps for each match.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const connect = () => {
    const trimmed = apiKey.trim();
    if (!isOllama && !trimmed) {
      toast.error('Paste an API key first.');
      return;
    }

    const preset = presets?.find((item) => item.name === selectedProvider);
    if (!preset) {
      toast.error(`${POPULAR_PROVIDER_CHOICES[selectedProvider].title} preset is unavailable.`);
      return;
    }

    const config = isOllama
      ? {
          provider: selectedProvider,
          base_url: 'http://localhost:11434/v1',
          api_key: 'ollama',
          model: ollamaDetect?.recommended_model || 'llama3.1',
        }
      : { provider: selectedProvider, base_url: preset.base_url, api_key: trimmed, model: preset.model };

    updateLLM.mutate(config, {
      onSuccess: () => {
        testConnection.mutate(undefined, {
          onSuccess: (result) => {
            if (result.success) {
              toast.success(`Connected to ${POPULAR_PROVIDER_CHOICES[selectedProvider].title}!`);
              setApiKey('');
              setJustConnected(true);
            } else {
              toast.error(result.message || 'Connection failed — check your key and try again');
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

  // Primary Gemini flow vs other provider flow
  const showingGemini = selectedProvider === 'gemini';

  return (
    <div className="space-y-3">
      {/* Value prop card */}
      <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand-light/30 to-brand-light/5 p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/15">
            <Zap className="h-5 w-5 text-brand" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-text-primary">
              Unlock AI-powered job scoring
            </p>
            <p className="mt-1 text-xs leading-relaxed text-text-tertiary">
              Without AI, jobs are matched by keywords only.
              With AI, each job is scored across{' '}
              <span className="font-medium text-text-secondary">7 dimensions</span> against your
              actual resume — technical fit, career progression, compensation potential, and more.
            </p>
          </div>
        </div>

        {/* Gemini recommended flow */}
        {showingGemini && (
          <div className="mt-4 rounded-xl border border-border-default bg-bg-card p-4">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-brand" />
              <span className="text-xs font-semibold text-text-primary">
                Google Gemini
              </span>
              <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
                Free
              </span>
              <span className="rounded-full bg-brand-light/60 px-2 py-0.5 text-[10px] font-medium text-brand">
                Recommended
              </span>
            </div>

            <div className="mt-3 space-y-2.5">
              {/* Step 1 */}
              <div className="flex items-start gap-2.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-light text-[10px] font-bold text-brand">
                  1
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <a
                    href="https://aistudio.google.com/apikey"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                  >
                    Get your free API key from Google AI Studio
                    <ExternalLink className="h-3 w-3" />
                  </a>
                  <p className="mt-0.5 text-[11px] text-text-muted">
                    Sign in with your Google account, click "Create API key" — takes 15 seconds
                  </p>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex items-start gap-2.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-light text-[10px] font-bold text-brand">
                  2
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  <p className="text-xs font-medium text-text-secondary">Paste your key below</p>
                  <Input
                    type="password"
                    placeholder="AIzaSy..."
                    value={apiKey}
                    onChange={(event) => setApiKey(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && apiKey.trim() && !isWorking) connect();
                    }}
                    className="mt-1.5 h-8 text-xs"
                    autoComplete="off"
                  />
                </div>
              </div>

              {/* Step 3 — Connect button */}
              <div className="flex items-start gap-2.5">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-light text-[10px] font-bold text-brand">
                  3
                </span>
                <div className="min-w-0 flex-1">
                  <Button
                    size="sm"
                    className="w-full"
                    onClick={connect}
                    disabled={isWorking || !apiKey.trim()}
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
                </div>
              </div>
            </div>

            <div className="mt-3 flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
              <Shield className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
              <p>Your key stays on this computer and is only sent to Google.</p>
            </div>
          </div>
        )}

        {/* Other provider flow (ChatGPT, Claude, or Ollama) */}
        {!showingGemini && (
          <div className="mt-4 rounded-xl border border-border-default bg-bg-card p-4">
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-text-primary">
                {POPULAR_PROVIDER_CHOICES[selectedProvider].title}
              </span>
              <span className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                POPULAR_PROVIDER_CHOICES[selectedProvider].badgeClassName,
              )}>
                {POPULAR_PROVIDER_CHOICES[selectedProvider].badge}
              </span>
            </div>
            <p className="mt-1.5 text-[11px] text-text-muted">
              {POPULAR_PROVIDER_CHOICES[selectedProvider].description}
            </p>

            {isOllama ? (
              <div className="mt-3 rounded-lg border border-border-default bg-bg-subtle/40 px-3 py-2.5 text-[11px] text-text-muted">
                {ollamaReady ? (
                  <span className="inline-flex items-center gap-1.5 font-medium text-success">
                    <Monitor className="h-3.5 w-3.5" />
                    Detected on localhost ({ollamaDetect?.recommended_model})
                  </span>
                ) : (
                  <>
                    Install Ollama from{' '}
                    <a href="https://ollama.com/download" target="_blank" rel="noopener noreferrer" className="font-medium text-brand hover:underline">
                      ollama.com
                    </a>
                    {' '}and run{' '}
                    <code className="rounded bg-bg-muted px-1 py-0.5 text-[10px]">ollama pull llama3.2:3b</code>
                  </>
                )}
              </div>
            ) : (
              <div className="mt-3 space-y-2">
                <a
                  href={selectedProvider === 'openai-api'
                    ? 'https://platform.openai.com/api-keys'
                    : 'https://console.anthropic.com/settings/keys'}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                >
                  Get your API key <ExternalLink className="h-3 w-3" />
                </a>
                <Input
                  type="password"
                  placeholder={selectedProvider === 'openai-api' ? 'sk-...' : 'sk-ant-...'}
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && apiKey.trim() && !isWorking) connect();
                  }}
                  className="h-8 text-xs"
                  autoComplete="off"
                />
              </div>
            )}

            <Button
              size="sm"
              className="mt-3 w-full"
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

            <div className="mt-3 flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
              <Shield className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
              <p>
                {isOllama
                  ? 'Runs entirely on your computer. Nothing leaves your machine.'
                  : `Your key stays on this computer and is only sent to ${POPULAR_PROVIDER_CHOICES[selectedProvider].title}.`}
              </p>
            </div>

            <button
              type="button"
              onClick={() => { setShowOtherProviders(false); setSelectedProvider('gemini'); setApiKey(''); }}
              className="mt-2 text-[10px] text-text-muted transition-colors hover:text-text-secondary"
            >
              ← Back to Gemini (recommended)
            </button>
          </div>
        )}

        {/* Other provider links */}
        {showingGemini && (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setShowOtherProviders((v) => !v)}
              className="flex items-center gap-1 text-[11px] text-text-muted transition-colors hover:text-text-secondary"
            >
              {showOtherProviders ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              Use a different AI provider
            </button>

            {showOtherProviders && (
              <div className="mt-2 flex flex-wrap gap-2">
                {(['openai-api', 'anthropic-api', 'ollama'] as const).map((name) => {
                  if (name === 'ollama' && hostedMode) return null;
                  return (
                    <button
                      key={name}
                      type="button"
                      onClick={() => { setSelectedProvider(name); setApiKey(''); }}
                      className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-card px-3 py-1.5 text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle"
                    >
                      {POPULAR_PROVIDER_CHOICES[name].title}
                      <span className={cn('rounded-full px-1.5 py-0.5 text-[9px] font-semibold', POPULAR_PROVIDER_CHOICES[name].badgeClassName)}>
                        {POPULAR_PROVIDER_CHOICES[name].badge}
                      </span>
                    </button>
                  );
                })}
                <button
                  type="button"
                  onClick={() => navigate({ to: '/settings', search: { tab: 'ai' } })}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-card px-3 py-1.5 text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle"
                >
                  More in Settings →
                </button>
              </div>
            )}

            {/* Ollama auto-detect nudge */}
            {ollamaReady && (
              <button
                type="button"
                onClick={() => { setSelectedProvider('ollama'); }}
                className="mt-2 inline-flex items-center gap-1.5 text-[11px] font-medium text-success"
              >
                <Monitor className="h-3.5 w-3.5" />
                Ollama detected — click to connect
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
