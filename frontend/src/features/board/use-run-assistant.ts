/* Runs the user's local Claude on the find_and_rank task: it reads the
   resume, refines roles, pulls the same fresh postings the plain button
   pulls, then ranks them. On success the posters and applications refetch so
   verdicts land and ranked rows float first. The assistant's raw completion
   summary stays out of the UI: it can contain role proposals and internal
   review notes that do not belong in a success toast. A superset of the plain
   pull, which is why the work lane keeps just one button. */

import { toast } from 'sonner';
import { useQueryClient } from '@tanstack/react-query';
import { useRunAgent } from '@/hooks/use-agent-clients';

export interface RunAssistant {
  start: () => void;
  isPending: boolean;
}

export function useRunAssistant(): RunAssistant {
  const run = useRunAgent();
  const queryClient = useQueryClient();

  function start() {
    if (run.isPending) return;
    run.mutate(
      { task: 'find_and_rank', client: 'claude' },
      {
        onSuccess: (data) => {
          // The durable refresh may have saved useful rows even if the later
          // assistant ranking step reports failure. Reload its board and
          // persisted source receipt before interpreting the agent outcome.
          void queryClient.invalidateQueries({ queryKey: ['profile-work'] });
          void queryClient.invalidateQueries({ queryKey: ['applications'] });
          void queryClient.invalidateQueries({ queryKey: ['board-summary'] });
          // The endpoint returns 200 even when the agent itself gave up; ok
          // separates a real ranking from a failed run.
          if (!data.ok) {
            toast.error(data.error || 'The run did not finish. Try again.');
            return;
          }
        },
        onError: (err) => {
          void queryClient.invalidateQueries({ queryKey: ['profile-work'] });
          void queryClient.invalidateQueries({ queryKey: ['applications'] });
          void queryClient.invalidateQueries({ queryKey: ['board-summary'] });
          toast.error(err instanceof Error ? err.message : 'The run did not finish. Try again.');
        },
      },
    );
  }

  return { start, isPending: run.isPending };
}
