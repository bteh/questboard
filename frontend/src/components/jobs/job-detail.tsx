import { useMemo, useState } from 'react';
import { FileText, Mail, Pencil, Building2, Copy, Check, ExternalLink, Compass } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { ScoreBars } from '@/components/scores/score-bars';
import { ScoreCircle } from '@/components/scores/score-circle';
import { StrengthsGaps } from '@/components/scores/strengths-gaps';
import { StatusBadge } from '@/components/badges/status-badge';
import { EvaluationReportView } from '@/components/jobs/evaluation-report';
import { useUpdateStatus } from '@/hooks/use-applications';
import { STATUS_OPTIONS, STATUS_LABELS } from '@/utils/constants';
import { cleanDescription } from '@/utils/format';
import { toast } from 'sonner';
import type { ApplicationResponse, EvaluationReport } from '@/types/application';

interface JobDetailProps {
  app: ApplicationResponse;
}

/**
 * Detect if a line looks like a section header.
 * Matches: "Minimum qualifications:", "ABOUT THE ROLE", "About the job", etc.
 */
function isHeader(line: string): boolean {
  // Short line ending with colon
  if (line.length < 80 && line.endsWith(':')) return true;
  // ALL CAPS line with letters
  if (line.length < 60 && line === line.toUpperCase() && /[A-Z]/.test(line)) return true;
  // Common section heading patterns (case-insensitive)
  if (/^(about|responsibilities|requirements|qualifications|what|who|why|how|benefits|perks|preferred|minimum|nice to have|our|the|your)/i.test(line) && line.length < 80) return true;
  return false;
}

/**
 * Convert a cleaned plain-text description into simple HTML.
 * Handles bullet lists, numbered lists, paragraphs, and section headers.
 */
function descriptionToHtml(raw: string): string {
  const cleaned = cleanDescription(raw);
  if (!cleaned) return '<p class="text-text-muted">No description available.</p>';

  const escaped = cleaned
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  const lines = escaped.split('\n');
  const parts: string[] = [];
  let inList = false;
  let listType: 'ul' | 'ol' = 'ul';

  const closeList = () => {
    if (inList) { parts.push(listType === 'ol' ? '</ol>' : '</ul>'); inList = false; }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) { closeList(); continue; }

    // Bullet list items
    const bulletMatch = trimmed.match(/^[-•·]\s+(.+)/);
    if (bulletMatch) {
      if (!inList || listType !== 'ul') { closeList(); listType = 'ul'; parts.push('<ul class="list-disc pl-5 my-2 space-y-1">'); inList = true; }
      parts.push(`<li>${bulletMatch[1]}</li>`);
      continue;
    }

    // Numbered list items
    const numberedMatch = trimmed.match(/^\d+[.)]\s+(.+)/);
    if (numberedMatch) {
      if (!inList || listType !== 'ol') { closeList(); listType = 'ol'; parts.push('<ol class="list-decimal pl-5 my-2 space-y-1">'); inList = true; }
      parts.push(`<li>${numberedMatch[1]}</li>`);
      continue;
    }

    closeList();

    // Section headers
    if (isHeader(trimmed)) {
      parts.push(`<h4 class="font-semibold text-text-primary mt-5 mb-1.5 text-[13px]">${trimmed}</h4>`);
      continue;
    }

    parts.push(`<p class="mb-2 leading-relaxed">${trimmed}</p>`);
  }

  closeList();
  return parts.join('\n');
}

/** Human-readable overrides for snake_case field names. */
const LABEL_OVERRIDES: Record<string, string> = {
  company_intel_json: 'Company Background',
  resume_tweaks_json: 'Resume Suggestions',
  funding_stage: 'Funding Stage',
  total_funding: 'Total Funding',
  employee_count: 'Employees',
  founded_year: 'Year Founded',
  job_url: 'Job URL',
  is_remote: 'Remote',
  work_type: 'Work Arrangement',
  date_posted: 'Date Posted',
  date_found: 'Date Found',
  date_applied: 'Date Applied',
};

