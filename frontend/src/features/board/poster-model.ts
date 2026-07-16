/* ApplicationResponse -> the poster's honest fields. Everything here is
   either the posting's own data (title, pay, dates, description) or the
   kind-level requirements model from kind-copy.ts; nothing is guessed in.
   The route composes the bring line's inline fit action itself. */

import { kindForVertical } from '@questboard/kinds';
import { cleanCompany, toBoardCard, type BoardCardModel } from '@/utils/board-card';
import { kindCopy, type KindCopy } from '@/features/board/kind-copy';
import { getCompanyLogoUrl } from '@/utils/company-domains';
import { avatarColor } from '@/utils/colors';
import type { ApplicationResponse } from '@/types/application';

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
  rotateDeg: number;
  /** the company/source logo, resolved from the poster's own company + url */
  logoUrl?: string;
  /** career rows only: the 40px logo well beside the title */
  logoWell?: PosterLogoWell;
}

/** First sentence of the posting's own description, capped for scanning.
    No text, no line: never summarized by a model, never invented. */
export function scannableDesc(description: string | null | undefined): string | undefined {
  const text = (description ?? '').replace(/\s+/g, ' ').trim();
  if (!text) return undefined;
  const sentence = text.split(/(?<=[.!?])\s/)[0] ?? text;
  const cut = sentence.length > 140 ? `${sentence.slice(0, 137).trimEnd()}…` : sentence;
  return cut;
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
    rotateDeg: rotationFor(app.id),
    logoUrl: logoWell ? undefined : logoUrl,
    logoWell,
  };
}
