/* ApplicationResponse -> the poster's honest fields. Everything here is
   either the posting's own data (title, pay, dates, description) or the
   kind-level requirements model from kind-copy.ts; nothing is guessed in.
   The route composes the bring line's inline fit action itself. */

import { kindForVertical } from '@questboard/kinds';
import { cleanDescription } from '@/utils/format';
import { cleanCompany, toBoardCard, type BoardCardModel } from '@/utils/board-card';
import { kindCopy, type KindCopy } from '@/features/board/kind-copy';
import {
  requirementsForQuest,
  type QuestRequirements,
} from '@/features/board/quest-requirements';
import { getCompanyLogoUrl } from '@/utils/company-domains';
import { avatarColor } from '@/utils/colors';
import type { AgentFitVerdict, ApplicationResponse } from '@/types/application';

/** The career poster's fixed logo tile; the monogram fallback derives
    deterministically from the company name (CompanyAvatar's pattern). */
export interface PosterLogoWell {
  src?: string;
  initial: string;
  color: string;
}

export interface PosterModel {
  kind: string;
  card: BoardCardModel;
  /** the scannable one-liner, cut from the posting's own text */
  desc?: string;
  copy: KindCopy;
  /** true when the career fit line replaces the kind template */
  hasFit: boolean;
  tags: string[];
  /** setup/application effort and criteria; Side Quests only */
  requirements?: QuestRequirements;
  rotateDeg: number;
  /** the company/source logo, resolved from the poster's own company + url */
  logoUrl?: string;
  /** career rows only: the 40px logo well beside the title */
  logoWell?: PosterLogoWell;
  /** the connected assistant's fit verdict for this row, from its last run */
  fitBadge?: { label: string; verdict: 'strong' | 'good' | 'reach' | 'skip' };
  /** fast offline skill-coverage hint, shown until the agent's verdict lands */
  skillBadge?: { label: string; band: 'close' | 'partial' | 'weak' };
}

/** The fast skill-coverage hint as a light poster badge, or undefined. */
export function skillBadgeFor(app: ApplicationResponse): PosterModel['skillBadge'] {
  const lf = app.local_fit;
  if (!lf || lf.skill_count < 1) return undefined;
  const n = lf.skill_count;
  return { label: `${n} skill${n === 1 ? '' : 's'} match`, band: lf.band };
}

const FIT_WORD: Record<'strong' | 'good' | 'reach' | 'skip', string> = {
  strong: 'strong fit',
  good: 'good fit',
  reach: 'a reach',
  skip: 'skip',
};

/** The assistant's verdict as a clear poster badge, or undefined. */
export function fitBadgeFor(app: ApplicationResponse): PosterModel['fitBadge'] {
  const fit = app.agent_fit;
  if (!fit) return undefined;
  const word = FIT_WORD[fit.verdict];
  const label = fit.verdict !== 'skip' && fit.rank ? `#${fit.rank} · ${word}` : word;
  return { label, verdict: fit.verdict };
}

/* ---- fit order: the wall's grouping when the assistant has ranked ----
   The API's roles feed floats ranked rows first but ignores the sort param
   and never sends skips last, so the wall does the residual ordering here.
   Pure and structural: poster-wall hands in the loaded rows, nothing else. */

type FitRow = { agent_fit?: { verdict: AgentFitVerdict; rank: number | null } | null };
type FitVerdictShown = Exclude<AgentFitVerdict, 'skip'>;

const FIT_GROUP_ORDER: readonly FitVerdictShown[] = ['strong', 'good', 'reach'];
const FIT_GROUP_LABEL: Record<FitVerdictShown, string> = {
  strong: 'Strong fit',
  good: 'Good fit',
  reach: 'Worth a reach',
};

export interface FitGroup<T> {
  verdict: FitVerdictShown;
  label: string;
  items: T[];
}

export interface FitWall<T> {
  /** verdict groups in strong/good/reach order; empty groups omitted */
  groups: FitGroup<T>[];
  /** rows the assistant never judged, original order, after the groups */
  unranked: T[];
  /** verdict skip, last; these fold away rather than hang on the wall */
  skips: T[];
}

/* rank asc, unranked members after ranked ones, original order as the tie */
function byRankThenPosition<T>(rows: { row: T; rank: number | null; i: number }[]): T[] {
  return rows
    .sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.i - b.i)
    .map((e) => e.row);
}

/** The loaded rows in the assistant's fit order, grouped for the wall. */
export function fitGroups<T extends FitRow>(items: T[]): FitWall<T> {
  const byVerdict = new Map<AgentFitVerdict, { row: T; rank: number | null; i: number }[]>();
  const unranked: T[] = [];
  items.forEach((row, i) => {
    const fit = row.agent_fit;
    if (!fit) {
      unranked.push(row);
      return;
    }
    const bucket = byVerdict.get(fit.verdict) ?? [];
    bucket.push({ row, rank: fit.rank, i });
    byVerdict.set(fit.verdict, bucket);
  });
  const groups = FIT_GROUP_ORDER.filter((v) => byVerdict.has(v)).map((verdict) => ({
    verdict,
    label: FIT_GROUP_LABEL[verdict],
    items: byRankThenPosition(byVerdict.get(verdict)!),
  }));
  return { groups, unranked, skips: byRankThenPosition(byVerdict.get('skip') ?? []) };
}

/** "Your assistant ranked 12 jobs: 6 strong, 4 good, 2 reach." Zero groups
    stay out; null when nothing but skips carries a verdict (the fold's own
    count tells that story). */
