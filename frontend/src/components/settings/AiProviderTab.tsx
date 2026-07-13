import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  HelpCircle,
  Loader2,
  Monitor,
  Shield,
  Sparkles,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useLLMStatus, useLLMPresets, useProviderModels, useDetectOllama, useDetectLocalAI, useTestConnection, useUpdateLLM } from '@/hooks/use-settings';
import { useWorkspace } from '@/contexts/workspace-context';
import { POPULAR_PROVIDER_CHOICES, getPopularProviderPresets, isPopularProvider } from '@/lib/llm-choice';
import { getModelDisplayName } from '@/lib/llm-providers';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { LLMConfig, LLMStatus } from '@/types/settings';

// ── Provider metadata for cards ──────────────────────────────────────
// Maps backend preset names to user-friendly descriptions and key URLs.
const PROVIDER_INFO: Record<string, { description: string; keyUrl?: string; keyLabel?: string; badge: string; badgeColor: string; recommended?: boolean }> = {
  groq:           { description: 'Free and fast, and it does not train on what you send. Best for ranking your resume. 1,000 uses a day.', keyUrl: 'https://console.groq.com/keys', keyLabel: 'Create a free Groq key', badge: 'Free', badgeColor: 'text-success bg-success/10', recommended: true },
  gemini:         { description: 'Best with your own free key. Google can use free-tier data to improve its products, so use it for drafting, not resumes.', keyUrl: 'https://aistudio.google.com/apikey', keyLabel: 'Get a free Gemini key', badge: 'Free', badgeColor: 'text-success bg-success/10' },
  cerebras:       { description: 'Ultra-fast — generous free tier', keyUrl: 'https://cloud.cerebras.ai', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-success bg-success/10' },
  openrouter:     { description: '29 free AI models through one key — 200 uses/day', keyUrl: 'https://openrouter.ai/keys', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-success bg-success/10' },
  mistral:        { description: 'European AI provider — generous free tier', keyUrl: 'https://console.mistral.ai/api-keys', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-success bg-success/10' },
  sambanova:      { description: 'Powerful AI — $5 free trial credits', keyUrl: 'https://cloud.sambanova.ai', keyLabel: 'Get free key', badge: 'Trial', badgeColor: 'text-amber-600 bg-amber-500/10' },
  deepseek:       { description: 'Strong AI — free signup bonus, then very cheap', keyUrl: 'https://platform.deepseek.com/api_keys', keyLabel: 'Get key', badge: 'Trial + cheap', badgeColor: 'text-amber-600 bg-amber-500/10' },
  'openai-api':   { description: 'Supported today for GPT models in Questboard. Requires an OpenAI API key.', keyUrl: 'https://platform.openai.com/api-keys', keyLabel: 'Get OpenAI API key', badge: 'Paid', badgeColor: 'text-amber-600 bg-amber-500/10' },
  'anthropic-api': { description: 'Supported today for Claude models in Questboard. Requires an Anthropic API key.', keyUrl: 'https://console.anthropic.com/settings/keys', keyLabel: 'Get Anthropic API key', badge: 'Paid', badgeColor: 'text-amber-600 bg-amber-500/10' },
  ollama:         { description: 'Runs on your computer — completely private, no account needed', keyUrl: 'https://ollama.com', keyLabel: 'Install Ollama (free)', badge: 'No account', badgeColor: 'text-brand bg-brand/10' },
  custom:         { description: 'Connect your own local AI model or OpenAI-compatible server', badge: 'Custom', badgeColor: 'text-brand bg-brand/10' },
};

/** Dev mode shows proxy/internal presets — requires explicit opt-in via localStorage */
function isDevMode(): boolean {
  try {
    return localStorage.getItem('questboard-dev-mode') === 'true';
  } catch { return false; }
}

function formatModelLabel(modelId: string): string {
  if (!modelId) return '';
  const known = getModelDisplayName(modelId);
  if (known !== modelId) return known;

  const withoutDate = modelId.replace(/-\d{8}$/, '');
  const titleized = withoutDate
    .replace(/^claude-/, 'Claude ')
    .replace(/^gpt-/, 'GPT ')
    .replace(/^gemini-/, 'Gemini ')
    .replace(/-/g, ' ')
    .replace(/\b([a-z])/g, (match) => match.toUpperCase());

  return titleized.replace(/\b(\d+)\s+(\d+)\b/g, '$1.$2');
}

function getConnectedLabel(llm: LLMStatus): string {
  if (llm.provider !== 'custom') {
    if (llm.provider === 'openai-api') return 'ChatGPT by OpenAI';
    if (llm.provider === 'anthropic-api') return 'Claude by Anthropic';
    if (llm.provider === 'gemini') return 'Gemini by Google';
    if (llm.provider === 'ollama') return 'Local / private';
    return llm.label || llm.provider || 'Configured provider';
  }
  const model = (llm.model || '').toLowerCase();
  if (model.startsWith('claude-')) return 'Claude-compatible endpoint';
  if (model.startsWith('gpt-') || model.startsWith('o3') || model.startsWith('o4')) return 'ChatGPT-compatible endpoint';
  if (model.startsWith('gemini-')) return 'Gemini-compatible endpoint';
  return 'Custom endpoint';
}

/**
 * True if a model ID looks like a flagship vendor model (Claude/GPT/Gemini/o-series).
 *
 * We use this to detect when a localhost "AI server" is actually a third-party
 * proxy (cliproxyapi, vibeproxy, Quotio, etc.) re-exporting a Claude Code or
 * Codex CLI OAuth subscription as if it were a local runtime. Real local
 * runtimes (Ollama, LM Studio, vLLM, llama.cpp) report model IDs like
 * "llama3.2:3b", "mistral", "qwen2.5-coder", etc. — not "claude-sonnet-4-5".
 *
 * When we see flagship IDs we surface a warning so the user understands
 * that connecting will burn their consumer subscription quota and may
 * violate the vendor's terms of service.
 */
function looksLikeFlagshipModel(modelId: string): boolean {
  const m = modelId.toLowerCase();
  return (
    m.startsWith('claude-') ||
    m.startsWith('gpt-') ||
    m.startsWith('o1-') ||
    m.startsWith('o3-') ||
    m.startsWith('o4-') ||
    m.startsWith('gemini-')
  );
}

interface DetectedServerLike {
  models: string[];
}

function serversIncludeFlagshipModels(servers: DetectedServerLike[] | undefined): boolean {
  if (!servers || servers.length === 0) return false;
  return servers.some((server) => server.models?.some(looksLikeFlagshipModel));
}

interface FlagshipDetectionWarningProps {
  className?: string;
}

/**
 * Disclosure shown above any "detected on your machine" card whose server
 * advertises flagship Claude / GPT / Gemini model IDs. We don't block the
 * user — they may know exactly what they're doing — but we make sure they
 * can't click "connect" without understanding what they're wiring up.
 */
function FlagshipDetectionWarning({ className }: FlagshipDetectionWarningProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900',
        'dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200',
        className,
      )}
      role="alert"
    >
      <p className="font-semibold">This local server is exposing vendor flagship models.</p>
      <p className="mt-1">
        It looks like a third-party proxy (e.g. <code className="rounded bg-amber-100/60 px-1 py-0.5 text-[11px] dark:bg-amber-900/40">cliproxyapi</code>,
        <code className="ml-0.5 rounded bg-amber-100/60 px-1 py-0.5 text-[11px] dark:bg-amber-900/40">vibeproxy</code>) wrapping your
        Claude Code, Codex CLI, or Gemini CLI OAuth subscription. Connecting Questboard to it will charge each
        request against your consumer subscription quota and may violate Anthropic / OpenAI / Google's terms of service —
        Questboard runs many calls per search and you can be rate-limited or have the upstream account suspended.
      </p>
      <p className="mt-1.5 text-amber-800/80 dark:text-amber-200/80">
        If you have a real API key, use the Gemini / ChatGPT / Claude tabs above instead.
      </p>
    </div>
  );
}