/** Render a JSON object as readable key-value pairs instead of raw JSON. */
function KeyValueDisplay({ data }: { data: Record<string, unknown> }) {
  return (
    <dl className="space-y-3">
      {Object.entries(data).map(([key, value]) => {
        const label = LABEL_OVERRIDES[key] || key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        if (Array.isArray(value)) {
          return (
            <div key={key}>
              <dt className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1">{label}</dt>
              <dd>
                <ul className="list-disc pl-5 space-y-0.5 text-sm text-text-secondary">
                  {value.map((item, i) => <li key={i}>{String(item)}</li>)}
                </ul>
              </dd>
            </div>
          );
        }
        if (value && typeof value === 'object') {
          return (
            <div key={key}>
              <dt className="text-xs font-medium text-text-tertiary uppercase tracking-wider mb-1">{label}</dt>
              <dd className="text-sm text-text-secondary bg-bg-subtle rounded-md p-3">
                <KeyValueDisplay data={value as Record<string, unknown>} />
              </dd>
            </div>
          );
        }
        return (
          <div key={key} className="flex items-baseline gap-2">
            <dt className="text-xs font-medium text-text-tertiary uppercase tracking-wider whitespace-nowrap">{label}:</dt>
            <dd className="text-sm text-text-secondary">{String(value ?? '—')}</dd>
          </div>
        );
      })}
    </dl>
  );
}

