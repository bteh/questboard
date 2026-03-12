import { useState, useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Rocket, Upload, CheckCircle2, Loader2, ArrowRight, Sparkles, Search, Zap, BarChart3, FileText, DollarSign } from 'lucide-react';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useResumeStatus, useUploadResume } from '@/hooks/use-resume';
import { useLLMStatus, useProfilePreferences, useUpdateProfilePreferences } from '@/hooks/use-settings';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import type { ProfilePreferences } from '@/types/settings';

const STORAGE_KEY = 'launchboard-onboarding-complete';

export function useOnboarding() {
  const { data: llm, isLoading: llmLoading } = useLLMStatus();
  const { data: resume, isLoading: resumeLoading } = useResumeStatus();

  const isLoading = llmLoading || resumeLoading;
  const isNewUser = !isLoading && !llm?.available && !resume?.exists;

  const dismissed = typeof window !== 'undefined' && localStorage.getItem(STORAGE_KEY) === 'true';
  const forceShow = typeof window !== 'undefined' && localStorage.getItem('launchboard-force-onboarding') === 'true';

  // Show wizard for new users who haven't dismissed, or when force-triggered for testing
  const shouldShow = !isLoading && ((isNewUser && !dismissed) || forceShow);

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, 'true');
      localStorage.removeItem('launchboard-force-onboarding');
    } catch {}
  };

  return { shouldShow, dismiss, isLoading };
}

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
}

type Step = 'welcome' | 'resume' | 'preferences' | 'ready';

const STEPS: Step[] = ['welcome', 'resume', 'preferences', 'ready'];

export function OnboardingWizard({ open, onComplete }: OnboardingWizardProps) {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('welcome');
  const { data: resume } = useResumeStatus();
  const uploadResume = useUploadResume();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resumeUploaded = resume?.exists === true;

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: () => {
        toast.success('Resume uploaded');
        setTimeout(() => setStep('preferences'), 600);
      },
      onError: () => toast.error('Upload failed — try again'),
    });
  };

  const handleComplete = () => {
    onComplete();
    navigate({ to: '/settings' });
  };

  const handleSearch = () => {
    onComplete();
    navigate({ to: '/search' });
  };

  return (
    <Dialog open={open}>
      <DialogContent
        showCloseButton={false}
        className="sm:max-w-md p-0 overflow-hidden"
      >
        {/* Progress dots */}
        <div className="flex justify-center gap-1.5 pt-5">
          {STEPS.map((s) => (
            <div
              key={s}
              className={cn(
                'h-1.5 rounded-full transition-all',
                s === step ? 'w-6 bg-brand' : 'w-1.5 bg-border-default',
              )}
            />
          ))}
        </div>

        <div className="px-6 pb-6">
          {step === 'welcome' && (
            <WelcomeStep onNext={() => setStep('resume')} />
          )}
          {step === 'resume' && (
            <ResumeStep
              fileInputRef={fileInputRef}
              isUploading={uploadResume.isPending}
              resumeUploaded={resumeUploaded}
              filename={resume?.filename}
              fileSize={resume?.file_size}
              onFileUpload={handleFileUpload}
              onSkip={() => setStep('preferences')}
              onNext={() => setStep('preferences')}
            />
          )}
          {step === 'preferences' && (
            <PreferencesStep
              onSkip={() => setStep('ready')}
              onNext={() => setStep('ready')}
            />
          )}
          {step === 'ready' && (
            <ReadyStep
              resumeUploaded={resumeUploaded}
              onSetup={handleComplete}
              onSearch={handleSearch}
            />
          )}
        </div>

        <input type="file" ref={fileInputRef} accept=".pdf" className="hidden" onChange={handleFileUpload} />
      </DialogContent>
    </Dialog>
  );
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  return (
    <div className="text-center pt-4 space-y-5">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mx-auto">
        <Rocket className="h-7 w-7 text-brand" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Welcome to Launchboard</h2>
        <p className="text-sm text-text-tertiary mt-2 leading-relaxed max-w-sm mx-auto">
          Your AI-powered job search agent. Let's get you set up in under a minute.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3 text-center">
        {[
          { icon: Search, label: 'Multi-board search' },
          { icon: Zap, label: 'AI-ranked matches' },
          { icon: FileText, label: 'Auto cover letters' },
        ].map((f) => (
          <div key={f.label} className="rounded-lg bg-bg-subtle p-3">
            <f.icon className="h-4 w-4 mx-auto text-brand mb-1.5" />
            <p className="text-[11px] text-text-secondary font-medium leading-tight">{f.label}</p>
          </div>
        ))}
      </div>

      <Button onClick={onNext} className="w-full">
        Get Started <ArrowRight className="h-4 w-4 ml-1.5" />
      </Button>
    </div>
  );
}

