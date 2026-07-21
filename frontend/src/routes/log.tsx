import { useState, type KeyboardEvent } from 'react';
import { createRoute, Link } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { StampDefs } from '@questboard/ui';
import { LaneStamp, laneDisplay } from '@/components/shared/lane-display';
import { useApplications, useCreateApplication, useLogEdit } from '@/hooks/use-applications';
import { useSourceLabels, resolveSourceLabel } from '@/hooks/use-scrapers';
import { useProfile } from '@/contexts/profile-context';
import { boardVertical, toBoardCard } from '@/utils/board-card';
import { ALL_VERTICALS } from '@/utils/board-verticals';
import {
  boardLogFilters,
  dismissSignup,
  followUpLine,
  hasLogValue,
  isApplied,
  isPersonal,
  isShelved,
  logDate,
  paidOut,
  paidTotal,
  parsePaidInput,
  personalLogFilters,
  readSignupState,
  reopenStatus,
  rowActions,
  saveSignupEmail,
  splitLog,
  withPaidOut,
  type SignupState,
} from '@/components/log/log-logic';
import type { ApplicationResponse } from '@/types/application';
import '@/components/log/log.css';

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/log',
  component: LogPage,
});

/* Your log, ported from packages/ui/reference/quest-board-mock.html
   (#page-log): the composer for personal quests, clipped and applied cards
   with status editing, the Done ledger with the paid total, the optional
   email row, and the chapter tail into the full ledger and the charts. */

function Composer({ profile }: { profile?: string }) {
  const create = useCreateApplication();
  const [value, setValue] = useState('');
  const [savedOnce, setSavedOnce] = useState(false);

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return;
    const title = value.trim();
    if (!title) return;
    create.mutate(
      { job_title: title, company: '', source: 'user', vertical: 'personal', profile },
      { onSuccess: () => setSavedOnce(true) },
    );
    setValue('');
  }

  return (
    <div className="qb-composer">
      <input
        placeholder="Add your own quest"
        aria-label="Add your own quest"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={onKeyDown}
      />
      {savedOnce && <div className="qb-comp-saved">Saved in this browser.</div>}
    </div>
  );
}

/* The optional email row. No mail goes out today, so the copy never claims
   one does: the address is kept in this browser until sync ships. */
function SignupRow() {
  const [state, setState] = useState<SignupState>(() => readSignupState(window.localStorage));
  const [email, setEmail] = useState('');
  const [rejected, setRejected] = useState(false);

  if (state === 'dismissed') return null;
  if (state === 'sent') {
    return (
      <div className="qb-signup">
        <span className="qb-grow">Saved. Sync ships later.</span>
      </div>
    );
  }

  function dismiss() {
    dismissSignup(window.localStorage);
    setState('dismissed');
  }

  if (state === 'email') {
    function save() {
      if (saveSignupEmail(window.localStorage, email)) {
        setState('sent');
      } else {
        setRejected(true);
      }
    }
    return (
      <div className="qb-signup">
        <span className="qb-grow">
          {rejected
            ? 'That does not look like an email address.'
            : 'It stays in this browser for now; sync ships later.'}
        </span>
        <input
          type="email"
          placeholder="Your email"
          aria-label="Your email"
          value={email}
          onChange={(event) => {
            setEmail(event.target.value);
            setRejected(false);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') save();
          }}
        />
        <button type="button" className="qb-btn-sage" onClick={save}>
          Save it
        </button>
        <button type="button" className="qb-plainbtn" onClick={dismiss}>
          Not now
        </button>
      </div>
    );
  }

  return (
    <div className="qb-signup">
      <span className="qb-grow">
        Your log lives in this browser. Add an email if you want it to survive a lost laptop.
      </span>
      <button type="button" className="qb-btn-sage" onClick={() => setState('email')}>
        Keep a copy
      </button>
      <button type="button" className="qb-plainbtn" onClick={dismiss}>
        Not now
      </button>
    </div>
  );
}

