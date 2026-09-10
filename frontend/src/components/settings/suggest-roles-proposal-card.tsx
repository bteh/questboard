import type { RoleProposal } from '@/api/agent';
import { Button } from '@/components/ui/button';

interface SuggestRolesProposalCardProps {
  proposal: RoleProposal;
  assistantName: string;
  busy: boolean;
  onAccept: () => void;
  onDismiss: () => void;
}

function Chips({ items }: { items: string[] }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <span key={item} className="rounded-full border border-border-default px-2 py-0.5 text-xs">
          {item}
        </span>
      ))}
    </div>
  );
}

/** One pending proposal: the roles, the keywords, the assistant's reason,
 *  and the two buttons that decide it. */
export function SuggestRolesProposalCard({
  proposal,
  assistantName,
  busy,
  onAccept,
  onDismiss,
}: SuggestRolesProposalCardProps) {
  return (
    <div className="space-y-2 rounded-lg border border-border-default bg-bg-card p-3">
      <p className="text-xs font-medium text-text-primary">Suggested by {assistantName}</p>
      <Chips items={proposal.proposed_roles} />
      {proposal.proposed_keywords.length > 0 ? (
        <div className="space-y-1">
          <p className="text-[11px] font-medium text-text-muted">Keywords</p>
          <Chips items={proposal.proposed_keywords} />
        </div>
      ) : null}
      {proposal.rationale ? <p className="text-xs text-text-muted">{proposal.rationale}</p> : null}
      <div className="flex gap-2">
        <Button type="button" size="sm" disabled={busy} onClick={onAccept}>
          Use these
        </Button>
        <Button type="button" variant="outline" size="sm" disabled={busy} onClick={onDismiss}>
          Not now
        </Button>
      </div>
    </div>
  );
}