export function AiProviderTab() {
  const { hostedMode } = useWorkspace();
  const { data: llm, refetch: refetchLLM } = useLLMStatus();
  // Always fetch fresh LLM status when the user opens Settings — they're
  // here to check/fix their AI connection, so stale data is worse than
  // an extra request.
  useEffect(() => { refetchLLM(); }, [refetchLLM]);
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();

  const derivedLlmForm = useMemo<LLMConfig>(() => {
    if (!llm) {
      return { provider: '', base_url: '', api_key: '', model: '' };
    }
    const preset = presets?.find((item) => item.name === llm.provider);
    return {
      provider: llm.provider,
      base_url: preset?.base_url || '',
      api_key: '',
      model: llm.model,
    };
  }, [llm, presets]);
  const [llmDraft, setLlmDraft] = useState<LLMConfig | null>(null);
  const llmForm = llmDraft ?? derivedLlmForm;
  const setLlmForm = useCallback((next: LLMConfig | ((prev: LLMConfig) => LLMConfig)) => {
    setLlmDraft((prev) => {
      const base = prev ?? derivedLlmForm;
      return typeof next === 'function' ? next(base) : next;
    });
  }, [derivedLlmForm]);
  const [showDevFields, setShowDevFields] = useState(false);
  const [autoDetectDismissed] = useState(false);
  const [showAllProviders, setShowAllProviders] = useState(false);
  const [geminiKey, setGeminiKey] = useState('');
  // AI tab — controls the simplified primary connect card.
  const [quickProvider, setQuickProvider] = useState<'groq' | 'gemini' | 'openai-api' | 'anthropic-api' | 'ollama'>('groq');
  const [quickKey, setQuickKey] = useState('');
  const [showAdvancedAi, setShowAdvancedAi] = useState(false);

  // Detect Ollama and local AI servers when no LLM is configured, AI is offline, or custom provider is selected
  // Only scan localhost in self-hosted mode — hosted backend can't reach user's localhost anyway
  const needsAI = !hostedMode && (!llm?.configured || (llm?.configured && !llm?.available)) && !autoDetectDismissed;
  const customSelected = llmForm.provider === 'custom';
  const { data: ollamaDetect } = useDetectOllama(needsAI);
  const { data: localAI } = useDetectLocalAI(needsAI || (!hostedMode && customSelected));

  const selectedPreset = presets?.find((item) => item.name === llmForm.provider);
  const providerInfo = llmForm.provider ? PROVIDER_INFO[llmForm.provider] : null;
  const { data: liveModels, isFetching: isFetchingModels } = useProviderModels(
    llmForm.base_url,
    llmForm.api_key,
    !!llmForm.base_url && (!selectedPreset?.needs_api_key || !!llmForm.api_key),
  );

  const selectProvider = (providerName: string) => {
    const preset = presets?.find((item) => item.name === providerName);
    setLlmForm((prev) => ({
      ...prev,
      provider: providerName,
      base_url: preset?.base_url || prev.base_url,
      model: preset?.model || prev.model,
    }));
  };

  const handleSaveLLM = () => {
    updateLLM.mutate(llmForm, {
      onSuccess: () => {
        testConnection.mutate(undefined, {
          onSuccess: (result) => {
            if (result.success) {
              toast.success(`Connected to ${result.provider || 'provider'}`);
            } else {
              toast.error(result.message || 'Connection failed');
            }
          },
          onError: (error) => toast.error(error instanceof Error ? error.message : 'Connection test failed'),
        });
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save provider settings'),
    });
  };

  /**
   * AI tab — quick connect for the primary "happy path" providers.
   *
   * Mirrors the ConnectAiPopover logic exactly so the user gets the same
   * behavior whether they click the sidebar pill or open the AI tab in
   * Settings. The advanced section below this card still exposes every
   * preset, custom endpoints, and the model picker for power users.
   */
  const handleQuickConnect = () => {
    const isOllama = quickProvider === 'ollama';
    const trimmed = quickKey.trim();
    if (!isOllama && !trimmed) {
      toast.error('Paste an API key first.');
      return;
    }

    const preset = presets?.find((item) => item.name === quickProvider);
    if (!preset) {
      toast.error('Provider preset is unavailable.');
      return;
    }

    const config = isOllama
      ? {
          provider: quickProvider,
          base_url: 'http://localhost:11434/v1',
          api_key: 'ollama',
          model: ollamaDetect?.recommended_model || 'llama3.1',
        }
      : { provider: quickProvider, base_url: preset.base_url, api_key: trimmed, model: preset.model };

    updateLLM.mutate(config, {
      onSuccess: () => {
        testConnection.mutate(undefined, {
          onSuccess: (result) => {
            if (result.success) {
              toast.success(`Connected to ${result.provider || quickProvider}`);
              setQuickKey('');
            } else {
              toast.error(result.message || 'Connection failed — check your key');
            }
          },
          onError: (error) =>
            toast.error(error instanceof Error ? error.message : 'Connection test failed'),
        });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Failed to save provider settings'),
    });
  };

  // Group presets for card display — order by tier with free first
  const PROVIDER_ORDER = ['gemini', 'groq', 'cerebras', 'openrouter', 'mistral', 'sambanova', 'deepseek', 'openai-api', 'anthropic-api', 'ollama'];
  const userPresets = PROVIDER_ORDER
    .map((name) => presets?.find((p) => p.name === name))
    .filter((p): p is NonNullable<typeof p> => !!p && !p.internal && !!PROVIDER_INFO[p.name]);
  const popularPresets = getPopularProviderPresets(userPresets, hostedMode);
  const advancedPresets = userPresets.filter((p) => !isPopularProvider(p.name, hostedMode));
  const devPresets = presets?.filter((p) => p.internal) || [];

  // Hosted: AI is platform-managed by the operator's server key. End users
  // can't (and shouldn't) set a provider key here — saving one 403s. So show
  // a managed status and nothing to configure. The paste-a-key UI below is
  // only ever for the self-host / desktop operator.
  if (hostedMode) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            AI for ranking and drafting
          </CardTitle>
        </CardHeader>
        <CardContent>
          {llm?.available ? (
            <div className="rounded-xl border border-success/20 bg-success/5 p-4">
              <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                <CheckCircle2 className="h-4 w-4" />
                AI is on
              </span>
              <p className="mt-1 text-sm text-text-secondary">
                Managed by Questboard. Your resume is ranked automatically, nothing to set up.
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
              <p className="text-sm text-text-secondary">
                AI ranking is managed by Questboard. Nothing to set up here.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    );
  }

  return (
    <>
    {/* Primary card — uses the unified diagnostic modal for connect/switch/fix. */}
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            AI for ranking and drafting
          </CardTitle>
          {!llm?.available && (
            <p className="text-sm text-text-tertiary">
              ChatGPT and Claude subscriptions don't work here. Get a free key below.
            </p>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Connected status */}
        {llm?.available && (
          <div className="rounded-xl border border-success/20 bg-success/5 p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                  <CheckCircle2 className="h-4 w-4" />
                  AI is connected
                </span>
                <p className="mt-1 text-sm font-medium text-text-primary">{getConnectedLabel(llm)}</p>
                {llm.model && (
                  <p className="text-xs text-text-muted">{formatModelLabel(llm.model)}</p>
                )}
              </div>
            </div>
            {llm?.auto_detected === 'ollama' && (
              <p className="mt-1 text-xs text-text-muted">Auto-detected from your local Ollama installation.</p>
            )}
          </div>
        )}

        {/* Not connected — quick connect form mirrors the popover */}
        {!llm?.available && (
          <div className="space-y-3">
            {/* Provider tabs */}
            <div
              role="tablist"
              aria-label="AI provider"
              className="flex gap-1 rounded-lg border border-border-default bg-bg-subtle p-0.5"
            >
              {(['groq', 'gemini', 'openai-api', 'anthropic-api', 'ollama'] as const)
                .filter((name) => !hostedMode || name !== 'ollama')
                .map((name) => {
                  const active = quickProvider === name;
                  const label =
                    name === 'groq'
                      ? 'Groq'
                      : name === 'gemini'
                        ? 'Gemini'
                        : name === 'openai-api'
                          ? 'ChatGPT'
                          : name === 'anthropic-api'
                            ? 'Claude'
                            : 'Local';
                  return (
                    <button
                      key={name}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      onClick={() => {
                        setQuickProvider(name);
                        setQuickKey('');
                      }}
                      className={cn(
                        'flex-1 rounded-md px-3 py-2 text-xs font-medium transition-colors',
                        active ? 'bg-bg-card text-text-primary shadow-sm' : 'text-text-muted hover:text-text-secondary',
                      )}
                    >
                      {label}
                    </button>
                  );
                })}
            </div>

            {/* Get-key link */}
            <a
              href={
                quickProvider === 'groq'
                  ? 'https://console.groq.com/keys'
                  : quickProvider === 'gemini'
                    ? 'https://aistudio.google.com/apikey'
                    : quickProvider === 'openai-api'
                      ? 'https://platform.openai.com/api-keys'
                      : quickProvider === 'anthropic-api'
                        ? 'https://console.anthropic.com/settings/keys'
                        : 'https://ollama.com/download'
              }
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
            >
              {quickProvider === 'groq'
                ? 'Create a free Groq key'
                : quickProvider === 'gemini'
                  ? 'Create a free Gemini API key'
                  : quickProvider === 'openai-api'
                    ? 'Get an OpenAI API key'
                    : quickProvider === 'anthropic-api'
                      ? 'Get an Anthropic API key'
                      : 'Install Ollama'}
              <ExternalLink className="h-3 w-3" />
            </a>

            {quickProvider === 'groq' && (
              <p className="text-[11px] leading-relaxed text-text-muted">
                Recommended. Free, fast, and Groq does not train on what you send, so your resume stays yours. No credit card.
              </p>
            )}
            {quickProvider === 'gemini' && (
              <p className="text-[11px] leading-relaxed text-text-muted">
                Fine with your own key. Google can use free-tier data to improve its products, so we keep resumes on Groq.
              </p>
            )}

            {/* Paste field or Ollama detection */}
            {quickProvider === 'ollama' ? (
              <div className="rounded-lg border border-border-default bg-bg-subtle/40 px-3 py-2.5 text-xs text-text-muted">
                {ollamaDetect?.detected ? (
                  <span className="inline-flex items-center gap-1.5 font-medium text-success">
                    <Monitor className="h-3.5 w-3.5" />
                    Detected on localhost ({ollamaDetect.recommended_model})
                  </span>
                ) : (
                  <>
                    Install Ollama and run <code className="rounded bg-bg-muted px-1 py-0.5 text-[11px]">ollama pull llama3.2:3b</code>, then click Connect below.
                  </>
                )}
              </div>
            ) : (
              <Input
                type="password"
                placeholder={
                  quickProvider === 'groq'
                    ? 'Paste Groq key'
                    : quickProvider === 'gemini'
                      ? 'Paste Gemini key'
                      : quickProvider === 'openai-api'
                        ? 'Paste OpenAI key'
                        : 'Paste Anthropic key'
                }
                value={quickKey}
                onChange={(event) => setQuickKey(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && quickKey.trim() && !updateLLM.isPending) handleQuickConnect();
                }}
                className="h-9"
              />
            )}

            <Button
              onClick={handleQuickConnect}
              disabled={
                updateLLM.isPending ||
                testConnection.isPending ||
                (quickProvider !== 'ollama' && !quickKey.trim())
              }
              className="w-full"
            >
              {updateLLM.isPending || testConnection.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Connecting…
                </>
              ) : (
                'Connect'
              )}
            </Button>

            <div className="flex items-start gap-1.5 text-[11px] leading-relaxed text-text-muted">
              <Shield className="h-3 w-3 shrink-0 text-success mt-0.5" />
              <p>
                {hostedMode
                  ? 'Your key is encrypted on Questboard and only sent to that provider.'
                  : 'Your key is stored on this computer and only sent to that provider.'}
              </p>
            </div>
          </div>
        )}

        {/* Advanced toggle — keeps the existing 940-line form available
            for power users (custom endpoints, model picker, dev presets,
            advanced free providers like Groq/Cerebras/OpenRouter, etc.)
            without putting it on the page by default. */}
        <div className="border-t border-border-default pt-3">
          <button
            type="button"
            onClick={() => setShowAdvancedAi((v) => !v)}
            className="flex items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-primary"
          >
            <ChevronDown className={cn('h-3 w-3 transition-transform', showAdvancedAi && 'rotate-180')} />
            {showAdvancedAi ? 'Hide advanced provider settings' : 'Show advanced provider settings'}
          </button>
        </div>
      </CardContent>
    </Card>

    {/* Advanced legacy AI card — only renders when explicitly expanded.
        Everything below is the original full-fat provider picker.  */}
    {showAdvancedAi && (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" />
            Advanced AI settings
          </CardTitle>
          <p className="text-sm text-text-tertiary">
            Custom endpoints, model picker, free provider tier (Groq, Cerebras, OpenRouter), and dev presets.
          </p>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {!hostedMode && (
          <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
            <p className="text-sm font-medium text-text-primary">Supported desktop AI paths today</p>
            <p className="mt-1 text-xs leading-relaxed text-text-muted">
              Questboard officially supports provider API keys, Ollama, and your own local OpenAI-compatible endpoint.
              Direct sign-in with your ChatGPT account or Claude account is not available in Questboard yet.
            </p>
          </div>
        )}

        {/* Locked: host configured a provider and disabled runtime editing */}
        {!llm?.runtime_configurable && llm?.configured ? (
          <div className="rounded-xl border border-border-default bg-bg-subtle/50 p-4">
            <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
              <CheckCircle2 className="h-4 w-4" />
              AI is connected
            </span>
            <p className="mt-1 text-sm font-medium text-text-primary">{getConnectedLabel(llm)}</p>
            {llm.model && (
              <p className="text-xs text-text-muted">{formatModelLabel(llm.model)}</p>
            )}
          </div>
        ) : (
          <>
            {/* ── Connected status ────────────────────────────── */}
            {llm?.available && (
              <div className="rounded-xl border border-success/20 bg-success/5 p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                      <CheckCircle2 className="h-4 w-4" />
                      AI connected
                    </span>
                    <p className="mt-1 text-sm font-medium text-text-primary">
                      {getConnectedLabel(llm)}
                    </p>
                    {llm.model && (
                      <p className="text-xs text-text-muted">{formatModelLabel(llm.model)}</p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setShowAllProviders(!showAllProviders)}
                  >
                    Change AI provider
                  </Button>
                </div>
                {llm?.auto_detected === 'ollama' && (
                  <p className="mt-1 text-xs text-text-muted">Auto-detected from your local Ollama installation.</p>
                )}
              </div>
            )}

            {/* ── Quick setup (when NOT configured) ──────────── */}
            {!llm?.configured && (
              <div className="space-y-4">
                {!hostedMode && (ollamaDetect?.detected || (localAI?.servers && localAI.servers.length > 0)) ? (
                  <p className="text-sm text-text-secondary">
                    We found AI running on your machine. Connect it now if you want Questboard to rank by resume fit and draft materials.
                  </p>
                ) : (
                  <p className="text-sm text-text-secondary">
                    Recommended: <strong>Gemini</strong>. You can search without AI, but this is what makes Questboard feel tailored to the user.
                  </p>
                )}

                {/* Option A: Ollama detected (self-hosted only) */}
                {!hostedMode && ollamaDetect?.detected && (
                  <button
                    type="button"
                    onClick={() => {
                      const model = ollamaDetect.recommended_model;
                      updateLLM.mutate(
                        { provider: 'ollama', base_url: 'http://localhost:11434/v1', api_key: 'ollama', model },
                        { onSuccess: () => toast.success(`Connected to Ollama (${model})`) },
                      );
                    }}
                    disabled={updateLLM.isPending}
                    className="w-full rounded-xl border-2 border-success/30 bg-success/5 p-4 text-left transition-all hover:border-success/50 hover:bg-success/10"
                  >
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/10">
                        {updateLLM.isPending ? <Loader2 className="h-5 w-5 animate-spin text-success" /> : <Monitor className="h-5 w-5 text-success" />}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-text-primary">Use Ollama</p>
                          <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Detected</span>
                        </div>
                        <p className="mt-0.5 text-xs text-text-muted">
                          Already running with {ollamaDetect.recommended_model}. Click to connect instantly — no account needed.
                        </p>
                      </div>
                    </div>
                  </button>
                )}

                {/* Option A2: Local AI servers detected on other ports (self-hosted only) */}
                {!hostedMode && localAI?.servers && localAI.servers.length > 0 && (
                  <>
                    {serversIncludeFlagshipModels(localAI.servers) && <FlagshipDetectionWarning />}
                    {localAI.servers.map((server) => (
                      <button
                        key={server.port}
                        type="button"
                        onClick={() => {
                          updateLLM.mutate(
                            { provider: 'custom', base_url: server.base_url, api_key: '', model: server.model },
                            {
                              onSuccess: () => {
                                testConnection.mutate(undefined, {
                                  onSuccess: (r) => r.success
                                    ? toast.success(`Connected · ${server.model}`)
                                    : toast.error(r.message || 'Connection failed'),
                                  onError: () => toast.error('Connection test failed'),
                                });
                              },
                            },
                          );
                        }}
                        disabled={updateLLM.isPending}
                        className="w-full rounded-xl border-2 border-success/30 bg-success/5 p-4 text-left transition-all hover:border-success/50 hover:bg-success/10"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/10">
                            {updateLLM.isPending ? <Loader2 className="h-5 w-5 animate-spin text-success" /> : <Sparkles className="h-5 w-5 text-success" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-semibold text-text-primary">{server.model}</p>
                              <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Detected</span>
                            </div>
                            <p className="mt-0.5 text-xs text-text-muted">
                              Found on port {server.port}. Click to connect.
                            </p>
                          </div>
                        </div>
                      </button>
                    ))}
                  </>
                )}

                <div className="space-y-2">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Popular choices</p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {popularPresets.map((preset) => {
                      const info = POPULAR_PROVIDER_CHOICES[preset.name as keyof typeof POPULAR_PROVIDER_CHOICES];
                      if (!info) return null;
                      const selected = llmForm.provider === preset.name;
                      return (
                        <button
                          key={preset.name}
                          type="button"
                          onClick={() => {
                            selectProvider(preset.name);
                            if (preset.name === 'ollama') {
                              setShowAllProviders(true);
                            } else {
                              setShowAllProviders(false);
                            }
                          }}
                          className={cn(
                            'rounded-xl border px-4 py-3 text-left transition-all',
                            selected
                              ? 'border-brand bg-brand-light/40 ring-1 ring-brand/20'
                              : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                          )}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{info.title}</span>
                            <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0', info.badgeClassName)}>{info.badge}</span>
                          </div>
                          <p className="mt-1 text-xs text-text-muted">{info.description}</p>
                          <p className="mt-1 text-[11px] text-text-tertiary">{info.detail}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Recommended default: Gemini inline setup */}
                {(llmForm.provider === 'gemini' || !llmForm.provider) && (
                <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                      <Sparkles className="h-5 w-5 text-brand" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold text-text-primary">Google Gemini</p>
                        <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Free</span>
                        <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand uppercase">Recommended</span>
                      </div>
                      <p className="mt-0.5 text-xs text-text-muted">Fastest low-cost setup. Free tier available, but you still need a free Gemini API key.</p>
                    </div>
                  </div>
                  <div className="space-y-2.5 pl-[52px]">
                    <div className="flex items-start gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                      <div>
                        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
                          Create a free Gemini API key <ExternalLink className="h-3 w-3" />
                        </a>
                        <p className="text-[11px] text-text-muted mt-0.5">Sign in to Google AI Studio, click "Create API key", then paste it here.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                      <div className="flex-1 flex gap-2">
                        <Input
                          type="password"
                          placeholder="Paste your key here"
                          value={geminiKey}
                          onChange={(e) => setGeminiKey(e.target.value)}
                          className="h-8 text-sm"
                        />
                        <Button
                          size="sm"
                          className="h-8 shrink-0"
                          onClick={() => {
                            if (!geminiKey.trim()) return;
                            updateLLM.mutate(
                              { provider: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', api_key: geminiKey.trim(), model: 'gemini-2.5-flash' },
                              {
                                onSuccess: () => {
                                  testConnection.mutate(undefined, {
                                    onSuccess: (r) => r.success ? toast.success('Connected to Gemini') : toast.error(r.message || 'Check your API key'),
                                    onError: () => toast.error('Connection test failed'),
                                  });
                                },
                              },
                            );
                          }}
                          disabled={!geminiKey.trim() || updateLLM.isPending || testConnection.isPending}
                        >
                          {updateLLM.isPending || testConnection.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Connect'}
                        </Button>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 pl-[52px]">
                    <Shield className="h-3 w-3 text-success shrink-0 mt-0.5" />
                    <p className="text-[10px] text-text-muted leading-relaxed">
                      {hostedMode
                        ? 'Your key is sent to Questboard over HTTPS, stored encrypted for your workspace, and used only to call Google.'
                        : `Your key stays on your ${llm?.key_storage === 'keychain' ? 'OS keychain' : 'computer'} and is only sent to Google.`}
                    </p>
                  </div>
                </div>
                )}

                {!showAllProviders && (llmForm.provider === 'openai-api' || llmForm.provider === 'anthropic-api') && (
                  <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                        <Sparkles className="h-5 w-5 text-brand" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-text-primary">
                            {llmForm.provider === 'openai-api' ? 'ChatGPT by OpenAI' : 'Claude by Anthropic'}
                          </p>
                          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-600 uppercase">
                            API key
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs text-text-muted">
                          {llmForm.provider === 'openai-api'
                            ? 'Paste your OpenAI API key to use GPT models in Questboard.'
                            : 'Paste your Anthropic API key to use Claude models in Questboard.'}
                        </p>
                      </div>
                    </div>
                    <div className="space-y-2.5 pl-[52px]">
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                        <div>
                          <a
                            href={providerInfo?.keyUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-sm text-brand hover:underline"
                          >
                            {providerInfo?.keyLabel || 'Get your API key'} <ExternalLink className="h-3 w-3" />
                          </a>
                          <p className="text-[11px] text-text-muted mt-0.5">
                            Create a key with that provider, then paste it here.
                          </p>
                        </div>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                        <div className="flex-1 flex gap-2">
                          <Input
                            type="password"
                            placeholder={llmForm.provider === 'openai-api' ? 'Paste your OpenAI API key' : 'Paste your Anthropic API key'}
                            value={llmForm.api_key}
                            onChange={(event) => setLlmForm((prev) => ({ ...prev, api_key: event.target.value }))}
                            className="h-8 text-sm"
                          />
                          <Button
                            size="sm"
                            className="h-8 shrink-0"
                            onClick={handleSaveLLM}
                            disabled={!llmForm.api_key.trim() || updateLLM.isPending || testConnection.isPending}
                          >
                            {updateLLM.isPending || testConnection.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Connect'}
                          </Button>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-start gap-2 pl-[52px]">
                      <Shield className="h-3 w-3 text-success shrink-0 mt-0.5" />
                      <p className="text-[10px] text-text-muted leading-relaxed">
                        {hostedMode
                          ? 'Your key is sent to Questboard over HTTPS, stored encrypted for your workspace, and used only to call that provider.'
                          : 'Your key is stored locally and sent only to that provider.'}
                      </p>
                    </div>
                  </div>
                )}

                <details className="rounded-xl border border-border-default bg-bg-subtle/30 p-4">
                  <summary className="flex cursor-pointer items-center gap-2 text-sm text-text-secondary hover:text-text-primary">
                    <HelpCircle className="h-4 w-4 text-text-muted" />
                    Why does this need an API key?
                  </summary>
                  <p className="mt-3 text-xs text-text-muted leading-relaxed">
                    ChatGPT Plus and Claude Pro/Max are chat subscriptions, not direct Questboard access today. For now,
                    Questboard officially supports provider API keys, Ollama, and your own local OpenAI-compatible endpoint.
                    If you want the easiest low-cost path, Gemini is still the simplest starting point.
                  </p>
                </details>

                <button
                  type="button"
                  onClick={() => setShowAllProviders(!showAllProviders)}
                  className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary"
                >
                  <ChevronDown className={cn('h-3 w-3 transition-transform', showAllProviders && 'rotate-180')} />
                  {showAllProviders ? 'Hide' : 'Show'} more AI options
                </button>
              </div>
            )}

            {/* ── AI not available — show reconnect options ──── */}
            {llm?.configured && !llm?.available && !showAllProviders && (
              <div className="space-y-4">
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950/30">
                  <p className="text-sm font-medium text-amber-800 dark:text-amber-200">
                    AI is offline
                  </p>
                  <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                    {llm.provider === 'ollama'
                      ? 'Your local AI server isn\'t responding. You can switch to a free cloud option below.'
                      : 'Can\'t reach your AI provider. Check your connection or switch to another option.'}
                  </p>
                </div>

                {/* Auto-detected local servers (self-hosted only) */}
                {!hostedMode && localAI?.servers && localAI.servers.length > 0 && (
                  <>
                    {serversIncludeFlagshipModels(localAI.servers) && <FlagshipDetectionWarning />}
                    {localAI.servers.map((server) => (
                      <button
                        key={server.port}
                        type="button"
                        onClick={() => {
                          updateLLM.mutate(
                            { provider: 'custom', base_url: server.base_url, api_key: '', model: server.model },
                            {
                              onSuccess: () => {
                                testConnection.mutate(undefined, {
                                  onSuccess: (r) => r.success
                                    ? toast.success(`Connected · ${server.model}`)
                                    : toast.error(r.message || 'Connection failed'),
                                  onError: () => toast.error('Connection test failed'),
                                });
                              },
                            },
                          );
                        }}
                        disabled={updateLLM.isPending}
                        className="w-full rounded-xl border-2 border-success/30 bg-success/5 p-4 text-left transition-all hover:border-success/50 hover:bg-success/10"
                      >
                        <div className="flex items-center gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/10">
                            {updateLLM.isPending ? <Loader2 className="h-5 w-5 animate-spin text-success" /> : <Sparkles className="h-5 w-5 text-success" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <p className="text-sm font-semibold text-text-primary">{server.model}</p>
                              <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Detected</span>
                            </div>
                            <p className="mt-0.5 text-xs text-text-muted">
                              Found on port {server.port}. Click to connect.
                            </p>
                          </div>
                        </div>
                      </button>
                    ))}
                  </>
                )}

                {/* Gemini quick-setup as fallback */}
                <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                      <Sparkles className="h-5 w-5 text-brand" />
                    </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-text-primary">Switch to Google Gemini</p>
                          <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Free</span>
                        </div>
                      <p className="mt-0.5 text-xs text-text-muted">Fastest way to add AI again without paying for user usage.</p>
                    </div>
                  </div>
                  <div className="space-y-2.5 pl-[52px]">
                    <div className="flex items-start gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                      <div>
                        <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
                          Get your free key from Google <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                    <div className="flex items-start gap-2">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                      <div className="flex-1 flex gap-2">
                        <Input
                          type="password"
                          placeholder="Paste your key here"
                          value={geminiKey}
                          onChange={(e) => setGeminiKey(e.target.value)}
                          className="h-8 text-sm"
                        />
                        <Button
                          size="sm"
                          className="h-8 shrink-0"
                          onClick={() => {
                            if (!geminiKey.trim()) return;
                            updateLLM.mutate(
                              { provider: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', api_key: geminiKey.trim(), model: 'gemini-2.5-flash' },
                              {
                                onSuccess: () => {
                                  testConnection.mutate(undefined, {
                                    onSuccess: (r) => r.success ? toast.success('Connected to Gemini') : toast.error(r.message || 'Check your key'),
                                    onError: () => toast.error('Connection test failed'),
                                  });
                                },
                              },
                            );
                          }}
                          disabled={!geminiKey.trim() || updateLLM.isPending || testConnection.isPending}
                        >
                          {updateLLM.isPending || testConnection.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : 'Connect'}
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => setShowAllProviders(true)}
                  className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary"
                >
                  <ChevronDown className="h-3 w-3" />
                  Show advanced AI options
                </button>
              </div>
            )}

            {/* ── Full provider grid (collapsed by default) ──── */}
            {showAllProviders && (
              <div className="space-y-4">
                {llm?.configured && !showAllProviders && (
                  <p className="text-sm text-text-tertiary">
                    Switch to a different AI provider.
                  </p>
                )}

                {llm?.configured && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Popular choices</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {popularPresets.map((preset) => {
                        const info = POPULAR_PROVIDER_CHOICES[preset.name as keyof typeof POPULAR_PROVIDER_CHOICES];
                        if (!info) return null;
                        const selected = llmForm.provider === preset.name;
                        return (
                          <button
                            key={preset.name}
                            type="button"
                            onClick={() => selectProvider(preset.name)}
                            className={cn(
                              'rounded-xl border px-4 py-3 text-left transition-all',
                              selected
                                ? 'border-brand bg-brand-light/40 ring-1 ring-brand/20'
                                : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{info.title}</span>
                              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0', info.badgeClassName)}>{info.badge}</span>
                            </div>
                            <p className="mt-1 text-xs text-text-muted">{info.description}</p>
                            <p className="mt-1 text-[11px] text-text-tertiary">{info.detail}</p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {advancedPresets.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Advanced providers</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {advancedPresets.map((preset) => {
                        const info = PROVIDER_INFO[preset.name];
                        if (!info) return null;
                        const selected = llmForm.provider === preset.name;
                        return (
                          <button
                            key={preset.name}
                            type="button"
                            onClick={() => selectProvider(preset.name)}
                            className={cn(
                              'rounded-xl border px-4 py-3 text-left transition-all',
                              selected
                                ? 'border-brand bg-brand-light/40 ring-1 ring-brand/20'
                                : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{preset.label}</span>
                              <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0', info.badgeColor)}>{info.badge}</span>
                            </div>
                            <p className="mt-1 text-xs text-text-muted">{info.description}</p>
                          </button>
                        );
                      })}
                    </div>
                    <p className="text-[11px] text-text-muted">
                      Use these only if you already know which provider you want. Most people should stick to Gemini, ChatGPT by OpenAI, Claude by Anthropic, or Local / private.
                    </p>
                  </div>
                )}

                {/* Dev presets (self-hosted only) */}
                {!hostedMode && devPresets.length > 0 && isDevMode() && (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-text-muted uppercase tracking-wide">Developer proxies</p>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {devPresets.map((preset) => {
                        const selected = llmForm.provider === preset.name;
                        return (
                          <button
                            key={preset.name}
                            type="button"
                            onClick={() => selectProvider(preset.name)}
                            className={cn(
                              'rounded-xl border border-dashed px-4 py-3 text-left transition-all',
                              selected ? 'border-brand bg-brand-light/40' : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                            )}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{preset.label}</span>
                              <span className="rounded-full bg-bg-subtle px-2 py-0.5 text-[10px] font-medium text-text-muted">Dev</span>
                            </div>
                            <p className="mt-1 text-xs text-text-muted">Developer proxy (localhost only)</p>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Custom Provider — self-hosted only (backend can't reach localhost URLs when hosted) */}
                {!hostedMode && <div className="space-y-2">
                  <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Custom Provider</p>
                  <button
                    type="button"
                    onClick={() => {
                      setLlmForm((prev) => ({
                        ...prev,
                        provider: 'custom',
                        base_url: prev.base_url || '',
                        model: prev.model || '',
                      }));
                    }}
                    className={cn(
                      'w-full rounded-xl border px-4 py-3 text-left transition-all',
                      llmForm.provider === 'custom'
                        ? 'border-brand bg-brand-light/40 ring-1 ring-brand/20'
                        : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className={cn('text-sm font-medium', llmForm.provider === 'custom' ? 'text-brand' : 'text-text-primary')}>Custom Provider</span>
                      <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-medium text-brand">Compatible</span>
                    </div>
                    <p className="mt-1 text-xs text-text-muted">Connect your own AI model or server</p>
                  </button>
                </div>}

                {/* Setup panel for selected provider */}
                {llmForm.provider && (
                  <div className="space-y-4 rounded-xl border border-brand/20 bg-brand-light/10 p-4">
                    <p className="text-sm font-medium text-text-primary">
                      {llmForm.provider === 'custom'
                        ? 'Connect to your AI server'
                        : llmForm.provider === 'openai-api'
                          ? 'Use ChatGPT by OpenAI'
                          : llmForm.provider === 'anthropic-api'
                            ? 'Use Claude by Anthropic'
                            : llmForm.provider === 'gemini'
                              ? 'Use Gemini with your Gemini API key'
                              : `Set up ${selectedPreset?.label || llmForm.provider}`}
                    </p>

                    {llmForm.provider === 'custom' ? (
                      <div className="space-y-3">
                        {/* Auto-detected servers — click to connect */}
                        {localAI?.servers && localAI.servers.length > 0 && (
                          <div className="space-y-2">
                            {serversIncludeFlagshipModels(localAI.servers) && <FlagshipDetectionWarning />}
                            <p className="text-xs font-medium text-text-secondary">Detected on your machine:</p>
                            <div className="grid gap-2">
                              {localAI.servers.map((server) => {
                                const isSelected = llmForm.base_url === server.base_url;
                                return (
                                  <button
                                    key={server.port}
                                    type="button"
                                    onClick={() => setLlmForm((prev) => ({ ...prev, base_url: server.base_url, model: server.model }))}
                                    className={cn(
                                      'w-full rounded-lg border px-3 py-2.5 text-left transition-all',
                                      isSelected
                                        ? 'border-success bg-success/5 ring-1 ring-success/20'
                                        : 'border-border-default bg-bg-card hover:border-success/40 hover:bg-success/5',
                                    )}
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
                                        <span className="text-sm font-medium text-text-primary">{server.model}</span>
                                        <span className="text-xs text-text-muted">port {server.port}</span>
                                      </div>
                                      {isSelected
                                        ? <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">Selected</span>
                                        : <span className="text-xs text-text-muted">Click to use</span>
                                      }
                                    </div>
                                    {isSelected && server.models.length > 1 && (
                                      <div className="mt-2 flex flex-wrap gap-1">
                                        {server.models.map((m) => (
                                          <button
                                            key={m}
                                            type="button"
                                            onClick={(e) => { e.stopPropagation(); setLlmForm((prev) => ({ ...prev, model: m })); }}
                                            className={cn(
                                              'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                                              llmForm.model === m
                                                ? 'border-brand bg-brand-light/40 text-brand font-medium'
                                                : 'border-border-default text-text-secondary hover:bg-bg-subtle hover:border-brand/40',
                                            )}
                                          >
                                            {m}
                                          </button>
                                        ))}
                                      </div>
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Ollama detected but not in localAI list */}
                        {ollamaDetect?.detected && !(localAI?.servers?.some((s) => s.port === 11434)) && (
                          <button
                            type="button"
                            onClick={() => setLlmForm((prev) => ({ ...prev, base_url: 'http://localhost:11434/v1', model: ollamaDetect.recommended_model }))}
                            className={cn(
                              'w-full rounded-lg border px-3 py-2.5 text-left transition-all',
                              llmForm.base_url === 'http://localhost:11434/v1'
                                ? 'border-success bg-success/5 ring-1 ring-success/20'
                                : 'border-border-default bg-bg-card hover:border-success/40 hover:bg-success/5',
                            )}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
                                <span className="text-sm font-medium text-text-primary">Ollama · {ollamaDetect.recommended_model}</span>
                              </div>
                              <span className="text-xs text-text-muted">Click to use</span>
                            </div>
                          </button>
                        )}

                        {/* Manual entry — collapsed if servers were detected */}
                        {localAI?.servers && localAI.servers.length > 0 ? (
                          <details className="group">
                            <summary className="cursor-pointer text-xs text-text-muted hover:text-text-secondary">
                              Enter a URL manually instead
                            </summary>
                            <div className="mt-2 space-y-2">
                              <div className="space-y-1.5">
                                <Label className="text-xs">Base URL</Label>
                                <Input
                                  className="h-8 text-xs"
                                  placeholder="http://localhost:8317/v1"
                                  value={llmForm.base_url}
                                  onChange={(event) => setLlmForm((prev) => ({ ...prev, base_url: event.target.value }))}
                                />
                              </div>
                              <div className="space-y-1.5">
                                <Label className="text-xs">Model</Label>
                                <Input
                                  className="h-8 text-xs"
                                  placeholder="Model name from your server"
                                  value={llmForm.model}
                                  onChange={(event) => setLlmForm((prev) => ({ ...prev, model: event.target.value }))}
                                />
                              </div>
                            </div>
                          </details>
                        ) : (
                          <>
                            <div className="space-y-1.5">
                              <Label className="text-sm">Base URL</Label>
                              <Input
                                placeholder="http://localhost:8317/v1"
                                value={llmForm.base_url}
                                onChange={(event) => setLlmForm((prev) => ({ ...prev, base_url: event.target.value }))}
                              />
                              <p className="text-xs text-text-muted">
                                No servers detected. Start your AI server, then reopen this page — or paste the URL manually.
                              </p>
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-sm">Model</Label>
                              <Input
                                placeholder={liveModels && liveModels.length > 0 ? liveModels[0].id : 'Enter a base URL first — models will appear here'}
                                value={llmForm.model}
                                onChange={(event) => setLlmForm((prev) => ({ ...prev, model: event.target.value }))}
                              />
                              {isFetchingModels && <p className="text-[11px] text-text-muted animate-pulse">Fetching models from your server...</p>}
                              {!isFetchingModels && liveModels && liveModels.length > 0 && (
                                <div className="space-y-1">
                                  <p className="text-[11px] text-text-muted">Available models — click to select:</p>
                                  <div className="flex flex-wrap gap-1">
                                    {liveModels.slice(0, 10).map((model) => (
                                      <button
                                        key={model.id}
                                        type="button"
                                        onClick={() => setLlmForm((prev) => ({ ...prev, model: model.id }))}
                                        className={cn(
                                          'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                                          llmForm.model === model.id
                                            ? 'border-brand bg-brand-light/40 text-brand font-medium'
                                            : 'border-border-default text-text-secondary hover:bg-bg-subtle hover:border-brand/40',
                                        )}
                                      >
                                        {model.id}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}
                              {!isFetchingModels && llmForm.base_url && (!liveModels || liveModels.length === 0) && (
                                <p className="text-[11px] text-text-muted">Couldn't fetch models — type the model name manually.</p>
                              )}
                            </div>
                          </>
                        )}

                        <div className="space-y-1.5">
                          <Label className="text-sm">API key <span className="font-normal text-text-muted">(optional)</span></Label>
                          <Input
                            type="password"
                            placeholder="Leave blank if not needed"
                            value={llmForm.api_key}
                            onChange={(event) => setLlmForm((prev) => ({ ...prev, api_key: event.target.value }))}
                          />
                        </div>
                      </div>
                    ) : selectedPreset?.needs_api_key ? (
                      <div className="space-y-3">
                        {providerInfo?.keyUrl && (
                          <div className="flex items-start gap-3">
                            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">1</span>
                            <div>
                              <a href={providerInfo.keyUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline">
                                {providerInfo.keyLabel || 'Get your API key'} <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                              <p className="text-xs text-text-muted mt-0.5">
                                {llmForm.provider === 'gemini'
                                  ? 'Google gives new users a free Gemini key in AI Studio. Create it there, then paste it here.'
                                  : 'Create an API key with that provider, then paste it here.'}
                              </p>
                            </div>
                          </div>
                        )}
                        <div className="flex items-start gap-3">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">{providerInfo?.keyUrl ? '2' : '1'}</span>
                          <div className="flex-1 space-y-1.5">
                            <Label className="text-sm">Paste your key here</Label>
                            <Input
                              type="password"
                              placeholder={
                                llmForm.provider === 'openai-api'
                                  ? 'Paste your OpenAI API key'
                                  : llmForm.provider === 'anthropic-api'
                                    ? 'Paste your Anthropic API key'
                                    : llmForm.provider === 'gemini'
                                      ? 'Paste your Gemini API key'
                                      : `Paste the key you copied from ${selectedPreset?.label || 'the provider'}`
                              }
                              value={llmForm.api_key}
                              onChange={(event) => setLlmForm((prev) => ({ ...prev, api_key: event.target.value }))}
                            />
                          </div>
                        </div>
                        <div className="flex items-start gap-2 rounded-lg bg-bg-subtle/60 px-3 py-2">
                          <Shield className="h-3.5 w-3.5 text-success shrink-0 mt-0.5" />
                          <p className="text-[11px] text-text-muted leading-relaxed">
                            {hostedMode
                              ? `Your key is sent to Questboard over HTTPS, stored encrypted for your workspace, and used only to call ${selectedPreset?.label || 'that provider'}.`
                              : llm?.key_storage === 'keychain'
                                ? `Your key is stored in your OS keychain and sent only to ${selectedPreset?.label || 'the provider'}. It never touches disk as plaintext.`
                                : `Your key is stored locally and sent only to ${selectedPreset?.label || 'the provider'}'s API.`}
                          </p>
                        </div>
                      </div>
                    ) : liveModels && liveModels.length > 0 ? (
                      // Subscription proxy (claude-proxy, openai-proxy, ...) OR a
                      // running Ollama: the endpoint exposes /v1/models, so render
                      // the chip picker directly instead of generic install steps.
                      <div className="space-y-2">
                        <Label className="text-sm">Model</Label>
                        <p className="text-[11px] text-text-muted">
                          {selectedPreset?.label || 'Your endpoint'} exposes {liveModels.length} models — click to select:
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {liveModels.slice(0, 20).map((model) => (
                            <button
                              key={model.id}
                              type="button"
                              onClick={() => setLlmForm((prev) => ({ ...prev, model: model.id }))}
                              className={cn(
                                'rounded-full border px-2 py-0.5 text-[11px] transition-colors',
                                llmForm.model === model.id
                                  ? 'border-brand bg-brand-light/40 text-brand font-medium'
                                  : 'border-border-default text-text-secondary hover:bg-bg-subtle hover:border-brand/40',
                              )}
                            >
                              {model.id}
                            </button>
                          ))}
                        </div>
                        {isFetchingModels && (
                          <p className="text-[11px] text-text-muted animate-pulse">Refreshing model list…</p>
                        )}
                      </div>
                    ) : (
                      <div className="space-y-3">
                        <div className="flex items-start gap-3">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">1</span>
                          <div>
                            <a href="https://ollama.com" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline">
                              Install Ollama (free) <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                            <p className="text-xs text-text-muted mt-0.5">Download and install — takes about 2 minutes</p>
                          </div>
                        </div>
                        <div className="flex items-start gap-3">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">2</span>
                          <div>
                            <p className="text-sm font-medium text-text-primary">Pull a model</p>
                            <code className="mt-1 block rounded bg-bg-subtle px-2 py-1 text-xs text-text-secondary">ollama pull llama3.2:3b</code>
                          </div>
                        </div>
                        <div className="flex items-start gap-3">
                          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">3</span>
                          <p className="text-sm text-text-muted">Click Save below — Questboard connects automatically</p>
                        </div>
                      </div>
                    )}

                    {/* Dev-mode: model + base URL override */}
                    {isDevMode() && (
                      <>
                        <button
                          type="button"
                          onClick={() => setShowDevFields(!showDevFields)}
                          className="flex items-center gap-1 text-xs text-text-muted hover:text-text-secondary"
                        >
                          <ChevronDown className={cn('h-3 w-3 transition-transform', showDevFields && 'rotate-180')} />
                          Model & endpoint override
                        </button>
                        {showDevFields && (
                          <div className="grid gap-3 sm:grid-cols-2">
                            <div className="space-y-1.5">
                              <Label className="text-xs">Model</Label>
                              <Input className="h-8 text-xs" value={llmForm.model} onChange={(event) => setLlmForm((prev) => ({ ...prev, model: event.target.value }))} />
                              {isFetchingModels && <p className="text-[11px] text-text-muted">Loading models...</p>}
                              {!isFetchingModels && liveModels && liveModels.length > 0 && (
                                <div className="flex flex-wrap gap-1">
                                  {liveModels.slice(0, 5).map((model) => (
                                    <button key={model.id} type="button" onClick={() => setLlmForm((prev) => ({ ...prev, model: model.id }))} className="rounded-full border border-border-default px-2 py-0.5 text-[10px] text-text-secondary hover:bg-bg-subtle">
                                      {model.id}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                            <div className="space-y-1.5">
                              <Label className="text-xs">Base URL</Label>
                              <Input className="h-8 text-xs" value={llmForm.base_url} onChange={(event) => setLlmForm((prev) => ({ ...prev, base_url: event.target.value }))} />
                            </div>
                          </div>
                        )}
                      </>
                    )}

                    <div className="flex items-center gap-3">
                      <Button
                        onClick={handleSaveLLM}
                        disabled={
                          !llmForm.provider
                          || (llmForm.provider === 'custom' && (!llmForm.base_url || !llmForm.model))
                          || (llmForm.provider !== 'custom' && selectedPreset?.needs_api_key && !llmForm.api_key)
                          || updateLLM.isPending
                          || testConnection.isPending
                        }
                      >
                        {updateLLM.isPending || testConnection.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                        Save and test connection
                      </Button>
                      {llmForm.provider === 'custom' && (!llmForm.base_url || !llmForm.model) && (
                        <p className="text-xs text-text-muted">Enter a base URL and model</p>
                      )}
                      {llmForm.provider !== 'custom' && selectedPreset?.needs_api_key && !llmForm.api_key && (
                        <p className="text-xs text-text-muted">Paste an API key first</p>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
    )}
    </>
  );
}