function ResumeStep({
  fileInputRef,
  isUploading,
  resumeUploaded,
  filename,
  fileSize,
  onFileUpload: _onFileUpload,
  onSkip,
  onNext,
}: {
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  isUploading: boolean;
  resumeUploaded: boolean;
  filename?: string;
  fileSize?: number;
  onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onSkip: () => void;
  onNext: () => void;
}) {
  const formatSize = (bytes: number) =>
    bytes >= 1_048_576 ? `${(bytes / 1_048_576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

  return (
    <div className="text-center pt-4 space-y-5">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mx-auto">
        <Upload className="h-7 w-7 text-brand" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Upload Your Resume</h2>
        <p className="text-sm text-text-tertiary mt-1.5 leading-relaxed">
          We'll use it to rank jobs by how well they match your experience.
        </p>
      </div>

      {resumeUploaded && filename ? (
        <div className="flex items-center gap-3 rounded-xl border border-success/20 bg-success/5 px-4 py-3 text-left">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10 shrink-0">
            <FileText className="h-5 w-5 text-red-500" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-text-primary truncate" title={filename}>{filename}</p>
            <p className="text-xs text-text-muted">{fileSize ? formatSize(fileSize) : 'PDF'}</p>
          </div>
          <button
            type="button"
            className="text-xs font-medium text-brand hover:text-brand-dark transition-colors shrink-0"
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
          >
            {isUploading ? 'Uploading...' : 'Replace'}
          </button>
        </div>
      ) : (
        <button
          type="button"
          className={cn(
            'w-full rounded-xl border-2 border-dashed p-8 text-center transition-all cursor-pointer',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand',
            'border-border-default hover:border-brand hover:bg-brand-light/30',
          )}
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
        >
          {isUploading ? (
            <Loader2 className="h-8 w-8 mx-auto text-brand animate-spin mb-2" />
          ) : (
            <Upload className="h-8 w-8 mx-auto text-text-muted mb-2" />
          )}
          <p className="text-sm font-medium text-text-primary">
            {isUploading ? 'Uploading...' : 'Click to upload (PDF)'}
          </p>
          <p className="text-xs text-text-muted mt-1">PDF format, up to 10MB</p>
        </button>
      )}

      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          Skip for now
        </Button>
        {resumeUploaded && (
          <Button onClick={onNext} className="flex-1">
            Continue <ArrowRight className="h-4 w-4 ml-1" />
          </Button>
        )}
      </div>
    </div>
  );
}

function PreferencesStep({ onSkip, onNext }: { onSkip: () => void; onNext: () => void }) {
  const { data } = useProfilePreferences();
  const updatePrefs = useUpdateProfilePreferences();

  const [form, setForm] = useState<ProfilePreferences>({
    current_title: '',
    current_level: ['mid'],
    current_tc: 100_000,
    min_base: 80_000,
    target_total_comp: 150_000,
    auto_apply_enabled: false,
    auto_apply_dry_run: true,
  });
  const [initialized, setInitialized] = useState(false);

  // Sync form with server data once loaded
  if (data?.preferences && !initialized) {
    setForm(data.preferences);
    setInitialized(true);
  }

  const handleSave = () => {
    updatePrefs.mutate(form, {
      onSuccess: () => {
        toast.success('Preferences saved');
        onNext();
      },
      onError: () => toast.error('Failed to save preferences'),
    });
  };

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(val);

  return (
    <div className="text-center pt-4 space-y-5">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mx-auto">
        <DollarSign className="h-7 w-7 text-brand" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-text-primary">Career & Compensation</h2>
        <p className="text-sm text-text-tertiary mt-1.5 leading-relaxed">
          Helps us rank jobs by career fit and compensation match.
        </p>
      </div>

      <div className="space-y-4 text-left">
        <div className="space-y-1.5">
          <Label className="text-sm font-medium">Current Title</Label>
          <Input
            value={form.current_title}
            onChange={(e) => setForm((p) => ({ ...p, current_title: e.target.value }))}
            placeholder="e.g. Software Engineer"
            className="h-9"
          />
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-text-secondary">Current TC</Label>
            <Input
              type="number"
              value={form.current_tc}
              onChange={(e) => setForm((p) => ({ ...p, current_tc: Number(e.target.value) }))}
              className="h-9 text-sm"
            />
            <p className="text-[10px] text-text-muted">{formatCurrency(form.current_tc)}</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-text-secondary">Min Base</Label>
            <Input
              type="number"
              value={form.min_base}
              onChange={(e) => setForm((p) => ({ ...p, min_base: Number(e.target.value) }))}
              className="h-9 text-sm"
            />
            <p className="text-[10px] text-text-muted">{formatCurrency(form.min_base)}</p>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs font-medium text-text-secondary">Target TC</Label>
            <Input
              type="number"
              value={form.target_total_comp}
              onChange={(e) => setForm((p) => ({ ...p, target_total_comp: Number(e.target.value) }))}
              className="h-9 text-sm"
            />
            <p className="text-[10px] text-text-muted">{formatCurrency(form.target_total_comp)}</p>
          </div>
        </div>
      </div>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          Skip for now
        </Button>
        <Button onClick={handleSave} disabled={updatePrefs.isPending} className="flex-1">
          {updatePrefs.isPending ? (
            <Loader2 className="h-4 w-4 mr-1 animate-spin" />
          ) : null}
          Save & Continue <ArrowRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function ReadyStep({
  resumeUploaded,
  onSetup,
  onSearch,
}: {
  resumeUploaded: boolean;
  onSetup: () => void;
  onSearch: () => void;
}) {
  return (
    <div className="text-center pt-4 space-y-5">
      <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-light mx-auto">
        <Sparkles className="h-7 w-7 text-brand" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-text-primary">
          {resumeUploaded ? "You're almost ready!" : "One more thing"}
        </h2>
        <p className="text-sm text-text-tertiary mt-1.5 leading-relaxed max-w-xs mx-auto">
          Connect an AI provider in Settings to unlock scoring, cover letters, and company research.
        </p>
      </div>

      <div className="rounded-xl border border-border-default bg-bg-subtle p-4 space-y-3 text-left">
        <div className="flex items-center gap-3">
          <div className={cn(
            'flex h-6 w-6 items-center justify-center rounded-full text-xs shrink-0',
            resumeUploaded ? 'bg-success/15 text-success' : 'bg-bg-muted text-text-muted',
          )}>
            {resumeUploaded ? <CheckCircle2 className="h-4 w-4" /> : '1'}
          </div>
          <span className={cn('text-sm', resumeUploaded ? 'text-success' : 'text-text-secondary')}>
            Upload resume {resumeUploaded && '— done'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-success/15 text-success text-xs shrink-0">
            <CheckCircle2 className="h-4 w-4" />
          </div>
          <span className="text-sm text-success">Set career preferences — done</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-brand-light text-brand text-xs shrink-0">
            3
          </div>
          <span className="text-sm text-text-secondary">Connect an AI provider</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex h-6 w-6 items-center justify-center rounded-full bg-bg-muted text-text-muted text-xs shrink-0">
            4
          </div>
          <span className="text-sm text-text-muted">Start your first search</span>
        </div>
      </div>

      <div className="flex gap-3">
        <Button variant="outline" onClick={onSearch} className="flex-1">
          <Search className="h-4 w-4 mr-1.5" />
          Search without AI
        </Button>
        <Button onClick={onSetup} className="flex-1">
          <BarChart3 className="h-4 w-4 mr-1.5" />
          Set up AI
        </Button>
      </div>
    </div>
  );
}
