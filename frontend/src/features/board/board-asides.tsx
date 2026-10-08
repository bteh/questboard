/* Board furniture that is not the board itself: the requirement sheet,
   the house rules note, and the first-run notice. */

import { useState, type ReactNode } from 'react';
import { LedgerRow, PlainButton, Sheet, TextLink } from '@questboard/ui';
import { useUpdateStatus } from '@/hooks/use-applications';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { dismissNotice, noticeDismissed } from '@/components/board/board-state';
import { CLIP_STATUS, toBoardCard } from '@/utils/board-card';
import type { ApplicationResponse, RequirementMatch } from '@/types/application';

function verdict(strength: RequirementMatch['strength']): ReactNode {
  if (strength === 'strong') return <span style={{ color: 'var(--sage)' }}>in your resume</span>;
  if (strength === 'partial') return <span style={{ color: 'var(--mute)' }}>partial</span>;
  return <span style={{ color: 'var(--mute)' }}>not in your resume yet</span>;
}

export function HouseRules() {
  return (
    <aside className="qb-house">
      <h4>House rules</h4>
      <p>Every quest links to its source. Pay is only what the poster states, never a guess.</p>
      <p>No MLMs, no pay-to-start, nothing adult. The risky ones carry their catch in plain words.</p>
      <p className="qb-house-sig">If it's pinned here, it's real.</p>
    </aside>
  );
}

export function RequirementSheet({
  app,
  labels,
  onClose,
}: {
  app: ApplicationResponse | null;
  labels: Record<string, string>;
  onClose: () => void;
}) {
  const updateStatus = useUpdateStatus();
  /* the mutation's response is the server's own updated row, so a clip made
     inside the sheet flips the footer without waiting for a refetch */
  const effective =
    app && updateStatus.data && updateStatus.data.id === app.id ? updateStatus.data : app;
  const card = effective ? toBoardCard(effective, resolveSourceLabel(effective.source, labels)) : null;
  return (
    <Sheet
      open={app !== null}
      onClose={onClose}
      label="Requirements against your resume"
      title={card?.title}
      meta={card ? `${card.meta ? `${card.meta}, ` : ''}covers ${card.fit?.strong ?? 0} of ${card.fit?.total ?? 0} requirements` : undefined}
    >
      {effective && card?.report && (
        <>
          <div
            style={{
              border: '1px solid var(--hair)',
              borderBottomColor: 'var(--edge)',
              borderRadius: 10,
              background: 'var(--paper)',
              padding: '14px 18px',
              marginTop: 14,
              maxHeight: '46vh',
              overflowY: 'auto',
            }}
          >
            <div className="qb-fb-label">From the posting, read against your resume</div>
            {card.report.requirements.map((req, i) => (
              <LedgerRow key={i} title={req.requirement} pay={verdict(req.strength)} />
            ))}
          </div>
          <div className="qb-srow">
            {effective.job_url && <TextLink href={effective.job_url}>Apply at source</TextLink>}
            {card.applied ? (
              <span className="qb-applied-stamp">{card.applied}</span>
            ) : card.clippedDate ? (
              <span className="qb-applied-stamp" style={{ color: 'var(--sage)' }}>
                Clipped, {card.clippedDate}
              </span>
            ) : (
              <PlainButton
                onClick={() =>
                  updateStatus.mutate({ id: effective.id, data: { status: CLIP_STATUS } })
                }
              >
                Clip
              </PlainButton>
            )}
            <PlainButton className="qb-closebtn" onClick={onClose}>
              Done for now
            </PlainButton>
          </div>
        </>
      )}
    </Sheet>
  );
}

/* "Never done any of this?" One honest door: the no-experience preset,
   backed by the source-stated first_quest_ok flag. Dismissal is stored
   locally and never asked about again. */
export function FirstRunNotice({ onStartHere }: { onStartHere: () => void }) {
  const [gone, setGone] = useState(() => noticeDismissed());
  if (gone) return null;
  return (
    <div className="qb-board-notice">
      <span>
        Never done any of this? Most quests here need nothing you don't already have.{' '}
        <button type="button" className="qb-textlink" style={{ fontSize: 14 }} onClick={onStartHere}>
          Start here
        </button>
      </span>
      <button
        type="button"
        className="qb-dismiss"
        onClick={() => {
          dismissNotice();
          setGone(true);
        }}
      >
        Dismiss
      </button>
    </div>
  );
}
