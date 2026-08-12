/* The Jobs lane's detail sheet, at its own URL (?job={id}) so refresh and
   share reopen it. Shows the full stored description as plain text with its
   paragraphs kept, the stated facts with their provenance, and the door to
   the original posting. Nothing here is summarized or guessed. When the
   pipeline drafted materials for a row (cover letter, application kit,
   requirement check, company notes), they wait below the description in
   collapsed folds, each labeled as generated work to check; see
   detail-artifacts.tsx. A row without them looks exactly as before. */

import { PlainButton, Sheet, TextLink } from '@questboard/ui';
import { DetailArtifacts } from '@/features/board/detail-artifacts';
import { effortMarks, type QuestRequirements } from '@/features/board/quest-requirements';
import { toPoster } from '@/features/board/poster-model';
import { useApplication } from '@/hooks/use-applications';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { cleanDescription } from '@/utils/format';
import { formatStatedPay, payUnitFor } from '@/utils/board-card';
import { postedAgoLabel } from '@/utils/job-trust';
import type { ApplicationResponse } from '@/types/application';

/* last_checked_at is naive UTC like every pipeline timestamp; pin it so the
   date never drifts with the reader's timezone */
function checkedDate(value: string | null | undefined): string | null {
  if (!value) return null;
  let v = value.trim().replace(' ', 'T');
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(v)) v = `${v}Z`;
  const t = Date.parse(v);
  if (Number.isNaN(t)) return null;
  return new Date(t).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function FactRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="qb-jd-fact">
      <span className="qb-jd-fact-label">{label}</span>
      <span className="qb-jd-fact-value">{value}</span>
    </div>
  );
}

function questString(app: ApplicationResponse, key: string): string {
  const value = app.quest?.[key];
  return typeof value === 'string' ? value.trim() : '';
}

function dateOnlyLabel(value: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return null;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function Facts({ app, sourceLabel }: { app: ApplicationResponse; sourceLabel: string }) {
  const pay = formatStatedPay(app.salary_min, app.salary_max, app.salary_currency);
  const payUnit = payUnitFor(app);
  const payValue = pay
    ? [pay, payUnit].filter(Boolean).join(' ') +
      (app.salary_source === 'reported' ? ', as the posting states it' : '')
    : 'not stated';
  const place = app.is_remote ? 'remote' : app.location || '';
  const posted = postedAgoLabel(app.date_posted, app.date_confidence);
  const source = sourceLabel + (app.direct_from_company ? ', direct from the company' : '');
  const checked = checkedDate(app.last_checked_at);
  const applyBy = questString(app, 'apply_by');
  const deadline = applyBy ? dateOnlyLabel(applyBy) : app.is_rolling ? 'rolling' : null;
  return (
    <div className="qb-jd-facts">
      <FactRow label="pay" value={payValue} />
      {place && <FactRow label="place" value={place} />}
      {posted && <FactRow label="posted" value={posted.toLowerCase()} />}
      {deadline && <FactRow label="apply by" value={deadline} />}
      <FactRow label="source" value={source} />
      {checked && (
        <FactRow
          label="last checked"
          value={checked + (app.url_status === 'dead' ? ', the link did not answer' : '')}
        />
      )}
    </div>
  );
}

function QuestRequirementsPanel({ requirements }: { requirements: QuestRequirements }) {
  const marks = effortMarks(requirements.effort.level);
  const effortBasis = requirements.effort.basis === 'listed'
    ? 'Based on the steps listed for this quest.'
    : 'Typical for this kind of quest; the posting did not state every step.';
  const criteriaBasis = requirements.criteria.basis === 'listed'
    ? 'These requirements are listed for this quest.'
    : 'These are typical requirements for this kind of quest.';

  return (
    <section className="qb-jd-quest" aria-labelledby="qb-jd-quest-title">
      <div className="qb-jd-quest-head">
        <div>
          <span className="qb-jd-quest-kicker">application effort</span>
          <div className="qb-jd-effort-line">
            <span className="qb-jd-effort-marks" aria-hidden="true">
              {[1, 2, 3].map((mark) => (
                <i key={mark} className={mark <= marks ? 'is-filled' : undefined} />
              ))}
            </span>
            <strong id="qb-jd-quest-title">{requirements.effort.label}</strong>
            <span>· {requirements.effort.time}</span>
          </div>
        </div>
        <span className="qb-jd-basis">
          {requirements.effort.basis === 'listed' ? 'listed steps' : 'typical estimate'}
        </span>
      </div>
      <p className="qb-jd-effort-note">{requirements.effort.note}</p>
      <p className="qb-jd-method">
        {effortBasis} This estimates setup and application work—not your odds, approval time,
        or the time needed to complete the quest.
      </p>

      <h4>Criteria</h4>
      <ul className="qb-jd-criteria">
        {requirements.criteria.items.map((item) => <li key={item}>{item}</li>)}
      </ul>
      <p className="qb-jd-method">
        {criteriaBasis} Confirm the complete eligibility rules on the original posting.
      </p>
    </section>
  );
}

export function JobDetailSheet({
  jobId,
  labels,
  onClose,
}: {
  jobId: number | null;
  labels: Record<string, string>;
  onClose: () => void;
}) {
  const { data: app, isError } = useApplication(jobId ?? 0);
  const open = jobId !== null;
  const poster = open && app ? toPoster(app, resolveSourceLabel(app.source, labels)) : null;
  const card = poster?.card ?? null;
  /* rows scraped before the pipeline cleaned text can carry markup junk;
     cleanDescription keeps the newlines, so pre-wrap still shows paragraphs */
  const desc = app ? cleanDescription(app.description) : '';

  return (
    <Sheet
      open={open}
      onClose={onClose}
      label={poster?.requirements ? 'Quest details' : 'Job details'}
      title={card?.title}
      meta={card?.meta}
    >
      {open && isError && (
        <p className="qb-hint">This posting is not on the board anymore.</p>
      )}
      {open && app && card && (
        <>
          <Facts app={app} sourceLabel={resolveSourceLabel(app.source, labels)} />
          {poster?.requirements && <QuestRequirementsPanel requirements={poster.requirements} />}
          {desc ? (
            <div className="qb-jd-desc">{desc}</div>
          ) : (
            <p className="qb-hint">
              No stored description for this one; the original posting has the full text.
            </p>
          )}
          <DetailArtifacts app={app} />
          <div className="qb-srow">
            {app.job_url && <TextLink href={app.job_url}>View original posting</TextLink>}
            <PlainButton className="qb-closebtn" onClick={onClose}>
              Done for now
            </PlainButton>
          </div>
        </>
      )}
    </Sheet>
  );
}
