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
import { useApplication } from '@/hooks/use-applications';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { formatStatedPay, payUnitFor, toBoardCard } from '@/utils/board-card';
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

function Facts({ app, sourceLabel }: { app: ApplicationResponse; sourceLabel: string }) {
  const pay = formatStatedPay(app.salary_min, app.salary_max);
  const payUnit = payUnitFor(app);
  const payValue = pay
    ? [pay, payUnit].filter(Boolean).join(' ') +
      (app.salary_source === 'reported' ? ', as the posting states it' : '')
    : 'not stated';
  const place = app.is_remote ? 'remote' : app.location || '';
  const posted = postedAgoLabel(app.date_posted, app.date_confidence);
  const source = sourceLabel + (app.direct_from_company ? ', direct from the company' : '');
  const checked = checkedDate(app.last_checked_at);
  return (
    <div className="qb-jd-facts">
      <FactRow label="pay" value={payValue} />
      {place && <FactRow label="place" value={place} />}
      {posted && <FactRow label="posted" value={posted.toLowerCase()} />}
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
  const card = open && app ? toBoardCard(app, resolveSourceLabel(app.source, labels)) : null;

  return (
    <Sheet
      open={open}
      onClose={onClose}
      label="Job details"
      title={card?.title}
      meta={card?.meta}
    >
      {open && isError && (
        <p className="qb-hint">This posting is not on the board anymore.</p>
      )}
      {open && app && card && (
        <>
          <Facts app={app} sourceLabel={resolveSourceLabel(app.source, labels)} />
          {app.description.trim() ? (
            <div className="qb-jd-desc">{app.description.trim()}</div>
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
