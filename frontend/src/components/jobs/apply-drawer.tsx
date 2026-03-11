import { useState, useEffect, useCallback, useRef } from 'react';
import {
  Shield,
  FileText,
  Send,
  CheckCircle2,
  Copy,
  ExternalLink,
  Sparkles,
  AlertTriangle,
  User,
  Mail,
  Building2,
  Check,
  Loader2,
} from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ScoreCircle } from '@/components/scores/score-circle';
import { CompanyAvatar } from '@/components/shared/company-avatar';
import { RecommendationBadge } from '@/components/badges/recommendation-badge';
import { usePrepareApplication, useSubmitApplication } from '@/hooks/use-apply';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';
import type { ApplicationResponse } from '@/types/application';
import type { PrepareResponse } from '@/api/apply';

/* ─── Step definitions ─── */
type DrawerStep = 'preparing' | 'review' | 'submitted' | 'error';

interface ApplyDrawerProps {
  app: ApplicationResponse;
  open: boolean;
  onClose: () => void;
}

/* ─── Preparation progress messages ─── */
const PROGRESS_STEPS = [
  { label: 'Analyzing job requirements...', icon: FileText, durationMs: 800 },
  { label: 'Tailoring your cover letter...', icon: Sparkles, durationMs: 1200 },
  { label: 'Optimizing resume highlights...', icon: Shield, durationMs: 1000 },
] as const;

/* ─── Helper: word count ─── */
function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

/* ─── ATS badge helper ─── */
function AtsBadge({ atsType, atsDetected }: { atsType: string | null; atsDetected: boolean }) {
  if (!atsDetected || !atsType) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-bg-muted px-2.5 py-1 text-xs font-medium text-text-secondary">
        <FileText className="h-3 w-3 text-text-muted" />
        Manual application — we'll prepare your materials
      </span>
    );
  }

  const name = atsType.charAt(0).toUpperCase() + atsType.slice(1);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-brand-light px-2.5 py-1 text-xs font-medium text-brand">
      <Shield className="h-3 w-3" />
      {name} detected — direct API submission
    </span>
  );
}

