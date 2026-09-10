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
  useMarkAgentIntent,
  useRoleProposals,
  useRunAgent,
} from '@/hooks/use-agent-clients';
import { isDesktopApp } from '@/lib/platform';
import type { AgentRunResult } from '@/types/resume';
import {
  PROPOSE_ROLES_PROMPT,
  canRunHeadless,
  panelState,
  pickAssistant,
  runOutcomeNote,
  suggestButtonLabel,
} from './suggest-roles-logic';
import { SuggestRolesProposalCard } from './suggest-roles-proposal-card';

interface SuggestRolesPanelProps {
  resumeExists: boolean;
  onAccepted: (applied: { roles: string[]; keywords: string[] }) => void;
}

/**
 * Under "Target roles": the connected assistant reads the resume and proposes
 * titles and keywords, right here, with one click. The assistant can only
 * propose; the person accepts, and the saved lists change only then.
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
  const markIntent = useMarkAgentIntent();
  const [copied, setCopied] = useState(false);
  const [lastRun, setLastRun] = useState<AgentRunResult | null>(null);

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
        and it can suggest roles and keywords from your resume.
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
        and your assistant can suggest roles and keywords from it.
      </p>
    );
  }

  const assistant = pickAssistant(clients);
  const assistantName = assistant?.name ?? 'your assistant';
  const granted = Boolean(consent.data?.granted);
  const pending = (proposals.data?.proposals ?? []).filter((proposal) => proposal.status === 'pending');
  const headless = assistant ? canRunHeadless(assistant) : false;
  const phase = progress.data?.phase;
  const outcome = lastRun ? runOutcomeNote(lastRun, pending.length) : null;

  const start = () => {
    const launch = () => {
      setLastRun(null);
      run.mutate(
        { task: 'propose_roles', client: assistant?.id ?? 'claude' },
        {
          onSuccess: (result) => {
            if (!result.ok) toast.error(result.error || `${assistantName} did not finish.`);
            setLastRun(result);
          },
          onError: (error) => toast.error(error instanceof Error ? error.message : 'The run failed'),
        },
      );
    };
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
      markIntent.mutate('propose_roles');
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

  const accept = (id: number) =>
    decide.mutate(
      { id, accept: true },
      {
        onSuccess: (decision) => {
          onAccepted({ roles: decision.roles, keywords: decision.keywords });
          toast.success('Roles and keywords updated from the suggestion');
        },
        onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not apply'),
      },
    );

  return (
    <div className="space-y-2 rounded-xl border border-border-default bg-bg-subtle/40 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-text-muted">
          Not sure what to type? {assistantName} can read your resume and fill in titles and keywords.
          Nothing is saved until you accept.
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
      {running ? (
        <p className="text-xs text-text-muted">
          {phase ? `Usually about a minute. ${phase}` : 'Usually about a minute.'}
        </p>
      ) : null}
      {outcome ? <p className="text-xs text-text-muted">{outcome}</p> : null}
      {pending.map((proposal) => (
        <SuggestRolesProposalCard
          key={proposal.id}
          proposal={proposal}
          assistantName={assistantName}
          busy={decide.isPending}
          onAccept={() => accept(proposal.id)}
          onDismiss={() => decide.mutate({ id: proposal.id, accept: false })}
        />
      ))}
    </div>
  );
}
