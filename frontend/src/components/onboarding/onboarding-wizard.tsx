import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  ArrowRight,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  Monitor,
  Rocket,
  Search,
  Shield,
  Sparkles,
  Upload,
} from 'lucide-react';

import { SearchAreaSection } from '@/components/shared/search-area-section';
import { JobBoardOptionsSection } from '@/components/shared/job-board-options-section';
import { TagListInput } from '@/components/shared/tag-list-input';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useSuggestSearch } from '@/hooks/use-search';
import { useOnboardingState, useStartOnboardingSearch, useUploadWorkspaceResume } from '@/hooks/use-workspace';
import { useLLMStatus, useDetectOllama, useLLMPresets, useUpdateLLM, useTestConnection } from '@/hooks/use-settings';
import { POPULAR_PROVIDER_CHOICES, getPopularProviderNames } from '@/lib/llm-choice';
import { buildDefaultWorkspacePreferences } from '@/lib/profile-preferences';
import {
  buildSearchRunSnapshot,
  buildSearchSnapshotMetadataFromPreferences,
} from '@/lib/search-preferences';
import { getSearchReadiness } from '@/lib/search-readiness';
import { cn } from '@/lib/utils';
import type { WorkspacePreferences } from '@/types/workspace';
import { useWorkspace } from '@/contexts/workspace-context';
import { useSearchContext } from '@/contexts/search-context';
import type { SearchRunSnapshot } from '@/types/search';
import { toast } from 'sonner';

type Step = 'welcome' | 'resume' | 'ai' | 'preferences';

const ALL_STEPS: Step[] = ['welcome', 'resume', 'ai', 'preferences'];

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
}

