/**
 * The "Explain this" sheet. The machinery behind it has no name here.
 *
 * Locked shape: title and meta, then the one result block (quick read renders
 * instantly, the full read upgrades it in place), then whatever the tier
 * allows under it: the first-time consent card, the quiet progress line, or
 * nothing at all. Phones and weak machines get the quick read and total
 * silence about anything fuller.
 */

import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { ConsentCard, ExplainNote, PlainButton, SageButton, Sheet, TextLink } from '@questboard/ui';
import type { ApplicationResponse } from '@/types/application';
import { resolveSourceLabel } from '@/hooks/use-scrapers';
import { toBoardCard } from '@/utils/board-card';
import {
  buildFullReadPrompt,
  currentTier,
  ExplainController,
  getEngine,
  quickRead,
  type ExplainViewState,
} from '@/lib/ai';

const IDLE: ExplainViewState = {
  body: '',
  method: '',
  view: 'none',
  pct: 0,
  swap: 0,
};

function useControllerState(controller: ExplainController | null): ExplainViewState {
  const subscribe = useCallback(
    (onChange: () => void) => (controller ? controller.subscribe(onChange) : () => {}),
    [controller],
  );
  return useSyncExternalStore(subscribe, () => (controller ? controller.getState() : IDLE));
}

function ConsentArea({
  state,
  onStart,
  onNotNow,
}: {
  state: ExplainViewState;
  onStart: () => void;
  onNotNow: () => void;
}) {
  if (state.view === 'offer') {
    return (
      <ConsentCard
        title="First time only."
        body={
          <>
            Your computer can do this work itself, so it's free and nothing you type leaves it.
            One download first, about <span className="qb-num">1.1 GB</span>, the size of a movie.
          </>
        }
        actions={
          <>
            <SageButton onClick={onStart}>Start the download</SageButton>
            <PlainButton onClick={onNotNow}>Not now</PlainButton>
          </>
        }
        foot="Remove it any time in Settings."
      />
    );
  }
  if (state.view === 'progress') {
    return (
      <ConsentCard
        body={
          <>
            On its way, <span className="qb-num">{state.pct}%</span>. Keep browsing, it finishes
            on its own.
          </>
        }
      />
    );
  }
  if (state.view === 'done') {
    return <ConsentCard foot="Done. Full reads from here on. It never downloads again." />;
  }
  if (state.view === 'settings-note') {
    return <ConsentCard foot="The full read is in Settings whenever you want it." />;
  }
  return null;
}

export function ExplainSheet({
  app,
  labels,
  onClose,
}: {
  app: ApplicationResponse | null;
  labels: Record<string, string>;
  onClose: () => void;
}) {
  /* the quick read is computed synchronously at construction, so the answer
     is in the very first paint; the engine and tier resolve behind it */
  const controller = useMemo(
    () =>
      app
        ? new ExplainController(
            {
              quickBody: quickRead(app, resolveSourceLabel(app.source, labels)),
              fullPrompt: buildFullReadPrompt(app),
            },
            getEngine(),
            currentTier(),
          )
        : null,
    // labels only affect the source name; re-opening picks fresh ones up
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [app],
  );

  useEffect(() => {
    if (!controller) return;
    void controller.start();
    return () => controller.dispose();
  }, [controller]);

  const state = useControllerState(controller);
  const card = app ? toBoardCard(app, resolveSourceLabel(app.source, labels)) : null;

  return (
    <Sheet
      open={app !== null}
      onClose={onClose}
      label="Explain this quest"
      title={card?.title}
      meta={card?.meta}
    >
      {controller && (
        <>
          <ExplainNote body={state.body} method={state.method} swap={state.swap} />
          <ConsentArea
            state={state}
            onStart={() => void controller.startDownload()}
            onNotNow={() => controller.notNow()}
          />
          <div className="qb-srow">
            {app?.job_url && <TextLink href={app.job_url}>Apply at source</TextLink>}
            <PlainButton className="qb-closebtn" onClick={onClose}>
              Done for now
            </PlainButton>
          </div>
        </>
      )}
    </Sheet>
  );
}
