/* The generated work the pipeline stored for a job, folded below the
   sheet's description: a draft cover letter, the application kit, the
   requirement check, and company notes. Every fold is collapsed until
   opened and opens with a caveat naming it generated work, because the
   sheet's facts above are stated and these are drafts. A row without
   artifacts renders nothing at all. Bad JSON also renders nothing; the
   sheet never breaks over a malformed row.

   The legacy 7-dimension scores, the match score, and the
   Strong Apply / Apply / Maybe / Skip recommendation are deliberately
   absent. PRODUCT.md forbids presenting the deterministic score as a fit
   verdict; on the board only the agent verdict system speaks to fit. */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { parseReport } from '@/utils/board-card';
import type { ApplicationResponse, RequirementMatch } from '@/types/application';
import '@/features/board/detail-artifacts.css';

/* ---------- defensive parsing: bad JSON reads as absent ---------- */

function parseObject(json: string | null | undefined): Record<string, unknown> | null {
  if (!json) return null;
  try {
    const parsed: unknown = JSON.parse(json);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed as Record<string, unknown>;
  } catch {
    return null;
  }
}

function asText(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function asTextList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(asText).filter((v): v is string => v !== null);
}

interface KitBullet {
  to: string;
  from: string | null;
}

interface Kit {
  title: string | null;
  summary: string | null;
  bullets: KitBullet[];
  keywords: string[];
  emphasize: string[];
  atsNotes: string[];
}

/* resume_tweaks_json holds a ResumeOptimization; every field optional */
function parseKit(json: string | null | undefined): Kit | null {
  const raw = parseObject(json);
  if (!raw) return null;
  const bullets: KitBullet[] = Array.isArray(raw.bullet_tweaks)
    ? (raw.bullet_tweaks as unknown[])
        .map((item) => {
          if (!item || typeof item !== 'object') return null;
          const tweak = item as Record<string, unknown>;
          const to = asText(tweak.tweaked_bullet);
          if (!to) return null;
          return { to, from: asText(tweak.original_bullet) };
        })
        .filter((b): b is KitBullet => b !== null)
    : [];
  const kit: Kit = {
    title: asText(raw.title_suggestion),
    summary: asText(raw.summary_rewrite),
    bullets,
    keywords: asTextList(raw.keywords_to_add),
    emphasize: asTextList(raw.sections_to_emphasize),
    atsNotes: asTextList(raw.ats_compatibility_notes),
  };
  const usable =
    kit.title ||
    kit.summary ||
    kit.bullets.length ||
    kit.keywords.length ||
    kit.emphasize.length ||
    kit.atsNotes.length;
  return usable ? kit : null;
}

/* evaluation_report_json rows with a stated requirement; nothing else */
function parseRequirements(json: string | null | undefined): RequirementMatch[] {
  const report = parseReport(json);
  if (!report) return [];
  return report.requirements.filter(
    (row): row is RequirementMatch =>
      !!row && typeof row === 'object' && asText((row as RequirementMatch).requirement) !== null,
  );
}

interface NoteRow {
  label: string;
  value: string | null;
  items: string[];
}

/* company_intel_json flattened to plain rows; nested objects are skipped */
function parseNotes(json: string | null | undefined): NoteRow[] {
  const raw = parseObject(json);
  if (!raw) return [];
  const rows: NoteRow[] = [];
  for (const [key, value] of Object.entries(raw)) {
    const label = key.replace(/_/g, ' ').trim().toLowerCase();
    if (!label) continue;
    if (typeof value === 'string') {
      const text = asText(value);
      if (text) rows.push({ label, value: text, items: [] });
    } else if (typeof value === 'number' || typeof value === 'boolean') {
      rows.push({ label, value: String(value), items: [] });
    } else if (Array.isArray(value)) {
      const items = asTextList(value);
      if (items.length) rows.push({ label, value: null, items });
    }
    /* objects and nulls fall through unrendered */
  }
  return rows;
}

/* ---------- small furniture ---------- */

/* The same copy affordance the ledger's detail view carries, in the
   board's quiet grammar: a text button that reads Copied for a moment. */