export function OnboardingWizard({ open, onComplete }: OnboardingWizardProps) {
  const navigate = useNavigate();
  const { hostedMode } = useWorkspace();
  const { data } = useOnboardingState(open);
  const uploadResume = useUploadWorkspaceResume();
  const startOnboardingSearch = useStartOnboardingSearch();
  const suggestSearch = useSuggestSearch();
  const { activate } = useSearchContext();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>('welcome');
  const serverForm = useMemo(
    () => data?.preferences ?? buildDefaultWorkspacePreferences(),
    [data?.preferences],
  );
  const [formDraft, setFormDraft] = useState<WorkspacePreferences | null>(null);
  const form = formDraft ?? serverForm;
  const setForm = useCallback((next: WorkspacePreferences | ((prev: WorkspacePreferences) => WorkspacePreferences)) => {
    setFormDraft((prev) => {
      const base = prev ?? serverForm;
      return typeof next === 'function' ? next(base) : next;
    });
  }, [serverForm]);
  const autoSuggestedCompaniesRef = useRef(false);

  // AI setup state
  const { data: llm } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const { data: ollamaDetect } = useDetectOllama(open && !llm?.configured && !hostedMode);
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();
  const [geminiKey, setGeminiKey] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [selectedAi, setSelectedAi] = useState<'gemini' | 'openai-api' | 'anthropic-api' | 'ollama'>('gemini');
  const [aiConnectedInFlow, setAiConnectedInFlow] = useState(false);

  const aiAlreadyConfigured = !!llm?.configured || !!llm?.auto_detected;
  const aiSetupDone = aiAlreadyConfigured || aiConnectedInFlow;
  const aiAvailable = llm?.available ?? false;
  const resumeUploaded = data?.resume.exists === true;
  const prefilledFromResume = form.roles.length > 0 || form.keywords.length > 0;
  const searchReadiness = getSearchReadiness({
    roles: form.roles,
    keywords: form.keywords,
    locations: form.preferred_places,
    workplacePreference: form.workplace_preference,
    allowResumeFallback: resumeUploaded,
  });

  useEffect(() => {
    if (serverForm.companies.length > 0) {
      autoSuggestedCompaniesRef.current = true;
    }
  }, [serverForm.companies.length]);

  useEffect(() => {
    if (autoSuggestedCompaniesRef.current) return;
    if (!resumeUploaded || !llm?.available) return;
    if (form.companies.length > 0) {
      autoSuggestedCompaniesRef.current = true;
      return;
    }
    if (suggestSearch.isPending) return;
    autoSuggestedCompaniesRef.current = true;
    suggestSearch.mutate('workspace', {
      onSuccess: (result) => {
        setForm((prev) => ({
          ...prev,
          roles: prev.roles.length > 0 ? prev.roles : result.roles,
          keywords: prev.keywords.length > 0 ? prev.keywords : result.keywords,
          companies: prev.companies.length > 0 ? prev.companies : result.companies,
        }));
      },
      onError: () => {
        autoSuggestedCompaniesRef.current = false;
      },
    });
  }, [resumeUploaded, llm?.available, form.companies.length, form.roles.length, form.keywords.length, suggestSearch, setForm]);

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: (result) => {
        toast.success(result.resume.parse_status === 'parsed' ? 'Resume uploaded' : 'Resume uploaded with warnings');
        if (result.analysis) {
          const roles = (result.analysis.suggested_target_roles as string[] | undefined)?.slice(0, 5) ?? [];
          const keywords = (result.analysis.suggested_keywords as string[] | undefined)?.slice(0, 8) ?? [];
          const title = (result.analysis.current_title as string) ?? '';
          const level = (result.analysis.seniority as string) ?? '';
          setForm((prev) => ({
            ...prev,
            roles: roles.length > 0 ? roles : prev.roles,
            keywords: keywords.length > 0 ? keywords : prev.keywords,
            current_title: title || prev.current_title,
            current_level: level || prev.current_level,
          }));
        }
        // Go to AI step (or skip if already configured)
        setStep(aiAlreadyConfigured ? 'preferences' : 'ai');
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : 'Upload failed');
      },
    });
  };

  const handleSetupOllama = () => {
    const model = ollamaDetect?.recommended_model || 'llama3.1';
    updateLLM.mutate(
      { provider: 'ollama', base_url: 'http://localhost:11434/v1', api_key: 'ollama', model },
      {
        onSuccess: () => {
          toast.success(`Connected to Ollama (${model})`);
          setAiConnectedInFlow(true);
          setStep('preferences');
        },
        onError: () => toast.error('Failed to configure Ollama'),
      },
    );
  };

  const connectPresetProvider = (provider: 'gemini' | 'openai-api' | 'anthropic-api', apiKey: string) => {
    const preset = presets?.find((item) => item.name === provider);
    if (!preset) {
      toast.error('Provider preset unavailable');
      return;
    }
    if (!apiKey.trim()) {
      toast.error(
        provider === 'gemini'
          ? 'Paste your Gemini key first'
          : provider === 'openai-api'
            ? 'Paste your OpenAI API key first'
            : 'Paste your Anthropic API key first',
      );
      return;
    }

    updateLLM.mutate(
      { provider, base_url: preset.base_url, api_key: apiKey.trim(), model: preset.model },
      {
        onSuccess: () => {
          testConnection.mutate(undefined, {
            onSuccess: (result) => {
              if (result.success) {
                toast.success(
                  provider === 'gemini'
                    ? 'Connected to Gemini'
                    : provider === 'openai-api'
                      ? 'Connected to ChatGPT'
                      : 'Connected to Claude',
                );
                setAiConnectedInFlow(true);
                setStep('preferences');
              } else {
                toast.error(result.message || 'Connection failed — check your key');
              }
            },
            onError: (error) => toast.error(error instanceof Error ? error.message : 'Connection test failed'),
          });
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to save settings'),
      },
    );
  };

  const handleSetupGemini = () => {
    connectPresetProvider('gemini', geminiKey);
  };

  const goToNextFromResume = () => {
    setStep(aiAlreadyConfigured ? 'preferences' : 'ai');
  };

  const handleSave = () => {
    if (searchReadiness.missingSearchTerms) {
      setStep('preferences');
      toast.error('Add at least one target role or keyword, or upload a resume');
      return;
    }
    if (searchReadiness.missingLocations) {
      setStep('preferences');
      toast.error('Add a preferred location, or switch to Remote + selected places / Remote only');
      return;
    }

    const request = form;

    startOnboardingSearch.mutate(request, {
      onSuccess: (result) => {
        const snapshot: SearchRunSnapshot = buildSearchRunSnapshot({
          profile: 'workspace',
          request: {
            mode: 'search_score',
            roles: request.roles,
            locations: request.preferred_places.map((place) => place.label),
            keywords: request.keywords,
            companies: request.companies,
            include_remote: request.workplace_preference !== 'location_only',
            workplace_preference: request.workplace_preference,
            max_days_old: request.max_days_old,
            include_linkedin_jobs: request.include_linkedin_jobs,
            use_ai: aiAvailable,
          },
          metadata: buildSearchSnapshotMetadataFromPreferences(form),
        });
        activate(result.run_id, 'search_score', snapshot);
        toast.success(aiAvailable ? 'Starting your first AI-ranked search...' : 'Starting your first search...');
        onComplete();
        navigate({ to: '/search' });
      },
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Failed to start search'),
    });
  };

  // Steps to show in progress bar (skip AI step if already configured)
  const visibleSteps = aiAlreadyConfigured
    ? ALL_STEPS.filter((s) => s !== 'ai')
    : ALL_STEPS;

  const isSaving = updateLLM.isPending || testConnection.isPending;
  const popularAiChoices = getPopularProviderNames(hostedMode);
  const selectedChoice = POPULAR_PROVIDER_CHOICES[selectedAi];

  return (
    <Dialog open={open}>
      <DialogContent showCloseButton={false} className="sm:max-w-lg p-0 overflow-hidden">
        <div className="flex justify-center gap-1.5 pt-5">
          {visibleSteps.map((value) => (
            <div
              key={value}
              className={cn(
                'h-1.5 rounded-full transition-all',
                step === value ? 'w-8 bg-brand' : 'w-2 bg-border-default',
              )}
            />
          ))}
        </div>

        <div className="px-6 pb-6 pt-4">
          {/* ── Step 1: Welcome ────────────────────────────────── */}
          {step === 'welcome' && (
            <div className="space-y-5 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light">
                <Rocket className="h-7 w-7 text-brand" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-text-primary">Welcome to Launchboard</h2>
                <p className="mt-2 text-sm text-text-tertiary">
                  Upload your resume, tell us what you want, and Launchboard will start searching right away. Add AI when you want deeper resume-fit ranking, auto-fill, and tailored drafts.
                </p>
              </div>
              <div className="rounded-xl border border-border-default bg-bg-subtle/50 p-4 text-left">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Private workspace</p>
                <p className="mt-2 text-sm text-text-secondary">
                  Your data stays in an isolated workspace and expires after 7 days of inactivity.
                </p>
              </div>
              <Button
                data-testid="onboarding-start"
                onClick={() => setStep(resumeUploaded ? (aiAlreadyConfigured ? 'preferences' : 'ai') : 'resume')}
                className="w-full"
              >
                Get Started <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            </div>
          )}

          {/* ── Step 2: Resume ─────────────────────────────────── */}
          {step === 'resume' && (
            <div className="space-y-5 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light">
                <Upload className="h-7 w-7 text-brand" />
              </div>
              <div>
                <h2 className="text-lg font-semibold text-text-primary">Upload Your Resume</h2>
                <p className="mt-2 text-sm text-text-tertiary">
                  We will parse your resume now so Launchboard can match jobs against your background. AI uses it later for deeper ranking and tailored materials.
                </p>
              </div>

              {resumeUploaded ? (
                <div className="rounded-xl border border-success/20 bg-success/5 p-4 text-left">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10">
                      <FileText className="h-5 w-5 text-red-500" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-text-primary">{data?.resume.filename}</p>
                      <p className="text-xs text-text-muted">
                        {data?.resume.file_size
                          ? `${Math.max(1, Math.round(data.resume.file_size / 1024))} KB`
                          : 'PDF'}
                      </p>
                    </div>
                  </div>
                  {data?.resume.parse_warning && (
                    <p className="mt-3 text-xs text-amber-700 dark:text-amber-300">{data.resume.parse_warning}</p>
                  )}
                </div>
              ) : (
                <button
                  type="button"
                  className={cn(
                    'w-full rounded-xl border-2 border-dashed border-border-default p-8 text-center transition-all',
                    'hover:border-brand hover:bg-brand-light/20',
                  )}
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadResume.isPending}
                >
                  {uploadResume.isPending ? (
                    <Loader2 className="mx-auto mb-2 h-8 w-8 animate-spin text-brand" />
                  ) : (
                    <Upload className="mx-auto mb-2 h-8 w-8 text-text-muted" />
                  )}
                  <p className="text-sm font-medium text-text-primary">
                    {uploadResume.isPending ? 'Uploading...' : 'Click to upload a PDF'}
                  </p>
                  <p className="mt-1 text-xs text-text-muted">PDF only, up to 10MB</p>
                </button>
              )}

              <div className="flex gap-3">
                {resumeUploaded ? (
                  <>
                    <Button variant="outline" onClick={goToNextFromResume} className="flex-1">
                      Customize search
                    </Button>
                    <Button
                      onClick={searchReadiness.missingLocations ? () => setStep('preferences') : handleSave}
                      disabled={startOnboardingSearch.isPending}
                      className="flex-1"
                    >
                      {startOnboardingSearch.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
                      {searchReadiness.missingLocations ? 'Add location first' : 'Search now'}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button variant="outline" onClick={goToNextFromResume} className="flex-1">
                      Skip for now
                    </Button>
                    <Button onClick={goToNextFromResume} className="flex-1">
                      Continue <ArrowRight className="ml-1 h-4 w-4" />
                    </Button>
                  </>
                )}
              </div>
              {resumeUploaded && searchReadiness.missingLocations && (
                <p className="text-xs text-text-muted">
                  Your workspace is currently set to Selected places only. Add a location first, or switch to Remote + selected places / Remote only.
                </p>
              )}
            </div>
          )}

          {/* ── Step 3: AI Provider ───────────────────────────────── */}
          {step === 'ai' && (
            <div className="space-y-5">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light">
                  <Sparkles className="h-7 w-7 text-brand" />
                </div>
                <h2 className="text-lg font-semibold text-text-primary">Connect AI to unlock Launchboard</h2>
                <p className="mt-2 text-sm text-text-tertiary">
                  You can start searching without AI, but AI is what powers resume-fit ranking, search suggestions, cover letters, and application prep.
                </p>
              </div>

              {/* Already done (they came back to this step) */}
              {aiSetupDone && (
                <div className="rounded-xl border border-success/20 bg-success/5 p-3">
                  <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
                    <CheckCircle2 className="h-4 w-4" />
                    AI is connected{llm?.label ? ` — ${llm.label}` : ''}
                  </span>
                </div>
              )}

              {!aiSetupDone && (
                <div className="space-y-3">
                  <p className="text-sm text-text-secondary">
                    Recommended: connect AI now if you want Launchboard to feel tailored from the start. Gemini is the easiest low-cost option. ChatGPT by OpenAI and Claude by Anthropic work too, but they need separate API keys.
                  </p>

                  {/* Option A: Ollama detected */}
                  {ollamaDetect?.detected && (
                    <button
                      type="button"
                      onClick={handleSetupOllama}
                      disabled={isSaving}
                      className="w-full rounded-xl border-2 border-success/30 bg-success/5 p-4 text-left transition-all hover:border-success/50 hover:bg-success/10"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/10">
                          {isSaving ? <Loader2 className="h-5 w-5 animate-spin text-success" /> : <Monitor className="h-5 w-5 text-success" />}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="text-sm font-semibold text-text-primary">Use Ollama</p>
                            <span className="rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-semibold text-success uppercase">Detected</span>
                          </div>
                          <p className="mt-0.5 text-xs text-text-muted">
                            Already running on your machine with {ollamaDetect.recommended_model}. Click to connect instantly.
                          </p>
                        </div>
                      </div>
                      </button>
                  )}

                  <div className="grid gap-2 sm:grid-cols-2">
                    {popularAiChoices.map((providerName) => {
                      const info = POPULAR_PROVIDER_CHOICES[providerName];
                      const selected = selectedAi === providerName;
                      return (
                        <button
                          key={providerName}
                          type="button"
                          onClick={() => setSelectedAi(providerName)}
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

                  <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                        <Sparkles className="h-5 w-5 text-brand" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-text-primary">{selectedChoice.title}</p>
                          <span className={cn('rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase', selectedChoice.badgeClassName)}>{selectedChoice.badge}</span>
                          {selectedAi === 'gemini' && (
                            <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand uppercase">Recommended</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-text-muted">{selectedChoice.detail}</p>
                      </div>
                    </div>

                    <div className="space-y-2.5 pl-[52px]">
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                        <a
                          href={
                            selectedAi === 'gemini'
                              ? 'https://aistudio.google.com/apikey'
                              : selectedAi === 'openai-api'
                                ? 'https://platform.openai.com/api-keys'
                                : selectedAi === 'anthropic-api'
                                  ? 'https://console.anthropic.com/settings/keys'
                                  : 'https://ollama.com'
                          }
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-brand hover:underline"
                        >
                          {selectedAi === 'gemini'
                            ? 'Create a free Gemini API key'
                            : selectedAi === 'openai-api'
                              ? 'Create an OpenAI API key'
                              : selectedAi === 'anthropic-api'
                                ? 'Create an Anthropic API key'
                                : 'Install Ollama'}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                      {selectedAi === 'ollama' ? (
                        <>
                          <div className="flex items-start gap-2">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                            <p className="pt-1 text-sm text-text-muted">Pull a model locally, then connect Launchboard.</p>
                          </div>
                          <code className="ml-7 block rounded bg-bg-subtle px-2 py-1 text-xs text-text-secondary">ollama pull llama3.2:3b</code>
                          <Button
                            size="sm"
                            onClick={handleSetupOllama}
                            disabled={isSaving}
                            className="ml-7"
                          >
                            {isSaving ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <CheckCircle2 className="mr-1.5 h-3 w-3" />}
                            Connect local AI
                          </Button>
                        </>
                      ) : (
                        <>
                          <div className="flex items-start gap-2">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                            <div className="flex-1">
                              <Input
                                type="password"
                                placeholder={
                                  selectedAi === 'gemini'
                                    ? 'Paste your Gemini API key'
                                    : selectedAi === 'openai-api'
                                      ? 'Paste your OpenAI API key'
                                      : 'Paste your Anthropic API key'
                                }
                                value={selectedAi === 'gemini' ? geminiKey : providerKey}
                                onChange={(e) => {
                                  const value = e.target.value;
                                  if (selectedAi === 'gemini') setGeminiKey(value);
                                  else setProviderKey(value);
                                }}
                                className="h-8 text-sm"
                              />
                            </div>
                          </div>
                          <Button
                            size="sm"
                            onClick={() => {
                              if (selectedAi === 'gemini') {
                                handleSetupGemini();
                                return;
                              }
                              connectPresetProvider(selectedAi as 'openai-api' | 'anthropic-api', providerKey);
                            }}
                            disabled={(selectedAi === 'gemini' ? !geminiKey.trim() : !providerKey.trim()) || isSaving}
                            className="ml-7"
                          >
                            {isSaving ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <CheckCircle2 className="mr-1.5 h-3 w-3" />}
                            Connect
                          </Button>
                        </>
                      )}
                    </div>

                    <div className="flex items-start gap-2 pl-[52px]">
                      <Shield className="h-3 w-3 text-emerald-500 shrink-0 mt-0.5" />
                      <p className="text-[10px] text-text-muted leading-relaxed">
                        {selectedAi === 'ollama'
                          ? 'Your model runs on your own machine. Launchboard talks only to your local Ollama server.'
                          : hostedMode
                            ? 'Your key is sent to Launchboard over HTTPS, stored encrypted for your workspace, and used only to call that provider.'
                            : 'Your key is stored on your machine and sent only to that provider.'}
                      </p>
                    </div>
                  </div>

                  <div className="rounded-xl border border-border-default bg-bg-subtle/30 p-4 space-y-3">
                    <div className="flex items-center gap-2">
                      <Shield className="h-4 w-4 text-text-muted" />
                      <p className="text-xs font-medium text-text-secondary">Good to know</p>
                    </div>
                    <p className="text-xs text-text-muted leading-relaxed">
                      ChatGPT Plus and Claude Pro are chat subscriptions. Launchboard needs API access instead, so those subscriptions alone are not enough.
                      Gemini is the easiest free path if you do not want to pay for user AI usage.
                    </p>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('resume')} className="flex-1">
                  Back
                </Button>
                {aiSetupDone ? (
                  <Button onClick={() => setStep('preferences')} className="flex-1">
                    Continue <ArrowRight className="ml-1 h-4 w-4" />
                  </Button>
                ) : (
                  <Button
                    data-testid="onboarding-skip-ai"
                    variant="ghost"
                    onClick={() => setStep('preferences')}
                    className="flex-1 text-text-muted"
                  >
                    Search basics first
                  </Button>
                )}
              </div>

              {!aiSetupDone && (
                <p className="text-center text-[11px] text-text-muted">
                  You can start with basic search now and connect AI later in Settings when you want deeper ranking and drafting.
                </p>
              )}
            </div>
          )}

          {/* ── Step 4: Preferences (simplified) ──────────────── */}
          {step === 'preferences' && (
            <div className="space-y-5">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light">
                  <Search className="h-7 w-7 text-brand" />
                </div>
                <h2 className="text-lg font-semibold text-text-primary">What are you looking for?</h2>
                <p className="mt-2 text-sm text-text-tertiary">
                  {prefilledFromResume
                    ? "We've suggested roles and keywords from your resume. Edit anything below, then hit search."
                    : resumeUploaded
                      ? 'You can search right away using your resume, or refine by adding roles and keywords.'
                      : 'Tell us the basics and we\'ll launch your first search. You can fine-tune everything later in Settings.'}
                </p>
                {!aiAvailable && (
                  <p className="mt-2 text-xs text-text-muted">
                    This first run will work without AI, but ranking will be more basic until you connect it.
                  </p>
                )}
              </div>

              <div className="space-y-4 text-left">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <Label>Target roles</Label>
                    {prefilledFromResume && form.roles.length > 0 && (
                      <span className="rounded-full bg-brand-light px-2 py-0.5 text-[10px] font-medium text-brand">From resume</span>
                    )}
                  </div>
                  <TagListInput
                    value={form.roles}
                    onChange={(roles) => setForm((prev) => ({ ...prev, roles }))}
                    placeholder="e.g. Nurse Practitioner — press Enter to add"
                    helperText="Type a role and press Enter."
                    emptyText="No roles added yet."
                    inputProps={{ 'data-testid': 'onboarding-roles-input' }}
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <Label>Keywords</Label>
                    {prefilledFromResume && form.keywords.length > 0 && (
                      <span className="rounded-full bg-brand-light px-2 py-0.5 text-[10px] font-medium text-brand">From resume</span>
                    )}
                  </div>
                  <TagListInput
                    value={form.keywords}
                    onChange={(keywords) => setForm((prev) => ({ ...prev, keywords }))}
                    placeholder="e.g. Project Management — press Enter to add"
                    emptyText="No keywords added yet."
                  />
                </div>

                <div className="space-y-2">
                  <Label>Target companies</Label>
                  <TagListInput
                    value={form.companies}
                    onChange={(companies) => setForm((prev) => ({ ...prev, companies }))}
                    placeholder="e.g. Stripe — press Enter to add"
                    helperText="Launchboard will search these company career pages directly in addition to the broader job boards."
                    emptyText="No target companies added yet."
                  />
                </div>

                <SearchAreaSection
                  preferredPlaces={form.preferred_places}
                  onPreferredPlacesChange={(preferred_places) => setForm((prev) => ({ ...prev, preferred_places }))}
                  workplacePreference={form.workplace_preference}
                  onWorkplacePreferenceChange={(workplace_preference) => setForm((prev) => ({ ...prev, workplace_preference }))}
                  context="onboarding"
                />

                <JobBoardOptionsSection
                  includeLinkedInJobs={form.include_linkedin_jobs}
                  onIncludeLinkedInJobsChange={(include_linkedin_jobs) => setForm((prev) => ({ ...prev, include_linkedin_jobs }))}
                  context="onboarding"
                />

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>Minimum salary</Label>
                    <Input
                      type="number"
                      value={form.compensation.min_base ?? ''}
                      onChange={(event) => setForm((prev) => ({
                        ...prev,
                        compensation: { ...prev.compensation, min_base: event.target.value === '' ? null : Number(event.target.value) },
                      }))}
                      placeholder="e.g. 80000"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Target salary</Label>
                    <Input
                      type="number"
                      value={form.compensation.target_total_comp ?? ''}
                      onChange={(event) => setForm((prev) => ({
                        ...prev,
                        compensation: { ...prev.compensation, target_total_comp: event.target.value === '' ? null : Number(event.target.value) },
                      }))}
                      placeholder="e.g. 150000"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label>Posted within</Label>
                  <Select value={String(form.max_days_old)} onValueChange={(value) => setForm((prev) => ({ ...prev, max_days_old: Number(value) }))}>
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
              </div>

              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep(aiAlreadyConfigured ? 'resume' : 'ai')} className="flex-1">
                  Back
                </Button>
                <Button
                  data-testid="onboarding-save-search"
                  onClick={handleSave}
                  disabled={startOnboardingSearch.isPending}
                  className="flex-1"
                >
                  {startOnboardingSearch.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
                  Save & Search
                </Button>
              </div>
              {!searchReadiness.missingSearchTerms && !searchReadiness.missingLocations && form.roles.length === 0 && form.keywords.length === 0 && resumeUploaded && (
                <p className="text-center text-[11px] text-text-muted">
                  No roles or keywords entered. Launchboard will derive them from your uploaded resume for this first run.
                </p>
              )}
            </div>
          )}
        </div>

        <input
          ref={fileInputRef}
          data-testid="onboarding-resume-input"
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={handleFileUpload}
        />
      </DialogContent>
    </Dialog>
  );
}
