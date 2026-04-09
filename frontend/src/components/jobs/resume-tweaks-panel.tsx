import { useState, type ReactNode } from 'react';
import { Check, Copy, FileText, Hash, Sparkles, Tag } from 'lucide-react';
import { toast } from 'sonner';

import { cn } from '@/lib/utils';
import type { BulletTweak, ResumeOptimization } from '@/types/application';

/**
 * Renders the resume-optimizer LLM output as copy-paste-ready coaching
 * instead of a raw JSON dump. Each section has its own copy button so a
 * non-technical user can:
 *
 *   1. Open a STRONG_APPLY job
 *   2. Read the Evaluation tab to decide whether to apply
 *   3. Open the Resume tab, click "Copy summary", paste into their resume
 *   4. Copy each bullet tweak individually, paste into their resume
 *   5. Done — they have a tailored resume without editing any template
 *
 * This component is deliberately NOT a PDF generator. For a non-technical
 * user, keeping their real .docx / .pdf file as the source of truth and
 * letting them apply the tweaks manually is actually more trustworthy than
 * a generated PDF that might mangle their layout or fail an ATS check.
 *
 * Inspired by the "Block E — CV Personalization" structure in career-ops
 * (santifer/career-ops) but surfaced as actionable UI instead of markdown.
 */
interface ResumeTweaksPanelProps {
  tweaks: ResumeOptimization;
}

