import { useMutation, useQueryClient } from '@tanstack/react-query';
import { SageButton } from '@questboard/ui';
import { questRestockDoneLine, refreshQuests } from './quest-restock-logic';

/* The quest board's own restock door, pinned by quest-restock.test.tsx.
   One trigger, three follow-up states: checking, the plain done count, or
   the server's refusal in its own words. On success the board queries
   invalidate, so fresh rows appear where the reader already is. */

/** `big` renders the empty board's primary button; the default is the
    restock line's quiet inline trigger. */
export function QuestRestockButton({
  big = false,
  label = 'Check for new quests',
}: {
  big?: boolean;
  label?: string;
}) {
  const queryClient = useQueryClient();
  const refresh = useMutation({
    mutationFn: refreshQuests,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['applications'] });
      void queryClient.invalidateQueries({ queryKey: ['board-summary'] });
    },
  });

  if (refresh.isPending) {
    return <span role="status">Checking the quest sources.</span>;
  }
  if (refresh.isSuccess) {
    return <span role="status">{questRestockDoneLine(refresh.data.saved)}</span>;
  }
  if (refresh.isError) {
    const message =
      refresh.error instanceof Error && refresh.error.message.trim()
        ? refresh.error.message
        : 'The check did not run. Try again in a minute.';
    return <span role="status">{message}</span>;
  }
  if (big) {
    return <SageButton onClick={() => refresh.mutate()}>{label}</SageButton>;
  }
  return (
    <button
      type="button"
      className="qb-textlink"
      style={{ fontSize: 13.5 }}
      onClick={() => refresh.mutate()}
    >
      {label}
    </button>
  );
}