/* ─── Step 1: Preparing ─── */
function PreparingStep({ progressIndex }: { progressIndex: number }) {
  return (
    <div className="flex flex-col items-center justify-center gap-6 py-12">
      <div className="relative">
        <div className="h-16 w-16 rounded-full bg-brand-light flex items-center justify-center">
          <Loader2 className="h-8 w-8 text-brand animate-spin" />
        </div>
      </div>
      <div className="space-y-4 w-full max-w-xs">
        {PROGRESS_STEPS.map((step, i) => {
          const Icon = step.icon;
          const isActive = i === progressIndex;
          const isComplete = i < progressIndex;
          return (
            <div
              key={step.label}
              className={cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 transition-all duration-300',
                isActive && 'bg-brand-light',
                isComplete && 'opacity-60',
                !isActive && !isComplete && 'opacity-30',
              )}
            >
              {isComplete ? (
                <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
              ) : (
                <Icon
                  className={cn(
                    'h-4 w-4 shrink-0',
                    isActive ? 'text-brand' : 'text-text-muted',
                  )}
                />
              )}
              <span
                className={cn(
                  'text-sm',
                  isActive ? 'text-text-primary font-medium' : 'text-text-secondary',
                )}
              >
                {step.label}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Step 3: Submitted ─── */
function SubmittedStep({
  method,
  onClose,
}: {
  method: string | null;
  onClose: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-12">
      <div className="h-16 w-16 rounded-full bg-success/10 flex items-center justify-center">
        <CheckCircle2 className="h-8 w-8 text-success" />
      </div>
      <div className="text-center space-y-1.5">
        <h3 className="text-lg font-semibold text-text-primary">Application Submitted</h3>
        {method && (
          <p className="text-sm text-text-secondary">Applied via {method}</p>
        )}
        <p className="text-xs text-text-muted">Your application has been tracked</p>
      </div>
      <Button onClick={onClose} className="mt-2 bg-brand text-white hover:bg-brand-hover">
        View Application
      </Button>
    </div>
  );
}

/* ─── Step 4: Error ─── */
function ErrorStep({
  errorMessage,
  onRetry,
  onCopyManual,
  jobUrl,
}: {
  errorMessage: string;
  onRetry: () => void;
  onCopyManual: () => void;
  jobUrl: string | null;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-5 py-12">
      <div className="h-16 w-16 rounded-full bg-danger/10 flex items-center justify-center">
        <AlertTriangle className="h-8 w-8 text-danger" />
      </div>
      <div className="text-center space-y-1.5">
        <h3 className="text-lg font-semibold text-text-primary">Something went wrong</h3>
        <p className="text-sm text-text-secondary max-w-xs">{errorMessage}</p>
      </div>
      <div className="flex items-center gap-3 mt-2">
        <Button onClick={onRetry} variant="outline" size="sm">
          Try Again
        </Button>
        <Button onClick={onCopyManual} variant="outline" size="sm">
          <Copy className="h-3.5 w-3.5 mr-1.5" />
          Copy & Apply Manually
        </Button>
        {jobUrl && (
          <a
            href={jobUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-brand hover:text-brand-hover transition-colors"
          >
            <ExternalLink className="h-3 w-3" />
            Open Posting
          </a>
        )}
      </div>
    </div>
  );
}

/* ─── Main Drawer ─── */
export function ApplyDrawer({ app, open, onClose }: ApplyDrawerProps) {
  const [step, setStep] = useState<DrawerStep>('preparing');
  const [progressIndex, setProgressIndex] = useState(0);
  const [prepareData, setPrepareData] = useState<PrepareResponse | null>(null);
  const [coverLetter, setCoverLetter] = useState('');
  const [errorMessage, setErrorMessage] = useState('');
  const [submitMethod, setSubmitMethod] = useState<string | null>(null);
  const hasStartedRef = useRef(false);

  const prepareMutation = usePrepareApplication();
  const submitMutation = useSubmitApplication();

  /* ─── Reset state when drawer closes ─── */
  useEffect(() => {
    if (!open) {
      // Small delay so animation completes before resetting
      const timer = setTimeout(() => {
        setStep('preparing');
        setProgressIndex(0);
        setPrepareData(null);
        setCoverLetter('');
        setErrorMessage('');
        setSubmitMethod(null);
        hasStartedRef.current = false;
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [open]);

  /* ─── Auto-run preparation on open ─── */
  useEffect(() => {
    if (!open || hasStartedRef.current) return;
    hasStartedRef.current = true;

    // Animate progress steps
    let stepIdx = 0;
    const interval = setInterval(() => {
      stepIdx += 1;
      if (stepIdx >= PROGRESS_STEPS.length) {
        clearInterval(interval);
      } else {
        setProgressIndex(stepIdx);
      }
    }, PROGRESS_STEPS[0].durationMs);

    // Fire the prepare API
    prepareMutation.mutate(app.id, {
      onSuccess: (data) => {
        clearInterval(interval);
        setProgressIndex(PROGRESS_STEPS.length);
        setPrepareData(data);
        setCoverLetter(data.cover_letter ?? '');
        // Short delay so user sees all steps completed
        setTimeout(() => setStep('review'), 400);
      },
      onError: (err) => {
        clearInterval(interval);
        setErrorMessage(err instanceof Error ? err.message : 'Failed to prepare application');
        setStep('error');
      },
    });

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  /* ─── Submit handler ─── */
  const handleSubmit = useCallback(() => {
    submitMutation.mutate(
      { id: app.id, data: { cover_letter: coverLetter || undefined, dry_run: false } },
      {
        onSuccess: (res) => {
          setSubmitMethod(res.method);
          setStep('submitted');
          toast.success(res.message || 'Application submitted');
        },
        onError: (err) => {
          setErrorMessage(err instanceof Error ? err.message : 'Submission failed');
          setStep('error');
        },
      },
    );
  }, [app.id, coverLetter, submitMutation]);

  /* ─── Copy materials handler ─── */
  const handleCopyMaterials = useCallback(() => {
    const parts: string[] = [];
    if (coverLetter) {
      parts.push('--- COVER LETTER ---\n' + coverLetter);
    }
    if (prepareData?.resume_tweaks) {
      parts.push(
        '\n--- RESUME HIGHLIGHTS ---\n' +
          Object.entries(prepareData.resume_tweaks)
            .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
            .join('\n'),
      );
    }
    const text = parts.join('\n\n') || 'No materials generated.';
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Materials copied to clipboard');
    });
  }, [coverLetter, prepareData]);

  /* ─── Retry handler ─── */
  const handleRetry = useCallback(() => {
    setStep('preparing');
    setProgressIndex(0);
    setErrorMessage('');
    hasStartedRef.current = false;
  }, []);

  const atsDetected = prepareData?.ats_detected ?? false;
  const atsType = prepareData?.ats_type ?? null;

  return (
    <Sheet open={open} onOpenChange={(isOpen) => { if (!isOpen) onClose(); }}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg md:max-w-xl flex flex-col p-0"
        showCloseButton
      >
        {/* ─── Header ─── */}
        <SheetHeader className="px-6 pt-6 pb-0">
          <SheetTitle className="text-base font-semibold text-text-primary">
            {step === 'preparing' && 'Preparing Your Application'}
            {step === 'review' && 'Review Your Application'}
            {step === 'submitted' && 'Application Submitted'}
            {step === 'error' && 'Application Error'}
          </SheetTitle>
          <SheetDescription className="text-xs text-text-muted">
            {app.job_title} at {app.company}
          </SheetDescription>
        </SheetHeader>

        <Separator className="mt-4" />

        {/* ─── Body ─── */}
        <ScrollArea className="flex-1 overflow-y-auto">
          <div className="px-6 py-5">
            {step === 'preparing' && <PreparingStep progressIndex={progressIndex} />}

            {step === 'review' && prepareData && (
              <ReviewStep
                app={app}
                prepareData={prepareData}
                coverLetter={coverLetter}
                onCoverLetterChange={setCoverLetter}
                atsDetected={atsDetected}
                atsType={atsType}
              />
            )}

            {step === 'submitted' && (
              <SubmittedStep method={submitMethod} onClose={onClose} />
            )}

            {step === 'error' && (
              <ErrorStep
                errorMessage={errorMessage}
                onRetry={handleRetry}
                onCopyManual={handleCopyMaterials}
                jobUrl={app.job_url}
              />
            )}
          </div>
        </ScrollArea>

        {/* ─── Footer actions (review step only) ─── */}
        {step === 'review' && (
          <>
            <Separator />
            <div className="flex items-center justify-end gap-3 px-6 py-4">
              {atsDetected ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyMaterials}
                  >
                    <Copy className="h-3.5 w-3.5 mr-1.5" />
                    Copy & Apply Manually
                  </Button>
                  <Button
                    size="sm"
                    className="bg-brand text-white hover:bg-brand-hover"
                    onClick={handleSubmit}
                    disabled={submitMutation.isPending}
                  >
                    {submitMutation.isPending ? (
                      <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                    ) : (
                      <Send className="h-3.5 w-3.5 mr-1.5" />
                    )}
                    Submit Application
                  </Button>
                </>
              ) : (
                <>
                  {app.job_url && (
                    <a
                      href={app.job_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 text-xs text-brand hover:text-brand-hover transition-colors font-medium"
                    >
                      <ExternalLink className="h-3.5 w-3.5" />
                      Open Job Posting
                    </a>
                  )}
                  <Button
                    size="sm"
                    className="bg-brand text-white hover:bg-brand-hover"
                    onClick={handleCopyMaterials}
                  >
                    <Copy className="h-3.5 w-3.5 mr-1.5" />
                    Copy Materials
                  </Button>
                </>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/* ─── Step 2: Review ─── */
function ReviewStep({
  app,
  prepareData,
  coverLetter,
  onCoverLetterChange,
  atsDetected,
  atsType,
}: {
  app: ApplicationResponse;
  prepareData: PrepareResponse;
  coverLetter: string;
  onCoverLetterChange: (val: string) => void;
  atsDetected: boolean;
  atsType: string | null;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopyCover = () => {
    navigator.clipboard.writeText(coverLetter).then(() => {
      setCopied(true);
      toast.success('Cover letter copied');
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const resumeTweaks = prepareData.resume_tweaks;
  const applicantInfo = prepareData.applicant_info;

  return (
    <div className="space-y-6">
      {/* ─── Job info summary ─── */}
      <div className="flex items-start gap-3 rounded-xl border border-border-default bg-bg-card p-4">
        <CompanyAvatar company={app.company} size={40} />
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-semibold text-text-primary leading-snug">{prepareData.job_title}</h4>
          <p className="text-xs text-text-secondary mt-0.5">{prepareData.company}</p>
          <div className="flex items-center gap-2 mt-2">
            <ScoreCircle score={app.overall_score} size="sm" />
            <RecommendationBadge recommendation={app.recommendation} />
          </div>
        </div>
      </div>

      {/* ─── ATS detection badge ─── */}
      <div className="flex items-center">
        <AtsBadge atsType={atsType} atsDetected={atsDetected} />
      </div>

      {/* ─── Cover Letter ─── */}
      <Section
        icon={<FileText className="h-4 w-4 text-brand" />}
        title="Cover Letter"
        trailing={
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-md bg-brand-light px-1.5 py-0.5 text-[10px] font-medium text-brand">
              <Sparkles className="h-2.5 w-2.5" />
              AI Generated
            </span>
            <button
              type="button"
              onClick={handleCopyCover}
              className="inline-flex items-center gap-1 text-[11px] text-text-muted hover:text-text-secondary transition-colors px-1.5 py-0.5 rounded-md hover:bg-bg-muted cursor-pointer"
            >
              {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        }
      >
        <Textarea
          value={coverLetter}
          onChange={(e) => onCoverLetterChange(e.target.value)}
          className="min-h-[200px] text-sm leading-relaxed resize-y"
          placeholder="No cover letter generated. You can write one here..."
        />
        <p className="text-[11px] text-text-muted mt-1.5 text-right tabular-nums">
          {wordCount(coverLetter)} words / {coverLetter.length} characters
        </p>
      </Section>

      {/* ─── Resume Highlights ─── */}
      {resumeTweaks && Object.keys(resumeTweaks).length > 0 && (
        <Section
          icon={<Sparkles className="h-4 w-4 text-brand" />}
          title="Resume Highlights"
        >
          <div className="space-y-2">
            {Object.entries(resumeTweaks).map(([key, value]) => {
              const label = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              return (
                <div
                  key={key}
                  className="flex items-start gap-2 rounded-md bg-bg-subtle p-2.5 text-xs"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 text-success mt-0.5 shrink-0" />
                  <div>
                    <span className="font-medium text-text-primary">{label}: </span>
                    <span className="text-text-secondary">
                      {typeof value === 'string' ? value : JSON.stringify(value)}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* ─── Application Details ─── */}
      <Section
        icon={<User className="h-4 w-4 text-brand" />}
        title="Application Details"
      >
        <div className="space-y-2.5 text-sm">
          <DetailRow
            icon={<User className="h-3.5 w-3.5" />}
            label="Name"
            value={`${applicantInfo.first_name} ${applicantInfo.last_name}`}
          />
          <DetailRow
            icon={<Mail className="h-3.5 w-3.5" />}
            label="Email"
            value={applicantInfo.email}
          />
          {applicantInfo.phone && (
            <DetailRow
              icon={<User className="h-3.5 w-3.5" />}
              label="Phone"
              value={applicantInfo.phone}
            />
          )}
          <DetailRow
            icon={<Building2 className="h-3.5 w-3.5" />}
            label="Application System"
            value={atsDetected && atsType ? atsType.charAt(0).toUpperCase() + atsType.slice(1) : 'None detected'}
          />
        </div>

        {/* What will be sent summary */}
        <div className="mt-3 rounded-md border border-border-default bg-bg-subtle p-3">
          <p className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-2">
            What will be sent
          </p>
          <ul className="space-y-1">
            <SummaryItem present={!!coverLetter} label="Cover letter" />
            <SummaryItem
              present={!!resumeTweaks && Object.keys(resumeTweaks).length > 0}
              label="Tailored resume highlights"
            />
            <SummaryItem present label="Contact information" />
            <SummaryItem present={atsDetected} label={`Direct ${atsType ?? 'application'} submission`} />
          </ul>
        </div>
      </Section>
    </div>
  );
}

/* ─── Shared sub-components ─── */

function Section({
  icon,
  title,
  trailing,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  trailing?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {icon}
          <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
        </div>
        {trailing}
      </div>
      {children}
    </div>
  );
}

function DetailRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-text-muted">{icon}</span>
      <span className="text-text-tertiary w-20 shrink-0">{label}</span>
      <span className="text-text-primary font-medium">{value}</span>
    </div>
  );
}

function SummaryItem({ present, label }: { present: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-xs">
      {present ? (
        <CheckCircle2 className="h-3 w-3 text-success shrink-0" />
      ) : (
        <div className="h-3 w-3 rounded-full border border-border-default shrink-0" />
      )}
      <span className={present ? 'text-text-secondary' : 'text-text-muted'}>{label}</span>
    </li>
  );
}
