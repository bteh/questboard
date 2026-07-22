import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Loader2, Sparkles } from 'lucide-react';

import { useAgentClients, useRunAgent } from '@/hooks/use-agent-clients';
import { useAgentConsent } from '@/hooks/use-agent-consent';
import { isDesktopApp } from '@/lib/platform';

const PHASES = ['Reading your resume', 'Searching the board', 'Ranking against your experience'];

export type AssistantEmphasis = 'quiet' | 'elevated';

/* One primary action per lane: "Get new jobs" keeps the only filled button.
   This door elevates (bordered, tinted) only when there are rows to rank and
   no verdicts stored yet; at zero rows, or once ranked, it reads as a quiet
   text link. Pinned by assistant-emphasis.test.ts. */
export function assistantRunEmphasis(rowCount: number, hasVerdicts: boolean): AssistantEmphasis {
  return rowCount > 0 && !hasVerdicts ? 'elevated' : 'quiet';
}

/* The AI run, in the work lane's actions row right after "Get new jobs":
   tap it and your own Claude reads your resume, ranks the board, and its
   verdicts land on the posters (badges + explain). Desktop-only; the run
   spawns your local agent. */
export function AssistantRunButton({
  rowCount = 0,
  hasVerdicts = false,
}: {
  /** loaded rows on the lane; zero keeps the door quiet */
  rowCount?: number;
  /** true once assistant verdicts are stored; keeps the door quiet again */
  hasVerdicts?: boolean;
}) {
  const run = useRunAgent();
  const clients = useAgentClients();
  const consent = useAgentConsent();
  const queryClient = useQueryClient();
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!run.isPending) return;
    setElapsed(0);
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [run.isPending]);

  if (!isDesktopApp()) return null;
  // Don't flash the "connect" link before we know the real state.
  if (!run.isPending && (clients.isLoading || consent.isLoading)) return null;

  // Claude only, on purpose: the backend's run_headless rejects codex because
  // `codex exec` can't be pinned to the Questboard tool allow-list yet (see
  // backend/app/services/agent_integration_service.py). Codex users get the
  // pasteable prompt in Settings > Assistant instead.
  const claude = clients.data?.clients.find((c) => c.id === 'claude');
  const ready = (claude?.installed ?? false) && (consent.data?.granted ?? false);

  const start = () => {
    setError(null);
    run.mutate(
      { task: 'find_and_rank', client: 'claude' },
      {
        onSuccess: () => {
          // Refresh so the posters wear their verdicts and float ranked-first.
          void queryClient.invalidateQueries({ queryKey: ['profile-work'] });
          void queryClient.invalidateQueries({ queryKey: ['applications'] });
        },
        onError: (err) =>
          setError(err instanceof Error ? err.message : 'The run did not finish. Try again.'),
      },
    );
  };

  if (run.isPending) {
    const phase = elapsed < 7 ? PHASES[0] : elapsed < 20 ? PHASES[1] : PHASES[2];
    const clock = `${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, '0')}`;
    return (
      <span className="inline-flex items-center gap-2 rounded-lg border border-brand/25 bg-brand/5 px-3 py-2 text-sm text-text-primary">
        <Loader2 className="h-4 w-4 animate-spin text-brand" />
        {phase}…
        <span className="font-mono text-xs tabular-nums text-text-muted">{clock}</span>
      </span>
    );
  }

  if (!ready) {
    return (
      <Link
        to="/settings"
        search={{ tab: 'assistant' }}
        className="text-sm font-medium text-brand underline underline-offset-2"
      >
        Connect your assistant to rank these
      </Link>
    );
  }

  const emphasis = assistantRunEmphasis(rowCount, hasVerdicts);
  return (
    <span className="inline-flex items-center gap-2">
      {emphasis === 'elevated' ? (
        <button
          type="button"
          onClick={start}
          className="inline-flex items-center gap-1.5 rounded-lg border border-brand bg-brand/10 px-3 py-2 text-sm font-medium text-brand transition-colors hover:bg-brand/15"
        >
          <Sparkles className="h-4 w-4" />
          Rank these with your assistant
        </button>
      ) : (
        <button
          type="button"
          onClick={start}
          className="text-sm font-medium text-brand underline underline-offset-2"
        >
          Rank these with your assistant
        </button>
      )}
      {error && <span className="text-xs text-amber-700 dark:text-amber-300">{error}</span>}
    </span>
  );
}
