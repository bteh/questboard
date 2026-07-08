/**
 * "The AI download", the one place in the app allowed to say "AI".
 *
 * The row renders only on machines that manage a download: phones, weak
 * machines, and machines whose own local runtime already answers see nothing
 * here at all. Remove is one click, no guilt modal.
 */

import { useEffect, useState, useSyncExternalStore } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { downloads, managedDownload, removeDownload, type Engine } from '@/lib/ai';

const DESCRIPTION =
  '1.1 GB, kept on this computer. It writes the full reads. Nothing you type leaves.';

type RowState = 'ready' | 'progress' | 'absent' | 'removed';

export function TheAiDownloadSection() {
  const [engine, setEngine] = useState<Engine | null>(null);
  const [row, setRow] = useState<RowState | null>(null);
  /* "Removed. The space is yours again." holds until the next click */
  const [justRemoved, setJustRemoved] = useState(false);

  const download = useSyncExternalStore(
    (onChange) => downloads.subscribe(onChange),
    () => `${downloads.running}:${downloads.pct}:${downloads.done}`,
  );

  useEffect(() => {
    if (justRemoved) return;
    let alive = true;
    (async () => {
      const managed = await managedDownload();
      if (!alive) return;
      setEngine(managed);
      if (!managed) return;
      if (downloads.running) {
        setRow('progress');
        return;
      }
      const status = await managed.status();
      if (!alive) return;
      setRow(status.availability === 'ready' ? 'ready' : 'absent');
    })();
    return () => {
      alive = false;
    };
    /* re-check when the shared download settles or moves */
  }, [download, justRemoved]);

  if (!engine || !row) return null;

  const startDownload = () => {
    setJustRemoved(false);
    setRow('progress');
    void downloads.start(engine);
  };

  const remove = async () => {
    setJustRemoved(true);
    setRow('removed');
    await removeDownload(engine);
  };

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>The AI download</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {row === 'ready' && (
          <>
            <p className="text-sm text-text-secondary">{DESCRIPTION}</p>
            <Button variant="outline" size="sm" onClick={() => void remove()}>
              Remove
            </Button>
          </>
        )}
        {row === 'progress' && (
          <p className="text-sm text-text-secondary">
            On its way, {downloads.pct}%. Keep browsing, it finishes on its own.
          </p>
        )}
        {row === 'absent' && (
          <>
            <p className="text-sm text-text-secondary">{DESCRIPTION}</p>
            <Button variant="outline" size="sm" onClick={startDownload}>
              Get it, 1.1 GB
            </Button>
          </>
        )}
        {row === 'removed' && (
          <>
            <p className="text-sm text-text-secondary">Removed. The space is yours again.</p>
            <Button variant="outline" size="sm" onClick={startDownload}>
              Get it again, 1.1 GB
            </Button>
          </>
        )}
      </CardContent>
    </Card>
  );
}
