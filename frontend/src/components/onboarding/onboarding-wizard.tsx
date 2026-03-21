import { useEffect, useRef, useState } from 'react';
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

import { LocationListInput } from '@/components/shared/location-list-input';
import { TagListInput } from '@/components/shared/tag-list-input';
import { WorkplacePreferenceSelector } from '@/components/shared/workplace-preference-selector';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useOnboardingState, useStartOnboardingSearch, useUploadWorkspaceResume } from '@/hooks/use-workspace';
import { useLLMStatus, useDetectOllama, useUpdateLLM, useTestConnection } from '@/hooks/use-settings';
import { buildDefaultWorkspacePreferences } from '@/lib/profile-preferences';
import { cn } from '@/lib/utils';
import type { WorkspacePreferences } from '@/types/workspace';
import { useWorkspace } from '@/contexts/workspace-context';
import { useSearchContext } from '@/contexts/search-context';
import type { SearchRunSnapshot } from '@/types/search';
import { toast } from 'sonner';

type Step = 'welcome' | 'resume' | 'ai' | 'preferences';

const ALL_STEPS: Step[] = ['welcome', 'resume', 'ai', 'preferences'];

export function useOnboarding() {
  const { isLoading: workspaceLoading } = useWorkspace();
  const { data, isLoading } = useOnboardingState(!workspaceLoading);

  return {
    shouldShow: !workspaceLoading && !isLoading && !!data && !data.ready_to_search,
    dismiss: () => {},
    isLoading: workspaceLoading || isLoading,
  };
}

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
}

