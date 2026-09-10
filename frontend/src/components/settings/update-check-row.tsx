import { Loader2, RefreshCw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useUpdateCheck } from '@/hooks/use-app-update';
import { isDesktopApp } from '@/lib/platform';
import { checkStatusText } from '@/lib/updater-logic';

/** "Questboard 0.2.3 · Check for updates". The one place the app is allowed
 *  to say "you already have the latest". */
export function UpdateCheckRow() {
  const { state, version, checkNow, restart } = useUpdateCheck();
  if (!isDesktopApp()) return null;

  const busy = state.kind === 'checking' || state.kind === 'downloading' || state.kind === 'installing';
  const retry = state.kind === 'install_failed';
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3">
      <p className="text-sm text-text-secondary">{checkStatusText(state, version)}</p>
      {state.kind === 'ready' || retry ? (
        <Button type="button" size="sm" onClick={restart}>
          {retry ? 'Try again' : 'Restart to update'}
        </Button>
      ) : (
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={checkNow}>
          {busy ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="mr-2 h-3.5 w-3.5" />}
          Check for updates
        </Button>
      )}
    </div>
  );
}