function CopyLink({ text, what }: { text: string; what: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const onCopy = () => {
    const clipboard = navigator.clipboard;
    if (!clipboard?.writeText) return;
    void clipboard.writeText(text).then(() => {
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      type="button"
      className="qb-textlink qb-jda-copy"
      aria-label={`Copy ${what}`}
      onClick={onCopy}
    >
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function Fold({
  name,
  count,
  caveat,
  children,
}: {
  name: string;
  count?: number;
  caveat: string;
  children: ReactNode;
}) {
  return (
    <details className="qb-jda">
      <summary>
        <span className="qb-jda-name">{name}</span>
        {count !== undefined && <span className="qb-jda-count">{count}</span>}
      </summary>
      <div className="qb-jda-body">
        <p className="qb-jda-caveat">{caveat}</p>
        {children}
      </div>
    </details>
  );
}

function KitRow({
  label,
  copyText,
  copyWhat,
  children,
}: {
  label: string;
  copyText?: string;
  copyWhat?: string;
  children: ReactNode;
}) {
  return (
    <div className="qb-jda-row">
      <div className="qb-jda-rowhead">
        <span className="qb-jda-label">{label}</span>
        {copyText && copyWhat && <CopyLink text={copyText} what={copyWhat} />}
      </div>
      {children}
    </div>
  );
}

/* ---------- the folds ---------- */

export function DetailArtifacts({ app }: { app: ApplicationResponse }) {
  const letter = asText(app.cover_letter);
  const kit = parseKit(app.resume_tweaks_json);
  const requirements = parseRequirements(app.evaluation_report_json);
  const notes = parseNotes(app.company_intel_json);

  if (!letter && !kit && requirements.length === 0 && notes.length === 0) return null;

  return (
    <div className="qb-jda-stack">
      {letter && (
        <Fold
          name="draft cover letter"
          caveat="A generated draft. Check it before sending; company facts in it are not verified."
        >
          <div className="qb-jda-rowhead qb-jda-lonecopy">
            <CopyLink text={letter} what="cover letter" />
          </div>
          <div className="qb-jda-text">{letter}</div>
        </Fold>
      )}

      {kit && (
        <Fold
          name="application kit"
          caveat="Generated materials to paste by hand. Nothing is sent for you."
        >
          {kit.title && (
            <KitRow label="suggested title" copyText={kit.title} copyWhat="suggested title">
              <div className="qb-jda-value">{kit.title}</div>
            </KitRow>
          )}
          {kit.summary && (
            <KitRow label="summary rewrite" copyText={kit.summary} copyWhat="summary rewrite">
              <div className="qb-jda-value">{kit.summary}</div>
            </KitRow>
          )}
          {kit.bullets.map((bullet, i) => (
            <KitRow
              key={i}
              label={kit.bullets.length > 1 ? `bullet rewrite ${i + 1}` : 'bullet rewrite'}
              copyText={bullet.to}
              copyWhat={kit.bullets.length > 1 ? `bullet rewrite ${i + 1}` : 'bullet rewrite'}
            >
              <div className="qb-jda-value">{bullet.to}</div>
              {bullet.from && <p className="qb-jda-sub">was: {bullet.from}</p>}
            </KitRow>
          ))}
          {kit.keywords.length > 0 && (
            <KitRow
              label="keywords to add"
              copyText={kit.keywords.join(', ')}
              copyWhat="keywords to add"
            >
              <div className="qb-jda-value">{kit.keywords.join(', ')}</div>
            </KitRow>
          )}
          {kit.emphasize.length > 0 && (
            <KitRow label="sections to emphasize">
              <div className="qb-jda-value">{kit.emphasize.join(', ')}</div>
            </KitRow>
          )}
          {kit.atsNotes.length > 0 && (
            <KitRow label="ats notes">
              {kit.atsNotes.map((note, i) => (
                <p key={i} className="qb-jda-value qb-jda-line">
                  {note}
                </p>
              ))}
            </KitRow>
          )}
        </Fold>
      )}

      {requirements.length > 0 && (
        <Fold
          name="requirement check"
          count={requirements.length}
          caveat="A generated mapping of the posting's requirements to your resume. Check the quotes yourself."
        >
          <ul className="qb-jda-reqs">
            {requirements.map((row, i) => (
              <li key={i} className="qb-jda-req">
                <span className="qb-jda-strength">
                  {row.strength === 'strong' || row.strength === 'partial' || row.strength === 'missing'
                    ? row.strength
                    : ''}
                </span>
                <div className="qb-jda-reqbody">
                  <div className="qb-jda-value">{row.requirement}</div>
                  {asText(row.evidence) && <p className="qb-jda-quote">{row.evidence}</p>}
                  {asText(row.mitigation) && <p className="qb-jda-sub">{row.mitigation}</p>}
                </div>
              </li>
            ))}
          </ul>
        </Fold>
      )}

      {notes.length > 0 && (
        <Fold
          name="company notes"
          caveat="Generated notes, not verified facts. Check anything before repeating it."
        >
          {notes.map((row) => (
            <div key={row.label} className="qb-jda-row">
              <span className="qb-jda-label">{row.label}</span>
              {row.value !== null ? (
                <div className="qb-jda-value">{row.value}</div>
              ) : (
                row.items.map((item, i) => (
                  <p key={i} className="qb-jda-value qb-jda-line">
                    {item}
                  </p>
                ))
              )}
            </div>
          ))}
        </Fold>
      )}
    </div>
  );
}
