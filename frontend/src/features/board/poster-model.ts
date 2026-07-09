/* ApplicationResponse -> the poster's honest fields. Everything here is
   either the posting's own data (title, pay, dates, description) or the
   kind-level requirements model from kind-copy.ts; nothing is guessed in.
   The route composes the bring line's inline fit action itself. */

import { kindForVertical } from '@questboard/kinds';
import { toBoardCard, type BoardCardModel } from '@/utils/board-card';
import { kindCopy, type KindCopy } from '@/features/board/kind-copy';
import type { ApplicationResponse } from '@/types/application';

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

  const tags: string[] = [];
  if (app.is_remote) tags.push('remote');
  if (app.work_type && app.work_type !== 'unknown') tags.push(app.work_type);

  return {
    kind,
    card,
    desc: scannableDesc(app.description),
    copy,
    hasFit,
    tags: tags.slice(0, 2),
    rotateDeg: rotationFor(app.id),
  };
}
