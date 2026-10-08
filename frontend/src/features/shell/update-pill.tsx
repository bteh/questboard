import { useAppUpdate } from '@/hooks/use-app-update';
import { updateActionText, updateBannerLabel, updateBannerText } from '@/lib/updater-logic';

/**
 * The "restart to get the new version" button beside the search box.
 *
 * It appears only once a signed update is already downloaded, so clicking
 * it costs a relaunch and nothing else. Nothing here interrupts: no modal,
 * no toast, no badge on a fresh install that has nothing to update to.
 * While the install runs there is nothing to click, and a failed install
 * says the app still works and offers a retry.
 */
export function UpdatePill() {
  const { state, restart } = useAppUpdate();
  const text = updateBannerText(state);
  if (!text) return null;

  const action = updateActionText(state);
  if (!action) return <span className="qb-update-pill">{text}</span>;

  const ready = state.kind === 'ready';
  const label = updateBannerLabel(state) ?? text;
  return (
    <button
      type="button"
      className={ready ? 'qb-update-pill qb-update-pill-ready' : 'qb-update-pill'}
      onClick={restart}
      aria-label={ready ? label : undefined}
      title={ready ? label : undefined}
    >
      <span className="qb-update-pill-text">{text}</span> <b>{action}</b>
    </button>
  );
}
