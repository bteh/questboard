/* Runs the user's local Claude on the find_and_rank task: it reads the
   resume, refines roles, pulls the same fresh postings the plain button
   pulls, then ranks them. On success the posters and applications refetch so
   verdicts land and ranked rows float first, and a toast reports the run's
   one-line summary (the assistant run has no live progress stream of its own,
   so this is how the reader learns it finished). A superset of the plain pull,
   which is why the work lane keeps just one button. */

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
          // The endpoint returns 200 even when the agent itself gave up; ok
          // separates a real ranking from a failed run.
          if (!data.ok) {
            toast.error(data.error || 'The run did not finish. Try again.');
            return;
          }
          void queryClient.invalidateQueries({ queryKey: ['profile-work'] });
          void queryClient.invalidateQueries({ queryKey: ['applications'] });
          toast.success(data.result?.trim() || 'Board ranked against your resume');
        },
        onError: (err) =>
          toast.error(err instanceof Error ? err.message : 'The run did not finish. Try again.'),
      },
    );
  }

  return { start, isPending: run.isPending };
}
