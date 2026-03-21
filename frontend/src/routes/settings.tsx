import { useEffect, useRef, useState } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import {
  CheckCircle2,
  ChevronDown,
  ExternalLink,
  FileText,
  HelpCircle,
  Loader2,
  Monitor,
  Rocket,
  Search,
  Shield,
  Sparkles,
  Upload,
} from 'lucide-react';

import { PageHeader } from '@/components/layout/page-header';
import { LocationListInput } from '@/components/shared/location-list-input';
import { TagListInput } from '@/components/shared/tag-list-input';
import { WorkplacePreferenceSelector } from '@/components/shared/workplace-preference-selector';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useLLMStatus, useLLMPresets, useProviderModels, useDetectOllama, useDetectLocalAI, useTestConnection, useUpdateLLM } from '@/hooks/use-settings';
import { useOnboardingState, useSaveWorkspacePreferences, useUploadWorkspaceResume } from '@/hooks/use-workspace';
import { useWorkspace } from '@/contexts/workspace-context';
import { buildDefaultWorkspacePreferences, LEVEL_OPTIONS } from '@/lib/profile-preferences';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { LLMConfig } from '@/types/settings';
import type { WorkspacePreferences } from '@/types/workspace';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsPage,
});

// ── Provider metadata for cards ──────────────────────────────────────
// Maps backend preset names to user-friendly descriptions and key URLs.
const PROVIDER_INFO: Record<string, { description: string; keyUrl?: string; keyLabel?: string; badge: string; badgeColor: string; recommended?: boolean }> = {
  gemini:         { description: 'Best free AI — 250 uses/day, no credit card', keyUrl: 'https://aistudio.google.com', keyLabel: 'Get free key from Google', badge: 'Free', badgeColor: 'text-emerald-600 bg-emerald-500/10', recommended: true },
  groq:           { description: 'Very fast — 1,000 uses/day', keyUrl: 'https://console.groq.com/keys', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-emerald-600 bg-emerald-500/10' },
  cerebras:       { description: 'Ultra-fast — generous free tier', keyUrl: 'https://cloud.cerebras.ai', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-emerald-600 bg-emerald-500/10' },
  openrouter:     { description: '29 free AI models through one key — 200 uses/day', keyUrl: 'https://openrouter.ai/keys', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-emerald-600 bg-emerald-500/10' },
  mistral:        { description: 'European AI provider — generous free tier', keyUrl: 'https://console.mistral.ai/api-keys', keyLabel: 'Get free key', badge: 'Free', badgeColor: 'text-emerald-600 bg-emerald-500/10' },
  sambanova:      { description: 'Powerful AI — $5 free trial credits', keyUrl: 'https://cloud.sambanova.ai', keyLabel: 'Get free key', badge: 'Trial', badgeColor: 'text-amber-600 bg-amber-500/10' },
  deepseek:       { description: 'Strong AI — free signup bonus, then very cheap', keyUrl: 'https://platform.deepseek.com/api_keys', keyLabel: 'Get key', badge: 'Trial + cheap', badgeColor: 'text-amber-600 bg-amber-500/10' },
  'openai-api':   { description: 'GPT-4o and other OpenAI models (separate from ChatGPT Plus)', keyUrl: 'https://platform.openai.com/api-keys', keyLabel: 'Get API key', badge: 'Paid', badgeColor: 'text-amber-600 bg-amber-500/10' },
  'anthropic-api': { description: 'Claude models (separate from Claude Pro subscription)', keyUrl: 'https://console.anthropic.com/settings/keys', keyLabel: 'Get API key', badge: 'Paid', badgeColor: 'text-amber-600 bg-amber-500/10' },
  ollama:         { description: 'Runs on your computer — completely private, no account needed', keyUrl: 'https://ollama.com', keyLabel: 'Install Ollama (free)', badge: 'No account', badgeColor: 'text-blue-600 bg-blue-500/10' },
  custom:         { description: 'Connect your own AI model or server', badge: 'Custom', badgeColor: 'text-violet-600 bg-violet-500/10' },
};

/** Dev mode shows proxy/internal presets — requires explicit opt-in via localStorage */
function isDevMode(): boolean {
  try {
    return localStorage.getItem('launchboard-dev-mode') === 'true';
  } catch { return false; }
}

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'INR', 'JPY', 'SGD'];
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$', EUR: '\u20AC', GBP: '\u00A3', CAD: 'C$', AUD: 'A$', INR: '\u20B9', JPY: '\u00A5', SGD: 'S$',
};

function SettingsPage() {
  const navigate = useNavigate();
  const { hostedMode } = useWorkspace();
  const { data: llm } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();
  const { data: onboarding } = useOnboardingState();
  const savePreferences = useSaveWorkspacePreferences();
  const uploadResume = useUploadWorkspaceResume();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [llmForm, setLlmForm] = useState<LLMConfig>({ provider: '', base_url: '', api_key: '', model: '' });
  const [prefsForm, setPrefsForm] = useState<WorkspacePreferences>(buildDefaultWorkspacePreferences());
  const [showDevFields, setShowDevFields] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [autoDetectDismissed, setAutoDetectDismissed] = useState(false);
  const [showAllProviders, setShowAllProviders] = useState(false);
  const [geminiKey, setGeminiKey] = useState('');

  // Detect Ollama and local AI servers when no LLM is configured, AI is offline, or custom provider is selected
  // Only scan localhost in self-hosted mode — hosted backend can't reach user's localhost anyway
  const needsAI = !hostedMode && (!llm?.configured || (llm?.configured && !llm?.available)) && !autoDetectDismissed;
  const customSelected = llmForm.provider === 'custom';
  const { data: ollamaDetect } = useDetectOllama(needsAI);
  const { data: localAI } = useDetectLocalAI(needsAI || (!hostedMode && customSelected));

  useEffect(() => {
    if (llm) {
      const preset = presets?.find((item) => item.name === llm.provider);
      setLlmForm({
        provider: llm.provider,
        base_url: preset?.base_url || '',
        api_key: '',
        model: llm.model,
      });
    }
  }, [llm, presets]);

  useEffect(() => {
    if (onboarding?.preferences) {
      setPrefsForm(onboarding.preferences);
    }
  }, [onboarding]);

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
          onError: () => toast.error('Connection test failed'),
        });
      },
      onError: () => toast.error('Failed to save provider settings'),
    });
  };

  const handleUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(result.resume.parse_status === 'parsed' ? 'Resume uploaded' : 'Resume uploaded with warnings');
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Upload failed'),
    });
  };

  const handleSavePreferences = () => {
    savePreferences.mutate(prefsForm, {
      onSuccess: () => toast.success('Preferences saved', {
        action: { label: 'Start searching', onClick: () => navigate({ to: '/search' }) },
      }),
      onError: () => toast.error('Failed to save preferences'),
    });
  };

  // Group presets for card display — order by tier with free first
  const PROVIDER_ORDER = ['gemini', 'groq', 'cerebras', 'openrouter', 'mistral', 'sambanova', 'deepseek', 'openai-api', 'anthropic-api', 'ollama'];
  const userPresets = PROVIDER_ORDER
    .map((name) => presets?.find((p) => p.name === name))
    .filter((p): p is NonNullable<typeof p> => !!p && !p.internal && !!PROVIDER_INFO[p.name]);
  const freePresets = userPresets.filter((p) => {
    const info = PROVIDER_INFO[p.name];
    return info && info.badge === 'Free';
  });
  const paidPresets = userPresets.filter((p) => {
    const info = PROVIDER_INFO[p.name];
    return info && (info.badge === 'Paid' || info.badge === 'Trial + cheap' || info.badge === 'Trial');
  });
  const localPresets = userPresets.filter((p) => {
    const info = PROVIDER_INFO[p.name];
    return info && info.badge === 'No account';
  });
  const devPresets = presets?.filter((p) => p.internal) || [];

  return (
    <div>
      <PageHeader title="Settings" description="Configure what you're looking for and how Launchboard finds it" />

      <div className="max-w-3xl space-y-6">
        {/* ── Resume ──────────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4" />
              Resume
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
              {onboarding?.resume.exists ? (
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                    <FileText className="h-5 w-5 text-red-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-text-primary">{onboarding.resume.filename}</p>
                    <p className="text-xs text-text-muted">
                      {Math.max(1, Math.round(onboarding.resume.file_size / 1024))} KB · {onboarding.resume.parse_status}
                    </p>
                    {onboarding.resume.parse_warning && (
                      <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">{onboarding.resume.parse_warning}</p>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-text-tertiary">No resume uploaded yet. Upload one to unlock resume-matched scoring.</p>
              )}
            </div>

            <Button variant="outline" onClick={() => fileInputRef.current?.click()} disabled={uploadResume.isPending}>
              {uploadResume.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Upload className="mr-2 h-4 w-4" />}
              {onboarding?.resume.exists ? 'Replace Resume' : 'Upload Resume PDF'}
            </Button>
            <input ref={fileInputRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={handleUpload} />
          </CardContent>
        </Card>

        {/* ── Search Preferences ──────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Search className="h-4 w-4" />
              Search Preferences
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="space-y-1.5">
              <Label>Target roles</Label>
              <TagListInput
                value={prefsForm.roles}
                onChange={(roles) => setPrefsForm((prev) => ({ ...prev, roles }))}
                placeholder="e.g. Your target role — press Enter to add"
                helperText="Type a role and press Enter. Separate multiple with commas."
                emptyText="No target roles added yet."
              />
            </div>

            <div className="space-y-1.5">
              <Label>Keywords</Label>
              <TagListInput
                value={prefsForm.keywords}
                onChange={(keywords) => setPrefsForm((prev) => ({ ...prev, keywords }))}
                placeholder="e.g. A key skill — press Enter to add"
                helperText="Skills or specialties to match against job descriptions."
                emptyText="No keywords added yet."
              />
            </div>

            <div className="space-y-2">
              <Label>Preferred locations</Label>
              <LocationListInput
                value={prefsForm.preferred_places}
                onChange={(preferred_places) => setPrefsForm((prev) => ({ ...prev, preferred_places }))}
                emptyText={prefsForm.workplace_preference === 'remote_only' ? 'Remote-only — no locations needed.' : 'No preferred locations yet.'}
              />
            </div>

            <div className="space-y-2">
              <Label>Workplace type</Label>
              <WorkplacePreferenceSelector
                value={prefsForm.workplace_preference}
                onChange={(workplace_preference) => setPrefsForm((prev) => ({ ...prev, workplace_preference }))}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Minimum salary</Label>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                    {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                  </span>
                  <Input
                    type="number"
                    className="pl-7"
                    value={prefsForm.compensation.min_base ?? ''}
                    onChange={(event) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: { ...prev.compensation, min_base: event.target.value === '' ? null : Number(event.target.value) },
                    }))}
                    placeholder="80,000"
                  />
                </div>
                <p className="text-xs text-text-muted">Jobs below this are filtered out.</p>
              </div>
              <div className="space-y-1.5">
                <Label>Target salary</Label>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                    {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                  </span>
                  <Input
                    type="number"
                    className="pl-7"
                    value={prefsForm.compensation.target_total_comp ?? ''}
                    onChange={(event) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: { ...prev.compensation, target_total_comp: event.target.value === '' ? null : Number(event.target.value) },
                    }))}
                    placeholder="150,000"
                  />
                </div>
                <p className="text-xs text-text-muted">Jobs near or above this score higher.</p>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Posted within</Label>
              <Select value={String(prefsForm.max_days_old)} onValueChange={(value) => setPrefsForm((prev) => ({ ...prev, max_days_old: Number(value) }))}>
                <SelectTrigger className="h-9 w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1">1 day</SelectItem>
                  <SelectItem value="3">3 days</SelectItem>
                  <SelectItem value="7">7 days</SelectItem>
                  <SelectItem value="14">14 days</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* ── Advanced (collapsed by default) ──────────────── */}
            <div className="border-t border-border-default pt-4">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-sm font-medium text-text-secondary hover:text-text-primary"
              >
                <ChevronDown className={cn('h-4 w-4 transition-transform', showAdvanced && 'rotate-180')} />
                Advanced options
              </button>

              {showAdvanced && (
                <div className="mt-4 space-y-5">
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div className="space-y-1.5">
                      <Label>Current title</Label>
                      <Input
                        value={prefsForm.current_title}
                        onChange={(event) => setPrefsForm((prev) => ({ ...prev, current_title: event.target.value }))}
                        placeholder="e.g. Senior Engineer"
                      />
                      <p className="text-xs text-text-muted">Used to score career progression.</p>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Current level</Label>
                      <Select value={prefsForm.current_level} onValueChange={(value) => setPrefsForm((prev) => ({ ...prev, current_level: value }))}>
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {LEVEL_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  <div className="grid gap-4 sm:grid-cols-3">
                    <div className="space-y-1.5">
                      <Label>Currency</Label>
                      <Select
                        value={prefsForm.compensation.currency}
                        onValueChange={(currency) => setPrefsForm((prev) => ({
                          ...prev,
                          compensation: { ...prev.compensation, currency },
                        }))}
                      >
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {CURRENCIES.map((currency) => (
                            <SelectItem key={currency} value={currency}>{currency}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Pay period</Label>
                      <Select
                        value={prefsForm.compensation.pay_period}
                        onValueChange={(pay_period: WorkspacePreferences['compensation']['pay_period']) => setPrefsForm((prev) => ({
                          ...prev,
                          compensation: { ...prev.compensation, pay_period },
                        }))}
                      >
                        <SelectTrigger className="h-9">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="hourly">Hourly</SelectItem>
                          <SelectItem value="monthly">Monthly</SelectItem>
                          <SelectItem value="annual">Annual</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-1.5">
                      <Label>Current compensation</Label>
                      <div className="relative">
                        <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                          {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                        </span>
                        <Input
                          type="number"
                          className="pl-7"
                          value={prefsForm.compensation.current_comp ?? ''}
                          onChange={(event) => setPrefsForm((prev) => ({
                            ...prev,
                            compensation: { ...prev.compensation, current_comp: event.target.value === '' ? null : Number(event.target.value) },
                          }))}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <Label>Absolute minimum (hard floor)</Label>
                    <div className="relative w-48">
                      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                        {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                      </span>
                      <Input
                        type="number"
                        className="pl-7"
                        value={prefsForm.compensation.min_acceptable_tc ?? ''}
                        onChange={(event) => setPrefsForm((prev) => ({
                          ...prev,
                          compensation: { ...prev.compensation, min_acceptable_tc: event.target.value === '' ? null : Number(event.target.value) },
                        }))}
                      />
                    </div>
                    <p className="text-xs text-text-muted">If set, jobs below this are completely hidden — stricter than minimum salary.</p>
                  </div>

                  <div className="space-y-3">
                    <div className="flex items-start gap-3">
                      <Checkbox
                        id="include-equity"
                        checked={prefsForm.compensation.include_equity}
                        onCheckedChange={(checked) => setPrefsForm((prev) => ({
                          ...prev,
                          compensation: { ...prev.compensation, include_equity: !!checked },
                        }))}
                      />
                      <div>
                        <Label htmlFor="include-equity">Count equity toward total compensation</Label>
                        <p className="mt-0.5 text-xs text-text-muted">Useful for startup roles with stock options.</p>
                      </div>
                    </div>
                    <div className="flex items-start gap-3">
                      <Checkbox
                        id="exclude-staffing"
                        checked={prefsForm.exclude_staffing_agencies}
                        onCheckedChange={(checked) => setPrefsForm((prev) => ({
                          ...prev,
                          exclude_staffing_agencies: !!checked,
                        }))}
                      />
                      <div>
                        <Label htmlFor="exclude-staffing">Exclude staffing agencies</Label>
                        <p className="mt-0.5 text-xs text-text-muted">Filter out listings from known recruitment firms.</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <Button onClick={handleSavePreferences} disabled={savePreferences.isPending}>
              {savePreferences.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              Save Preferences
            </Button>
          </CardContent>
        </Card>

        {/* ── AI Provider ─────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4" />
              AI Provider
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Locked: host configured a provider and disabled runtime editing */}
            {!llm?.runtime_configurable && llm?.configured ? (
              <div className="rounded-xl border border-border-default bg-bg-subtle/50 p-4">
                <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                  <CheckCircle2 className="h-4 w-4" />
                  AI scoring is enabled
                </span>
                <p className="mt-1 text-xs text-text-muted">
                  Provider: {llm.provider || 'configured'}{llm.model ? ` · ${llm.model}` : ''}
                </p>
              </div>
            ) : (
              <>
                {/* ── Connected status ────────────────────────────── */}
                {llm?.available && (
                  <div className="rounded-xl border border-success/20 bg-success/5 p-3">
                    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                      <CheckCircle2 className="h-4 w-4" />
                      Connected{llm.provider === 'custom' ? '' : ` to ${llm.label || llm.provider}`}{llm.model ? ` · ${llm.model}` : ''}
                    </span>
                    {llm?.auto_detected === 'ollama' && (
                      <p className="mt-1 text-xs text-text-muted">Auto-detected from your local Ollama installation.</p>
                    )}
                    <button
                      type="button"
                      onClick={() => setShowAllProviders(!showAllProviders)}
                      className="mt-2 text-xs text-text-muted hover:text-text-secondary underline"
                    >
                      Change provider
                    </button>
                  </div>
                )}

                {/* ── Quick setup (when NOT configured) ──────────── */}
                {!llm?.configured && (
                  <div className="space-y-4">
                    {!hostedMode && (ollamaDetect?.detected || (localAI?.servers && localAI.servers.length > 0)) ? (
                      <p className="text-sm text-text-secondary">
                        We found AI running on your machine. Click to connect — no setup needed.
                      </p>
                    ) : (
                      <p className="text-sm text-text-secondary">
                        Launchboard needs AI to score jobs, write cover letters, and research companies for you.
                        The fastest way is <strong>Google Gemini</strong> — free, 30 seconds, no credit card.
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
                    {!hostedMode && localAI?.servers && localAI.servers.length > 0 && localAI.servers.map((server) => (
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

                    {/* Option B: Gemini inline setup */}
                    <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                          <Sparkles className="h-5 w-5 text-brand" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-text-primary">Google Gemini</p>
                            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 uppercase">Free</span>
                            {(hostedMode || !ollamaDetect?.detected) && (
                              <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand uppercase">Recommended</span>
                            )}
                          </div>
                          <p className="mt-0.5 text-xs text-text-muted">Best free AI available — 250 uses/day, no credit card needed.</p>
                        </div>
                      </div>
                      <div className="space-y-2.5 pl-[52px]">
                        <div className="flex items-start gap-2">
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                          <div>
                            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-brand hover:underline">
                              Get your free key from Google <ExternalLink className="h-3 w-3" />
                            </a>
                            <p className="text-[11px] text-text-muted mt-0.5">Sign in with your Google account, click "Create API key", and copy it.</p>
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
                        <Shield className="h-3 w-3 text-emerald-500 shrink-0 mt-0.5" />
                        <p className="text-[10px] text-text-muted leading-relaxed">
                          Your key stays on your {llm?.key_storage === 'keychain' ? 'OS keychain' : 'computer'} and is only sent to Google. Launchboard never sees it.
                        </p>
                      </div>
                    </div>

                    {/* FAQ for non-technical users */}
                    <div className="rounded-xl border border-border-default bg-bg-subtle/30 p-4 space-y-3">
                      <div className="flex items-center gap-2">
                        <HelpCircle className="h-4 w-4 text-text-muted" />
                        <p className="text-xs font-medium text-text-secondary">Common questions</p>
                      </div>
                      <details className="group">
                        <summary className="cursor-pointer text-sm text-text-secondary hover:text-text-primary">
                          I pay for ChatGPT Plus / Claude Pro — can I use that?
                        </summary>
                        <p className="mt-2 text-xs text-text-muted leading-relaxed pl-0.5">
                          Unfortunately, no. ChatGPT Plus and Claude Pro are <em>chat</em> subscriptions — they let you chat on their website,
                          but they don't let other apps like Launchboard use their AI. It's like having a Netflix subscription but not being
                          able to stream Netflix through a different app.
                          <br /><br />
                          The good news: <strong>Google Gemini gives you a free key</strong> that works just as well for Launchboard.
                          It takes 30 seconds and doesn't cost anything.
                        </p>
                      </details>
                      <details className="group">
                        <summary className="cursor-pointer text-sm text-text-secondary hover:text-text-primary">
                          What's an API key?
                        </summary>
                        <p className="mt-2 text-xs text-text-muted leading-relaxed pl-0.5">
                          Think of it like a password that lets Launchboard talk to Google's AI on your behalf. You create one on Google's
                          website (it's free), paste it here, and you're done. It's not shared with anyone else.
                        </p>
                      </details>
                      <details className="group">
                        <summary className="cursor-pointer text-sm text-text-secondary hover:text-text-primary">
                          Is this really free? What's the catch?
                        </summary>
                        <p className="mt-2 text-xs text-text-muted leading-relaxed pl-0.5">
                          Google offers Gemini for free to developers (you get 250 requests per day). For most job searches, this is more
                          than enough. If you search multiple times a day, every day, you might hit the limit — but it resets daily.
                          There's no credit card required and nothing to cancel.
                        </p>
                      </details>
                    </div>

                    <button
                      type="button"
                      onClick={() => setShowAllProviders(!showAllProviders)}
                      className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary"
                    >
                      <ChevronDown className={cn('h-3 w-3 transition-transform', showAllProviders && 'rotate-180')} />
                      {showAllProviders ? 'Hide' : 'Show'} other AI providers
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
                    {!hostedMode && localAI?.servers && localAI.servers.length > 0 && localAI.servers.map((server) => (
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

                    {/* Gemini quick-setup as fallback */}
                    <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                          <Sparkles className="h-5 w-5 text-brand" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-text-primary">Switch to Google Gemini</p>
                            <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 uppercase">Free</span>
                          </div>
                          <p className="mt-0.5 text-xs text-text-muted">Works instantly — 250 uses/day, no credit card.</p>
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
                      Show other options
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

                    {/* Local providers (self-hosted only — backend can't reach user's localhost when hosted) */}
                    {!hostedMode && localPresets.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Runs on your computer</p>
                        {localPresets.map((preset) => {
                          const info = PROVIDER_INFO[preset.name];
                          if (!info) return null;
                          const selected = llmForm.provider === preset.name;
                          return (
                            <button
                              key={preset.name}
                              type="button"
                              onClick={() => selectProvider(preset.name)}
                              className={cn(
                                'w-full rounded-xl border px-4 py-3 text-left transition-all',
                                selected
                                  ? 'border-brand bg-brand-light/40 ring-1 ring-brand/20'
                                  : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
                              )}
                            >
                              <div className="flex items-center justify-between gap-2">
                                <div className="flex items-center gap-2">
                                  <Monitor className="h-4 w-4 text-blue-500" />
                                  <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{preset.label}</span>
                                </div>
                                <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0', info.badgeColor)}>{info.badge}</span>
                              </div>
                              <p className="mt-1 text-xs text-text-muted">{info.description}</p>
                            </button>
                          );
                        })}
                      </div>
                    )}

                    {/* Free cloud providers */}
                    <div className="space-y-2">
                      <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Cloud — free key needed</p>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {freePresets.map((preset) => {
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
                                <div className="flex items-center gap-2">
                                  <span className={cn('text-sm font-medium', selected ? 'text-brand' : 'text-text-primary')}>{preset.label}</span>
                                  {info.recommended && (
                                    <span className="rounded-full bg-brand/10 px-1.5 py-0.5 text-[9px] font-semibold text-brand uppercase">Recommended</span>
                                  )}
                                </div>
                                <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-medium shrink-0', info.badgeColor)}>{info.badge}</span>
                              </div>
                              <p className="mt-1 text-xs text-text-muted">{info.description}</p>
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    {/* Paid providers */}
                    {paidPresets.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Paid (separate from chat subscriptions)</p>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {paidPresets.map((preset) => {
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
                          <span className="rounded-full bg-violet-500/10 px-2 py-0.5 text-[10px] font-medium text-violet-600">Compatible</span>
                        </div>
                        <p className="mt-1 text-xs text-text-muted">Connect your own AI model or server</p>
                      </button>
                    </div>}

                    {/* Setup panel for selected provider */}
                    {llmForm.provider && (
                      <div className="space-y-4 rounded-xl border border-brand/20 bg-brand-light/10 p-4">
                        <p className="text-sm font-medium text-text-primary">
                          {llmForm.provider === 'custom' ? 'Connect to your AI server' : `Set up ${selectedPreset?.label || llmForm.provider}`}
                        </p>

                        {llmForm.provider === 'custom' ? (
                          <div className="space-y-3">
                            {/* Auto-detected servers — click to connect */}
                            {localAI?.servers && localAI.servers.length > 0 && (
                              <div className="space-y-2">
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
                                  <p className="text-xs text-text-muted mt-0.5">Create an account (free) and generate a key — takes about 30 seconds</p>
                                </div>
                              </div>
                            )}
                            <div className="flex items-start gap-3">
                              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-xs font-bold text-brand">{providerInfo?.keyUrl ? '2' : '1'}</span>
                              <div className="flex-1 space-y-1.5">
                                <Label className="text-sm">Paste your key here</Label>
                                <Input
                                  type="password"
                                  placeholder={`Paste the key you copied from ${selectedPreset?.label || 'the provider'}`}
                                  value={llmForm.api_key}
                                  onChange={(event) => setLlmForm((prev) => ({ ...prev, api_key: event.target.value }))}
                                />
                              </div>
                            </div>
                            <div className="flex items-start gap-2 rounded-lg bg-bg-subtle/60 px-3 py-2">
                              <Shield className="h-3.5 w-3.5 text-emerald-500 shrink-0 mt-0.5" />
                              <p className="text-[11px] text-text-muted leading-relaxed">
                                {llm?.key_storage === 'keychain'
                                  ? `Your key is stored in your OS keychain and sent only to ${selectedPreset?.label || 'the provider'}. It never touches disk as plaintext.`
                                  : `Your key is stored locally and sent only to ${selectedPreset?.label || 'the provider'}'s API. Launchboard never sends it to any other server.`}
                              </p>
                            </div>
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
                              <p className="text-sm text-text-muted">Click Save below — Launchboard connects automatically</p>
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
                            Save & Test Connection
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

        {/* ── Auto-Apply ─────────────────────────────────────── */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Rocket className="h-4 w-4" />
              Auto-Apply
              <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 uppercase">Coming soon</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-text-tertiary">
              Launchboard will automatically apply to your top-scored jobs through Greenhouse and Lever career pages.
              You'll review matches first, then approve applications in bulk.
            </p>
            <div className="mt-4 rounded-xl border border-border-default bg-bg-subtle/40 p-4 space-y-3">
              <div className="flex items-center gap-3 text-sm text-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
                AI scores and ranks jobs against your resume
              </div>
              <div className="flex items-center gap-3 text-sm text-text-secondary">
                <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
                Generates tailored cover letters per company
              </div>
              <div className="flex items-center gap-3 text-sm text-text-muted">
                <div className="h-4 w-4 shrink-0 rounded-full border-2 border-border-default" />
                One-click apply to Greenhouse & Lever jobs
              </div>
              <div className="flex items-center gap-3 text-sm text-text-muted">
                <div className="h-4 w-4 shrink-0 rounded-full border-2 border-border-default" />
                LinkedIn Easy Apply integration
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