export function OnboardingWizard({ open, onComplete }: OnboardingWizardProps) {
  const navigate = useNavigate();
  const { data } = useOnboardingState(open);
  const uploadResume = useUploadWorkspaceResume();
  const startOnboardingSearch = useStartOnboardingSearch();
  const { activate } = useSearchContext();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<Step>('welcome');
  const [form, setForm] = useState<WorkspacePreferences>(buildDefaultWorkspacePreferences());
  const [prefilledFromResume, setPrefilledFromResume] = useState(false);

  // AI setup state
  const { data: llm } = useLLMStatus();
  const { data: ollamaDetect } = useDetectOllama(open && !llm?.configured);
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();
  const [geminiKey, setGeminiKey] = useState('');
  const [aiSetupDone, setAiSetupDone] = useState(false);

  const aiAlreadyConfigured = !!llm?.configured || !!llm?.auto_detected;
  const resumeUploaded = data?.resume.exists === true;

  useEffect(() => {
    if (data?.preferences) {
      setForm(data.preferences);
      if (data.preferences.roles.length > 0 || data.preferences.keywords.length > 0) {
        setPrefilledFromResume(true);
      }
    }
  }, [data]);

  // Track when AI gets configured during this session
  useEffect(() => {
    if (llm?.configured && !aiSetupDone) {
      setAiSetupDone(true);
    }
  }, [llm?.configured, aiSetupDone]);

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
          if (roles.length > 0 || keywords.length > 0) {
            setPrefilledFromResume(true);
          }
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
          setAiSetupDone(true);
          setStep('preferences');
        },
        onError: () => toast.error('Failed to configure Ollama'),
      },
    );
  };

  const handleSetupGemini = () => {
    if (!geminiKey.trim()) {
      toast.error('Paste your Gemini key first');
      return;
    }
    updateLLM.mutate(
      { provider: 'gemini', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai/', api_key: geminiKey.trim(), model: 'gemini-2.5-flash' },
      {
        onSuccess: () => {
          testConnection.mutate(undefined, {
            onSuccess: (result) => {
              if (result.success) {
                toast.success('Connected to Gemini');
                setAiSetupDone(true);
                setStep('preferences');
              } else {
                toast.error(result.message || 'Connection failed — check your key');
              }
            },
            onError: () => toast.error('Connection test failed'),
          });
        },
        onError: () => toast.error('Failed to save settings'),
      },
    );
  };

  const goToNextFromResume = () => {
    setStep(aiAlreadyConfigured ? 'preferences' : 'ai');
  };

  const handleSave = () => {
    const hasTerms = form.roles.length > 0 || form.keywords.length > 0;
    const hasLocations = form.workplace_preference === 'remote_only' || form.preferred_places.length > 0;

    if (!hasTerms && !resumeUploaded) {
      toast.error('Add at least one target role or keyword, or upload a resume');
      return;
    }
    if (!hasLocations && !resumeUploaded) {
      toast.error('Add at least one preferred location, or switch to Remote only');
      return;
    }

    startOnboardingSearch.mutate(form, {
      onSuccess: (result) => {
        const snapshot: SearchRunSnapshot = {
          profile: 'workspace',
          mode: 'search_score',
          roles: form.roles,
          locations: form.preferred_places.map((place) => place.label),
          keywords: form.keywords,
          include_remote: form.workplace_preference !== 'location_only',
          workplace_preference: form.workplace_preference,
          max_days_old: form.max_days_old,
          use_ai: true,
          current_title: form.current_title,
          current_level: form.current_level,
          current_tc: form.compensation.current_comp,
          min_base: form.compensation.min_base,
          target_total_comp: form.compensation.target_total_comp,
          min_acceptable_tc: form.compensation.min_acceptable_tc,
          compensation_currency: form.compensation.currency,
          compensation_period: form.compensation.pay_period,
          include_equity: form.compensation.include_equity,
          exclude_staffing_agencies: form.exclude_staffing_agencies,
        };
        activate(result.run_id, 'search_score', snapshot);
        toast.success('Starting your first search...');
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
                  Upload your resume, tell us what you're looking for, and we'll search 14+ job boards for you.
                </p>
              </div>
              <div className="rounded-xl border border-border-default bg-bg-subtle/50 p-4 text-left">
                <p className="text-xs font-medium uppercase tracking-wide text-text-muted">Private workspace</p>
                <p className="mt-2 text-sm text-text-secondary">
                  Your data stays in an isolated workspace and expires after 7 days of inactivity.
                </p>
              </div>
              <Button onClick={() => setStep(resumeUploaded ? (aiAlreadyConfigured ? 'preferences' : 'ai') : 'resume')} className="w-full">
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
                  We'll extract your skills and experience to rank jobs more accurately. You can skip this.
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
                    <Button onClick={handleSave} disabled={startOnboardingSearch.isPending} className="flex-1">
                      {startOnboardingSearch.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
                      Search now
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
            </div>
          )}

          {/* ── Step 3: AI Provider ───────────────────────────────── */}
          {step === 'ai' && (
            <div className="space-y-5">
              <div className="text-center">
                <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light">
                  <Sparkles className="h-7 w-7 text-brand" />
                </div>
                <h2 className="text-lg font-semibold text-text-primary">Connect AI</h2>
                <p className="mt-2 text-sm text-text-tertiary">
                  Launchboard uses AI to score jobs against your resume, generate cover letters, and research companies. Takes 30 seconds.
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

                  {/* Option B: Gemini (always shown) */}
                  <div className="rounded-xl border border-border-default bg-bg-card p-4 space-y-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-light">
                        <Sparkles className="h-5 w-5 text-brand" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-semibold text-text-primary">Google Gemini</p>
                          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 uppercase">Free</span>
                          {!ollamaDetect?.detected && (
                            <span className="rounded-full bg-brand/10 px-2 py-0.5 text-[10px] font-semibold text-brand uppercase">Recommended</span>
                          )}
                        </div>
                        <p className="mt-0.5 text-xs text-text-muted">Gemini 2.5 Flash — best free model, 250 requests/day, no credit card.</p>
                      </div>
                    </div>

                    <div className="space-y-2.5 pl-[52px]">
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">1</span>
                        <a
                          href="https://aistudio.google.com/apikey"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-brand hover:underline"
                        >
                          Get your free key from Google <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-[10px] font-bold text-brand">2</span>
                        <div className="flex-1">
                          <Input
                            type="password"
                            placeholder="Paste your key here"
                            value={geminiKey}
                            onChange={(e) => setGeminiKey(e.target.value)}
                            className="h-8 text-sm"
                          />
                        </div>
                      </div>
                      <Button
                        size="sm"
                        onClick={handleSetupGemini}
                        disabled={!geminiKey.trim() || isSaving}
                        className="ml-7"
                      >
                        {isSaving ? <Loader2 className="mr-1.5 h-3 w-3 animate-spin" /> : <CheckCircle2 className="mr-1.5 h-3 w-3" />}
                        Connect
                      </Button>
                    </div>

                    <div className="flex items-start gap-2 pl-[52px]">
                      <Shield className="h-3 w-3 text-emerald-500 shrink-0 mt-0.5" />
                      <p className="text-[10px] text-text-muted leading-relaxed">
                        Your key is stored on your machine and sent only to Google. Launchboard never sees it.
                      </p>
                    </div>
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
                  <Button variant="ghost" onClick={() => setStep('preferences')} className="flex-1 text-text-muted">
                    Skip — I'll do this later
                  </Button>
                )}
              </div>

              {!aiSetupDone && (
                <p className="text-center text-[11px] text-text-muted">
                  You can change providers or add more in Settings anytime.
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
                  <Label>Preferred locations</Label>
                  <LocationListInput
                    value={form.preferred_places}
                    onChange={(preferred_places) => setForm((prev) => ({ ...prev, preferred_places }))}
                    emptyText={form.workplace_preference === 'remote_only' ? 'Remote-only — no locations needed.' : 'No locations added yet.'}
                    helperText="Type a city or state, then press Enter."
                  />
                </div>

                <div className="space-y-2">
                  <Label>Workplace type</Label>
                  <WorkplacePreferenceSelector
                    value={form.workplace_preference}
                    onChange={(workplace_preference) => setForm((prev) => ({ ...prev, workplace_preference }))}
                  />
                </div>

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
                <Button onClick={handleSave} disabled={startOnboardingSearch.isPending} className="flex-1">
                  {startOnboardingSearch.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Search className="mr-1 h-4 w-4" />}
                  Save & Search
                </Button>
              </div>
            </div>
          )}
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,application/pdf"
          className="hidden"
          onChange={handleFileUpload}
        />
      </DialogContent>
    </Dialog>
  );
}