function LogCard({ app, labels }: { app: ApplicationResponse; labels: Record<string, string> }) {
  const edit = useLogEdit();
  const [asking, setAsking] = useState(false);
  const personal = isPersonal(app);
  const applied = isApplied(app);
  const shelved = isShelved(app);
  const actions = rowActions(app);
  const card = personal ? null : toBoardCard(app, resolveSourceLabel(app.source, labels));
  const vertical = personal ? 'personal' : card!.vertical;
  const date = logDate(app);
  const followUp = followUpLine(app);

  function markDone(raw: string) {
    const amount = parsePaidInput(raw);
    edit.mutate({
      id: app.id,
      data: amount
        ? { status: 'paid_out', quest_json: withPaidOut(app, amount) }
        : { status: 'attended' },
    });
    setAsking(false);
  }

  /* updated_at moves on every edit, so the date shown is the latest act:
     "shelved Jun 12" after a shelve, "written by you, Jul 8" fresh */
  const meta = personal
    ? shelved
      ? `written by you, shelved${date ? ` ${date}` : ''}`
      : `written by you${date ? `, ${date}` : ''}`
    : `via ${card!.meta || app.source}${shelved ? `, shelved${date ? ` ${date}` : ''}` : ''}`;

  return (
    <article className="qb-lcard">
      <div className="qb-stampcell">
        <LaneStamp vertical={vertical} size={28} />
      </div>
      <div>
        <div className="qb-ltitle">{personal ? app.job_title : card!.title}</div>
        <div className="qb-lmeta">{meta}</div>
        {followUp && <div className="qb-lnext">{followUp}</div>}
        {shelved && (
          <div className="qb-shelfnote">Miss a month and the quest stays where you left it.</div>
        )}
        <div className="qb-aff">
          {!personal && app.job_url && (
            <a
              className="qb-textlink"
              style={{ fontSize: 13 }}
              href={app.job_url}
              target="_blank"
              rel="noreferrer"
            >
              Apply at source
            </a>
          )}
          {asking ? (
            <input
              className="qb-affinput"
              autoFocus
              inputMode="numeric"
              placeholder="Paid something? Type the amount, or just press enter"
              aria-label="Paid amount, optional"
              onKeyDown={(event) => {
                if (event.key === 'Enter') markDone(event.currentTarget.value);
                if (event.key === 'Escape') setAsking(false);
              }}
            />
          ) : (
            actions.length > 0 && (
              <span className="qb-acts">
                {actions.includes('done') && (
                  <button type="button" onClick={() => setAsking(true)}>
                    Done
                  </button>
                )}
                {actions.includes('shelve') && (
                  <button
                    type="button"
                    onClick={() => edit.mutate({ id: app.id, data: { status: 'shelved' } })}
                  >
                    Shelve
                  </button>
                )}
                {actions.includes('reopen') && (
                  <button
                    type="button"
                    onClick={() => edit.mutate({ id: app.id, data: { status: reopenStatus(app) } })}
                  >
                    Reopen
                  </button>
                )}
                {/* back to 'found': out of the log, still on the board */}
                {actions.includes('remove') && (
                  <button
                    type="button"
                    onClick={() => edit.mutate({ id: app.id, data: { status: 'found' } })}
                  >
                    Remove
                  </button>
                )}
              </span>
            )
          )}
        </div>
      </div>
      <div className="qb-rightcol">
        {applied ? (
          <span className="qb-applied-stamp">{card?.applied ?? 'Applied'}</span>
        ) : card?.clippedDate ? (
          <span
            className="qb-applied-stamp"
            style={{ color: verticalHue(app), borderColor: verticalHue(app) }}
          >
            Clipped, {card.clippedDate}
          </span>
        ) : null}
        {card?.pay && (
          <span className="qb-lpay">
            {card.pay} {card.payUnit && <span className="qb-u">{card.payUnit}</span>}
          </span>
        )}
      </div>
    </article>
  );
}

