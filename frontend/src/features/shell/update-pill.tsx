import { useAppUpdate } from '@/hooks/use-app-update';
import { updateActionText, updateBannerText } from '@/lib/updater-logic';

/**
 * A quiet "restart to get the new version" affordance in the topbar.
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

  return (
    <button type="button" className="qb-update-pill" onClick={restart}>
      {text} <b>{action}</b>
    </button>
  );
}
