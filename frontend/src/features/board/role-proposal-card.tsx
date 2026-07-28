import { useState } from 'react';
import { SageButton } from '@questboard/ui';

import { ApiError } from '@/lib/api-client';
import { useDecideRoleProposal, useRoleProposals } from '@/hooks/use-agent-clients';
import { rationaleIsLong, roleProposalChanges, type CappedRoleList } from './role-proposal';

interface RoleProposalCardProps {
  enabled?: boolean;
}

function RoleList({
  label,
  list,
  tone,
}: {
  label: string;
  list: CappedRoleList;
  tone: 'add' | 'drop';
}) {
  if (list.roles.length === 0) return null;

  const mark = tone === 'add' ? '+' : '−';
  return (
    <div className="qb-proposal-change">
      <span className="qb-proposal-label">{label}</span>
      <div className="qb-proposal-roles">
        {list.roles.map((role) => (
          <span className={`qb-proposal-role qb-proposal-${tone}`} key={role}>
            <span aria-hidden="true">{mark}</span> {role}
          </span>
        ))}
        {list.moreLabel && <span className="qb-proposal-more">{list.moreLabel}</span>}
      </div>
    </div>
  );
}

function Rationale({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  if (!text.trim()) return null;
  const long = rationaleIsLong(text);
  return (
    <div className="qb-proposal-why">
      <p className={long && !open ? 'qb-proposal-rationale qb-clamped' : 'qb-proposal-rationale'}>
        {text}
      </p>
      {long && (
        <button type="button" className="qb-textlink" onClick={() => setOpen((v) => !v)}>
          {open ? 'less' : 'the full note'}
        </button>
      )}
    </div>
  );
}

export function RoleProposalCard({ enabled = true }: RoleProposalCardProps) {
  const proposals = useRoleProposals(enabled);
  const decide = useDecideRoleProposal();
  const [decisionError, setDecisionError] = useState<{ id: number; message: string } | null>(
    null,
  );

  const visibleProposal = proposals.data?.proposals
    .filter((proposal) => proposal.status === 'pending')
    .map((proposal) => ({
      proposal,
      changes: roleProposalChanges(proposal.base_roles, proposal.proposed_roles),
    }))
    .find(({ changes }) => changes !== null);

  if (!enabled || !visibleProposal || !visibleProposal.changes) return null;

  const { proposal, changes } = visibleProposal;
  const errorMessage = decisionError?.id === proposal.id ? decisionError.message : null;

  function submitDecision(accept: boolean) {
    setDecisionError(null);
    decide.mutate(
      { id: proposal.id, accept },
      {
        onError: (error) => {
          const message =
            error instanceof ApiError && error.status === 409
              ? 'Your roles changed since this suggestion; ask for a fresh run.'
              : error instanceof Error
                ? error.message
                : 'The decision could not be saved. Try again.';
          setDecisionError({ id: proposal.id, message });
        },
      },
    );
  }

  return (
    <section className="qb-proposal" aria-labelledby={`qb-proposal-title-${proposal.id}`}>
      <p className="qb-proposal-kicker">From your assistant's last run</p>
      <h3 className="qb-proposal-title" id={`qb-proposal-title-${proposal.id}`}>
        A sharper role list to consider
      </h3>
      <div className="qb-proposal-diff">
        <RoleList label="add" list={changes.added} tone="add" />
        <RoleList label="drop" list={changes.dropped} tone="drop" />
      </div>
      <Rationale text={proposal.rationale} />
      {errorMessage && (
        <p className="qb-proposal-error" role="alert">
          {errorMessage}
        </p>
      )}
      <div className="qb-proposal-actions">
        <SageButton onClick={() => submitDecision(true)} disabled={decide.isPending}>
          Update my roles
        </SageButton>
        <button
          type="button"
          className="qb-proposal-keep"
          onClick={() => submitDecision(false)}
          disabled={decide.isPending}
        >
          Keep mine
        </button>
      </div>
    </section>
  );
}