export function fitDigest<T>(wall: FitWall<T>): string | null {
  const parts = wall.groups.map((g) => `${g.items.length} ${g.verdict}`);
  const n = wall.groups.reduce((sum, g) => sum + g.items.length, 0);
  if (n === 0) return null;
  return `Your assistant ranked ${n} job${n === 1 ? '' : 's'}: ${parts.join(', ')}.`;
}

/* date_found comes back as naive UTC (new-since pins the same way): fix the
   zone so the order never drifts with the reader's timezone */
function foundAtMs(value: string | null | undefined): number | null {
  if (!value) return null;
  let v = value.trim().replace(' ', 'T');
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(v)) v = `${v}Z`;
  const t = Date.parse(v);
  return Number.isNaN(t) ? null : t;
}

/** The loaded rows by date_found desc, unknown dates last, ties in the given
    order. The roles API keeps ranked rows first whatever sort it is asked
    for, so an explicit "newly found" pick re-orders the loaded rows here. */
export function newestFirst<T extends { date_found: string | null }>(items: T[]): T[] {
  return items
    .map((row, i) => ({ row, i, t: foundAtMs(row.date_found) }))
    .sort((a, b) => {
      if (a.t === b.t) return a.i - b.i;
      if (a.t === null) return 1;
      if (b.t === null) return -1;
      return b.t - a.t;
    })
    .map((e) => e.row);
}

/** First sentence of the posting's own description, capped for scanning.
    No text, no line: never summarized by a model, never invented. */
export function scannableDesc(description: string | null | undefined): string | undefined {
  /* rows scraped before the pipeline cleaned text can carry markup junk;
     strip it here so the excerpt never shows it */
  const text = cleanDescription(description ?? '').replace(/\s+/g, ' ').trim();
  if (!text) return undefined;
  // Return a clean word-boundary lead and let the card's 2-line CSS clamp do
  // the visual cut (it adds its own ellipsis). A JS character cut here fought
  // the clamp and left mid-word fragments like "...Okta Data Engineer to".
  if (text.length <= 200) return text;
  const slice = text.slice(0, 200);
  const lastSpace = slice.lastIndexOf(' ');
  return (lastSpace > 60 ? slice.slice(0, lastSpace) : slice).replace(/[,;:.]$/, '');
}

function statedStr(quest: ApplicationResponse['quest'], key: string): string {
  const v = quest?.[key];
  return typeof v === 'string' ? v.trim() : '';
}

/** Stable per-posting tilt so the wall reads tacked-up, not animated. */
export function rotationFor(id: number): number {
  const steps = [-1.4, -1.1, -0.7, 0.6, 0.9, 1.2, 1.4];
  return steps[Math.abs(id) % steps.length];
}

export function toPoster(app: ApplicationResponse, sourceLabel: string): PosterModel {
  const kind = kindForVertical(app.vertical || 'career')?.id ?? 'skill';
  const card = toBoardCard(app, sourceLabel);
  const hasFit = Boolean(card.fit && card.fit.total > 0);

  let copy = kindCopy(kind);
  /* a career job with no fit report yet still asks for a resume, never the
     gig-tier template */
  if ((app.vertical || 'career') === 'career' && !hasFit) {
    copy = { ...copy, bring: 'a resume' };
  }
  /* the source-stated beginner signal beats the kind template */
  if (!hasFit && card.firstQuest) {
    copy = { bring: 'nothing you don’t already have', bringFree: true, catchLine: copy.catchLine };
  }
  /* a row's own stated bring/catch beats any template: curated sources
     (flip on-ramps) state the real fee as the catch, so the card never
     shows a kind-generic line when the source said the specific thing */
  const statedBring = statedStr(app.quest, 'bring');
  const statedCatch = statedStr(app.quest, 'catch');
  if (statedBring) copy = { ...copy, bring: statedBring };
  if (statedCatch) copy = { ...copy, catchLine: statedCatch };

  // Location already reads on the meta line, so "remote" never doubles as a
  // tag. Career rows carry no flavor tags; a quest keeps its work type only
  // when it adds something the meta doesn't (hybrid/onsite, never "remote").
  const isCareer = (app.vertical || 'career') === 'career';
  const wt = (app.work_type || '').trim();
  const tags: string[] = isCareer
    ? (app.match_bucket === 'adjacent' ? ['adjacent match'] : [])
    : (!wt || wt === 'unknown' || wt.toLowerCase() === 'remote' ? [] : [wt]);

  const company = cleanCompany(app.company);
  const logoUrl = getCompanyLogoUrl(company, 64, app.job_url) ?? undefined;
  /* career posters carry the fixed logo well; quests keep the small giver
     logo. The well needs a real company name for its monogram fallback. */
  const logoWell: PosterLogoWell | undefined =
    isCareer && company
      ? { src: logoUrl, initial: company[0].toUpperCase(), color: avatarColor(company) }
      : undefined;

  return {
    kind,
    card,
    desc: scannableDesc(app.description),
    copy,
    hasFit,
    tags: tags.slice(0, 2),
    requirements: requirementsForQuest(app, kind, copy.bring) ?? undefined,
    rotateDeg: rotationFor(app.id),
    logoUrl: logoWell ? undefined : logoUrl,
    logoWell,
    fitBadge: fitBadgeFor(app),
    skillBadge: skillBadgeFor(app),
  };
}