export function ResumeTweaksPanel({ tweaks }: ResumeTweaksPanelProps) {
  const hasSummary = !!tweaks.summary_rewrite?.trim();
  const hasTitle = !!tweaks.title_suggestion?.trim();
  const hasKeywords = (tweaks.keywords_to_add?.length ?? 0) > 0;
  const hasBullets = (tweaks.bullet_tweaks?.length ?? 0) > 0;
  const hasSections = (tweaks.sections_to_emphasize?.length ?? 0) > 0;
  const hasAts = (tweaks.ats_compatibility_notes?.length ?? 0) > 0;

  const anything = hasSummary || hasTitle || hasKeywords || hasBullets || hasSections || hasAts;

  if (!anything) {
    return (
      <p className="text-sm text-text-muted">
        No resume tweaks were generated for this role. This usually means the AI either wasn't
        connected when the search ran or decided no specific changes were needed.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      {/* Intro / how-to-use */}
      <div className="rounded-lg border border-border-default bg-bg-subtle/40 px-3 py-2.5 text-xs leading-relaxed text-text-muted">
        These are tailored suggestions for <span className="font-medium text-text-secondary">this specific job</span>.
        Open your resume, click the copy buttons below, and paste the updates in. You stay in control of your real file.
      </div>

      {/* Summary rewrite — the highest-impact single block */}
      {hasSummary && (
        <Section
          icon={<Sparkles className="h-3.5 w-3.5" />}
          title="Tailored professional summary"
          helper="Replace the top paragraph of your resume with this version."
          copyText={tweaks.summary_rewrite!}
          copyLabel="Summary"
        >
          <p className="text-sm leading-relaxed text-text-primary">{tweaks.summary_rewrite}</p>
        </Section>
      )}

      {/* Title suggestion — small but high leverage */}
      {hasTitle && (
        <Section
          icon={<Hash className="h-3.5 w-3.5" />}
          title="Resume headline / title"
          helper="Use this as the line directly under your name."
          copyText={tweaks.title_suggestion!}
          copyLabel="Title"
        >
          <p className="text-sm font-medium text-text-primary">{tweaks.title_suggestion}</p>
        </Section>
      )}

      {/* Keywords — quick-copy for the skills section */}
      {hasKeywords && (
        <Section
          icon={<Tag className="h-3.5 w-3.5" />}
          title="Keywords to weave in"
          helper="Work these into your summary, skills, or bullet points. ATS systems scan for exact matches."
          copyText={(tweaks.keywords_to_add || []).join(', ')}
          copyLabel="Keywords"
        >
          <div className="flex flex-wrap gap-1.5">
            {(tweaks.keywords_to_add || []).map((kw, idx) => (
              <span
                key={`${idx}-${kw}`}
                className="inline-flex items-center rounded-md bg-bg-card px-2 py-1 text-xs text-text-secondary ring-1 ring-border-default"
              >
                {kw}
              </span>
            ))}
          </div>
        </Section>
      )}

      {/* Bullet rewrites — the biggest section, one card per tweak with
          its own copy button so users can pick-and-choose */}
      {hasBullets && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <FileText className="h-3.5 w-3.5 text-text-muted" />
            <h4 className="text-xs font-medium uppercase tracking-wide text-text-muted">
              Experience bullets to rewrite
            </h4>
          </div>
          <p className="text-xs leading-relaxed text-text-muted">
            For each bullet below, the new version is already tailored to the job description. Click Copy on
            the ones you want to use and paste them in over the originals.
          </p>
          <div className="space-y-2.5">
            {(tweaks.bullet_tweaks || []).map((tweak, idx) => (
              <BulletTweakCard key={idx} tweak={tweak} />
            ))}
          </div>
        </div>
      )}

      {/* Sections to emphasize — smaller advisory */}
      {hasSections && (
        <div className="rounded-lg border border-border-default bg-bg-card p-3">
          <h4 className="text-xs font-medium uppercase tracking-wide text-text-muted mb-2">
            Sections to move up or expand
          </h4>
          <ul className="space-y-1.5">
            {(tweaks.sections_to_emphasize || []).map((section, idx) => (
              <li key={idx} className="flex items-start gap-2 text-sm text-text-secondary">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-brand" />
                <span>{section}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ATS notes — last because it's the least actionable */}
      {hasAts && (
        <div className="rounded-lg border border-border-default bg-bg-subtle/40 p-3">
          <h4 className="text-xs font-medium uppercase tracking-wide text-text-muted mb-2">
            ATS compatibility notes
          </h4>
          <ul className="space-y-1.5">
            {(tweaks.ats_compatibility_notes || []).map((note, idx) => (
              <li key={idx} className="flex items-start gap-2 text-xs leading-relaxed text-text-tertiary">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-text-muted" />
                <span>{note}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

interface SectionProps {
  icon: ReactNode;
  title: string;
  helper?: string;
  copyText: string;
  copyLabel: string;
  children: ReactNode;
}

function Section({ icon, title, helper, copyText, copyLabel, children }: SectionProps) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-card p-3.5">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 text-text-muted">
            {icon}
            <h4 className="text-xs font-medium uppercase tracking-wide">{title}</h4>
          </div>
          {helper && <p className="mt-1 text-[11px] leading-relaxed text-text-tertiary">{helper}</p>}
        </div>
        <CopyButton text={copyText} label={copyLabel} />
      </div>
      <div className="rounded-md bg-bg-subtle/40 px-3 py-2">{children}</div>
    </div>
  );
}

function BulletTweakCard({ tweak }: { tweak: BulletTweak }) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-card p-3">
      {/* Original → new with a copy button targeting only the tweaked version */}
      {tweak.original_bullet && (
        <div className="mb-2">
          <p className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Before</p>
          <p className="mt-0.5 text-xs leading-relaxed text-text-tertiary line-through decoration-text-muted/40">
            {tweak.original_bullet}
          </p>
        </div>
      )}
      <div>
        <div className="flex items-center justify-between gap-3">
          <p className="text-[10px] font-medium uppercase tracking-wide text-brand">
            Rewritten for this job
          </p>
          <CopyButton text={tweak.tweaked_bullet} label="Bullet" />
        </div>
        <p className="mt-1 rounded-md bg-brand-light/30 px-2.5 py-2 text-sm leading-relaxed text-text-primary">
          {tweak.tweaked_bullet}
        </p>
      </div>
      {tweak.rationale && (
        <p className="mt-2 text-[11px] leading-relaxed text-text-tertiary">
          <span className="font-medium text-text-secondary">Why: </span>
          {tweak.rationale}
        </p>
      )}
      {tweak.target_keywords && tweak.target_keywords.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {tweak.target_keywords.map((kw, idx) => (
            <span
              key={`${idx}-${kw}`}
              className="rounded-full border border-border-default bg-bg-subtle/60 px-1.5 py-0.5 text-[10px] text-text-muted"
            >
              {kw}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        toast.success(`${label} copied`);
        setTimeout(() => setCopied(false), 1800);
      })
      .catch(() => {
        toast.error('Clipboard unavailable — select the text manually');
      });
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-md border border-border-default bg-bg-card px-2 py-1 text-[11px] font-medium transition-colors',
        copied ? 'text-success' : 'text-text-muted hover:bg-bg-subtle hover:text-text-primary',
      )}
    >
      {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}