function verticalHue(app: ApplicationResponse): string {
  return laneDisplay(boardVertical(app)).hue;
}

function DoneBlock({ done }: { done: ApplicationResponse[] }) {
  if (done.length === 0) return null;
  const year = new Date().getFullYear();
  const total = paidTotal(done, year);
  return (
    <div className="qb-done-block">
      <div className="qb-done-label">Done</div>
      {done.map((app) => {
        const amount = paidOut(app);
        return (
          <div key={app.id} className={amount ? 'qb-dline' : 'qb-dline qb-pending'}>
            <span className="qb-dd">{logDate(app) ?? ''}</span>
            <span className="qb-dt">{app.job_title}.</span>
            {amount !== null && <span className="qb-dn">${amount.toLocaleString('en-US')}.</span>}
          </div>
        );
      })}
      {total > 0 && (
        <div className="qb-ledger-total">
          Paid out in <span className="qb-num">{year}</span> so far:{' '}
          <span className="qb-num">${total.toLocaleString('en-US')}</span>. Counting only what
          landed.
        </div>
      )}
    </div>
  );
}

function useTotal(filters: Parameters<typeof useApplications>[0]): number | undefined {
  return useApplications({ ...filters, page: 1, page_size: 1 }).data?.total;
}

function ChapterTail({ profile }: { profile?: string }) {
  /* two live totals: the ledger's all-tracked career count and the
     applications that actually went out, across every board vertical */
  const tracked = useTotal({ profile });
  const out = useTotal({
    vertical: ALL_VERTICALS,
    status: 'applied,interviewing,offer',
    profile,
  });
  return (
    <div className="qb-log-tail">
      <div className="qb-tailstat">
        <div className="qb-tailnum">{tracked ?? ''}</div>
        <div className="qb-taillab">
          career {tracked === 1 ? 'job' : 'jobs'} tracked.{' '}
          <Link to="/log/ledger" search={{ run: undefined, scope: 'all' }} className="qb-textlink">
            The full ledger
          </Link>
        </div>
      </div>
      <div className="qb-tailstat">
        <div className="qb-tailnum">{out ?? ''}</div>
        <div className="qb-taillab">
          {out === 1 ? 'application' : 'applications'} out.{' '}
          <Link to="/log/numbers" className="qb-textlink">
            See the charts
          </Link>
        </div>
      </div>
    </div>
  );
}

function LogPage() {
  const labels = useSourceLabels();
  const { profile } = useProfile();
  const personal = useApplications(personalLogFilters(profile));
  const board = useApplications(boardLogFilters(profile));

  const loaded = personal.data !== undefined && board.data !== undefined;
  const split = splitLog(personal.data?.items ?? [], board.data?.items ?? []);

  return (
    <>
      <StampDefs />
      <div className="qb-logwrap">
        <div className="qb-log-head">
          <h1>Your log</h1>
          <div className="qb-log-status">Saved in this browser</div>
        </div>

        <Composer profile={profile} />

        {loaded && hasLogValue(split) && <SignupRow />}

        {(personal.isError || board.isError) && (
          <p className="qb-log-empty">
            Your log could not reach the backend. Start it with make dev and reload.
          </p>
        )}

        {loaded && split.active.length === 0 && split.done.length === 0 && (
          <p className="qb-log-empty">
            Nothing here yet. Clip a quest on{' '}
            <Link to="/board" className="qb-textlink">
              the board
            </Link>{' '}
            and it lands in your log, next to anything you write above.
          </p>
        )}

        <div className="qb-loglist">
          {split.active.map((app) => (
            <LogCard key={app.id} app={app} labels={labels} />
          ))}
        </div>

        <DoneBlock done={split.done} />

        <ChapterTail profile={profile} />

        <p className="qb-log-foot">Nothing here turns red. Nothing resets.</p>
      </div>
    </>
  );
}
