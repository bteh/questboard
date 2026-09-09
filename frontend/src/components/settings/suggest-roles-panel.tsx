import { Link } from '@tanstack/react-router';
import { Check, Copy, Loader2, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { useAgentConsent, useSetAgentConsent } from '@/hooks/use-agent-consent';
import {
  useAgentClients,
  useAgentProgress,
  useAgentRunActive,
  useDecideRoleProposal,
  useRoleProposals,
  useRunAgent,
} from '@/hooks/use-agent-clients';
import { isDesktopApp } from '@/lib/platform';
import { PROPOSE_ROLES_PROMPT, canRunHeadless, panelState, pickAssistant, suggestButtonLabel } from './suggest-roles-logic';

interface SuggestRolesPanelProps {
  resumeExists: boolean;
  onAccepted: (roles: string[]) => void;
}

/**
 * Under "Target roles": the connected assistant reads the resume and proposes
 * titles, right here, with one click. The assistant can only propose; the
 * person accepts, and the saved roles change only then.
 */
export function SuggestRolesPanel({ resumeExists, onAccepted }: SuggestRolesPanelProps) {
  const clientsQuery = useAgentClients();
  const consent = useAgentConsent();
  const setConsent = useSetAgentConsent();
  const run = useRunAgent();
  const running = useAgentRunActive();
  const progress = useAgentProgress(running);
  const proposals = useRoleProposals();
  const decide = useDecideRoleProposal();
  const [copied, setCopied] = useState(false);

  const clients = clientsQuery.data?.clients ?? [];
  const state = panelState({ desktop: isDesktopApp(), clients, resumeExists });
  if (state === 'hidden') return null;

  if (state === 'connect') {
    return (
      <p className="text-xs text-text-muted">
        Connect Claude Code or Codex in the{' '}
        <Link to="/settings" search={{ tab: 'assistant' }} className="underline underline-offset-2">
          Assistant tab
        </Link>{' '}
        and it can suggest roles from your resume.
      </p>
    );
  }
  if (state === 'resume') {
    return (
      <p className="text-xs text-text-muted">
        Upload your resume in the{' '}
        <Link to="/settings" search={{ tab: 'resume' }} className="underline underline-offset-2">
          Resume tab
        </Link>{' '}
        and your assistant can suggest roles from it.
      </p>
    );
  }

  const assistant = pickAssistant(clients);
  const assistantName = assistant?.name ?? 'your assistant';
  const granted = Boolean(consent.data?.granted);
  const pending = (proposals.data?.proposals ?? []).filter((proposal) => proposal.status === 'pending');
  const headless = assistant ? canRunHeadless(assistant) : false;

  const start = () => {
    const launch = () =>
      run.mutate(
        { task: 'propose_roles', client: assistant?.id ?? 'claude' },
        {
          onSuccess: (result) => {
            if (!result.ok) toast.error(result.error || `${assistantName} did not finish.`);
          },
          onError: (error) => toast.error(error instanceof Error ? error.message : 'The run failed'),
        },
      );
    if (granted) {
      launch();
      return;
    }
    // The click on a button that says "resume" is the human consent; record
    // it as the same setting the Assistant tab shows, then run.
    setConsent.mutate(true, {
      onSuccess: launch,
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not allow access'),
    });
  };

  const copyPrompt = async () => {
    const write = async () => {
      try {
        await navigator.clipboard.writeText(PROPOSE_ROLES_PROMPT);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1800);
      } catch {
        toast.error('Copy failed. Open the Assistant tab and copy the prompt by hand.');
      }
    };
    if (granted) {
      await write();
      return;
    }
    setConsent.mutate(true, {
      onSuccess: () => void write(),
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not allow access'),
    });
  };

  const accept = (id: number, roles: string[]) =>
    decide.mutate(
      { id, accept: true },
      {
        onSuccess: () => {
          onAccepted(roles);
          toast.success('Roles updated from the suggestion');
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not apply'),
      },
    );

  return (
    <div className="space-y-2 rounded-xl border border-border-default bg-bg-subtle/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-text-muted">
          Not sure what to type? {assistantName} can read your resume and suggest titles. Nothing is saved
          until you accept.
        </p>
        {headless ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={running || setConsent.isPending}
            onClick={start}
          >
            {running ? <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" /> : <Sparkles className="mr-2 h-3.5 w-3.5" />}
            {suggestButtonLabel({ assistantName, consentGranted: granted, running })}
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={setConsent.isPending}
            onClick={copyPrompt}
          >
            {copied ? <Check className="mr-2 h-3.5 w-3.5" /> : <Copy className="mr-2 h-3.5 w-3.5" />}
            {copied ? 'Copied' : granted ? `Copy prompt for ${assistantName}` : 'Allow resume access and copy prompt'}
          </Button>
        )}
      </div>
      {!headless ? (
        <p className="text-xs text-text-muted">
          Paste it into {assistantName} and send. When it answers, the suggestion appears here.
        </p>
      ) : null}
      {running && progress.data?.phase ? (
        <p className="text-xs text-text-muted">{progress.data.phase}</p>
      ) : null}
      {pending.map((proposal) => (
        <div key={proposal.id} className="space-y-2 rounded-lg border border-border-default bg-bg-card p-3">
          <p className="text-xs font-medium text-text-primary">Suggested by {assistantName}</p>
          <div className="flex flex-wrap gap-1.5">
            {proposal.proposed_roles.map((role) => (
              <span key={role} className="rounded-full border border-border-default px-2 py-0.5 text-xs">
                {role}
              </span>
            ))}
          </div>
          {proposal.rationale ? <p className="text-xs text-text-muted">{proposal.rationale}</p> : null}
          <div className="flex gap-2">
            <Button type="button" size="sm" disabled={decide.isPending} onClick={() => accept(proposal.id, proposal.proposed_roles)}>
              Use these roles
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={decide.isPending}
              onClick={() => decide.mutate({ id: proposal.id, accept: false })}
            >
              Not now
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
