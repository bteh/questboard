import { Link } from '@tanstack/react-router';
import type { BoardParams } from '@/components/board/board-state';
import { workflowForKind, type KindKey, type Workflow } from '@/features/board/kind-params';

/* The board's primary structure: its two workflows named side by side at
   the top of the page. Side quests is the quest board, Find work is the
   career lane (?v=work). Quiet text tabs in the trade-paper register, the
   active lane inked with an underline. They are Links, so keyboard,
   middle-click, and a shared /board?v=work address all work; the route's
   validateSearch sets the active tab from the URL on a deep link.
   The search updaters come from the board page, which owns the param
   hygiene for a lane switch (facets and hidden presets must not ride
   along). */

export function LaneTabs({
  kindKey,
  searchFor,
}: {
  kindKey: KindKey;
  /** the board page's lane-switch param updater for each tab's Link */
  searchFor: (lane: Workflow) => (prev: BoardParams) => BoardParams;
}) {
  const active = workflowForKind(kindKey);
  function tab(lane: Workflow, label: string) {
    const on = active === lane;
    return (
      <Link
        to="/board"
        search={searchFor(lane)}
        className={on ? 'qb-lane qb-lane-on' : 'qb-lane'}
        aria-current={on ? 'page' : undefined}
      >
        {label}
      </Link>
    );
  }
  return (
    <nav className="qb-lanes" aria-label="Workflows">
      {tab('quests', 'Side quests')}
      {tab('work', 'Find work')}
    </nav>
  );
}