function safeJsonParse(json: string | null | undefined): Record<string, unknown> | null {
  if (!json) return null;
  try { return JSON.parse(json) as Record<string, unknown>; }
  catch { return null; }
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      toast.success(`${label} copied`);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex items-center gap-1 text-[11px] text-text-muted hover:text-text-secondary transition-colors cursor-pointer px-2 py-1 rounded-md hover:bg-bg-muted"
    >
      {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

export function JobDetail({ app }: JobDetailProps) {
  const updateStatus = useUpdateStatus();
  const companyIntel = useMemo(() => safeJsonParse(app.company_intel_json), [app.company_intel_json]);
  const resumeTweaks = useMemo(() => safeJsonParse(app.resume_tweaks_json), [app.resume_tweaks_json]);
  const evaluationReport = useMemo<EvaluationReport | null>(() => {
    const parsed = safeJsonParse(app.evaluation_report_json);
    if (!parsed) return null;
    // Defensive shape check — if the LLM returned an unexpected object we
    // don't want to render garbage. The required fields are all optional in
    // the schema, so just confirm it at least looks like an EvaluationReport.
    if (typeof parsed !== 'object') return null;
    return parsed as unknown as EvaluationReport;
  }, [app.evaluation_report_json]);

  const handleStatusChange = (newStatus: string | null) => {
    if (!newStatus) return;
    updateStatus.mutate(
      { id: app.id, data: { status: newStatus } },
      {
        onSuccess: () => toast.success(`Status updated to ${newStatus}`),
        onError: () => toast.error('Failed to update status'),
      }
    );
  };

  const matchLabel = (app.overall_score ?? 0) >= 70
    ? 'Strong Match'
    : (app.overall_score ?? 0) >= 55
      ? 'Good Match'
      : (app.overall_score ?? 0) >= 40
        ? 'Possible Match'
        : 'Weak Match';

  return (
    <div
      className="border-t border-border-default bg-bg-subtle px-5 py-5 space-y-5"
      onClick={(e) => e.stopPropagation()}
    >
      {/* ─── Zone 1: Action Bar ─── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <Select value={app.status} onValueChange={handleStatusChange}>
            <SelectTrigger className="w-36 h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_OPTIONS.map((s) => (
                <SelectItem key={s} value={s} className="text-xs">{STATUS_LABELS[s] || s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <StatusBadge status={app.status} />
        </div>
        {app.job_url && (
          <a
            href={app.job_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-brand hover:text-brand-hover transition-colors font-medium"
            onClick={(e) => e.stopPropagation()}
          >
            <ExternalLink className="h-3.5 w-3.5" />
            Open posting
          </a>
        )}
      </div>

      {/* ─── Zone 2: Score Summary ─── */}
      {app.overall_score != null && (
        <div className="rounded-xl border border-border-default bg-bg-card p-5 space-y-5">
          {/* Score header with circle + bars */}
          <div className="flex gap-6 items-start">
            {/* Left: overall score */}
            <div className="flex flex-col items-center gap-1 shrink-0">
              <ScoreCircle score={app.overall_score} size="lg" />
              <span className="text-[10px] font-medium text-text-muted mt-0.5">{matchLabel}</span>
            </div>

            {/* Right: dimension bars */}
            <div className="flex-1 min-w-0">
              <ScoreBars app={app} />
            </div>
          </div>

          {/* Score reasoning */}
          {app.score_reasoning && (
            <p className="text-xs text-text-tertiary leading-relaxed border-l-2 border-brand/30 pl-3">
              {app.score_reasoning}
            </p>
          )}

          {/* Strengths & gaps */}
          <StrengthsGaps strengths={app.key_strengths} gaps={app.key_gaps} />
        </div>
      )}

      {/* ─── Zone 3: Content Tabs ─── */}
      <Tabs defaultValue={evaluationReport ? 'evaluation' : 'description'} className="w-full">
        <TabsList variant="line" className="w-full justify-start border-b border-border-default gap-0">
          {evaluationReport && (
            <TabsTrigger value="evaluation" className="text-xs gap-1.5">
              <Compass className="h-3 w-3" />
              Evaluation
            </TabsTrigger>
          )}
          <TabsTrigger value="description" className="text-xs gap-1.5">
            <FileText className="h-3 w-3" />
            Description
          </TabsTrigger>
          {app.cover_letter && (
            <TabsTrigger value="cover-letter" className="text-xs gap-1.5">
              <Mail className="h-3 w-3" />
              Cover letter
            </TabsTrigger>
          )}
          {resumeTweaks && (
            <TabsTrigger value="resume" className="text-xs gap-1.5">
              <Pencil className="h-3 w-3" />
              Resume tweaks
            </TabsTrigger>
          )}
          {companyIntel && (
            <TabsTrigger value="intel" className="text-xs gap-1.5">
              <Building2 className="h-3 w-3" />
              Company background
            </TabsTrigger>
          )}
        </TabsList>

        {evaluationReport && (
          <TabsContent value="evaluation" className="mt-3">
            <div className="max-h-[560px] overflow-y-auto rounded-lg border border-border-default bg-bg-card p-4">
              <EvaluationReportView report={evaluationReport} />
            </div>
          </TabsContent>
        )}

        <TabsContent value="description" className="mt-3">
          <div className="relative">
            <div
              className="prose prose-sm max-w-none text-sm text-text-secondary max-h-[480px] overflow-y-auto leading-relaxed rounded-lg bg-bg-card border border-border-default p-4 [&_h4]:text-sm [&_li]:text-sm [&_li]:leading-relaxed [&_p]:text-sm [&_ol]:list-decimal [&_ol]:pl-5"
              dangerouslySetInnerHTML={{ __html: descriptionToHtml(app.description) }}
            />
          </div>
        </TabsContent>

        {app.cover_letter && (
          <TabsContent value="cover-letter" className="mt-3">
            <div className="relative rounded-lg bg-bg-card border border-border-default">
              <div className="flex items-center justify-end px-3 py-1.5 border-b border-border-default">
                <CopyButton text={app.cover_letter} label="Cover letter" />
              </div>
              <div className="text-sm text-text-secondary whitespace-pre-wrap max-h-[400px] overflow-y-auto p-4 leading-relaxed">
                {app.cover_letter}
              </div>
            </div>
          </TabsContent>
        )}

        {resumeTweaks && (
          <TabsContent value="resume" className="mt-3">
            <div className="text-sm text-text-secondary overflow-auto max-h-[400px] bg-bg-card p-4 rounded-lg border border-border-default">
              <KeyValueDisplay data={resumeTweaks} />
            </div>
          </TabsContent>
        )}

        {companyIntel && (
          <TabsContent value="intel" className="mt-3">
            <div className="text-sm text-text-secondary overflow-auto max-h-[400px] bg-bg-card p-4 rounded-lg border border-border-default">
              <KeyValueDisplay data={companyIntel} />
            </div>
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}
