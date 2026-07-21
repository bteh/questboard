import { Fragment, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { Loader2, Sparkles, Wand2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useAgentClients, useRunAgent } from '@/hooks/use-agent-clients';
import { useAgentConsent } from '@/hooks/use-agent-consent';
import { isDesktopApp } from '@/lib/platform';
import type { AgentRunResult } from '@/types/resume';

/** Render a small subset of Markdown as React nodes (headings, bold, links).
 *  No dangerouslySetInnerHTML: every node is constructed, so there's no XSS
 *  surface even though the text comes from the model. */
function renderMarkdown(text: string): React.ReactNode {
  const blocks = text.trim().split(/\n{2,}/);
  return blocks.map((block, bi) => {
    const heading = block.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      const cls =
        level === 1
          ? 'text-base font-semibold text-text-primary'
          : 'text-sm font-semibold text-text-primary';
      return (
        <p key={bi} className={cls}>
          {renderInline(heading[2])}
        </p>
      );
    }
    const lines = block.split('\n');
    return (
      <p key={bi} className="text-sm leading-relaxed text-text-secondary">
        {lines.map((line, li) => (
          <Fragment key={li}>
            {li > 0 && <br />}
            {renderInline(line)}
          </Fragment>
        ))}
      </p>
    );
  });
}

const INLINE = /(\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\)|https?:\/\/[^\s)]+)/g;

function renderInline(text: string): React.ReactNode {
  const parts = text.split(INLINE).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <strong key={i} className="font-semibold text-text-primary">
          {part.slice(2, -2)}
        </strong>
      );
    }
    const linked = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linked) {
      return (
        <a key={i} href={linked[2]} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2">
          {linked[1]}
        </a>
      );
    }
    if (/^https?:\/\//.test(part)) {
      return (
        <a key={i} href={part} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2 break-all">
          {part}
        </a>
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}

/**
 * One-click AI: the user clicks a button and the app runs their own connected
 * assistant (Claude) headlessly over the local MCP. The ranked, explained
 * result lands right here, with no copy-paste and no opening the agent.
 * Desktop-only (the run spawns a local CLI).
 */
export function AssistantRunPanel() {
  const run = useRunAgent();
  const clients = useAgentClients();
  const consent = useAgentConsent();
  const [outcome, setOutcome] = useState<AgentRunResult | null>(null);
  const [httpError, setHttpError] = useState<string | null>(null);

  if (!isDesktopApp()) return null;

  const claude = clients.data?.clients.find((c) => c.id === 'claude');
  const claudeInstalled = claude?.installed ?? false;
  const consentGranted = consent.data?.granted ?? false;

  const start = () => {
    setHttpError(null);
    setOutcome(null);
    run.mutate(
      { task: 'find_and_rank', client: 'claude' },
      {
        onSuccess: (data) => setOutcome(data),
        onError: (error) => setHttpError(error instanceof Error ? error.message : 'Something went wrong.'),
      },
    );
  };

  return (
    <div className="rounded-2xl border border-border-default bg-bg-card p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/10">
          <Sparkles className="h-5 w-5 text-brand" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-base font-semibold text-text-primary">Find and rank with your assistant</p>
          <p className="mt-1 text-sm text-text-secondary">
            It reads your resume and ranks the board against your experience, then tells you why the
            top few fit. Runs in your own Claude, so Questboard adds no AI cost. Takes a minute or two.
          </p>

          {!claudeInstalled && !clients.isLoading && (
            <p className="mt-3 text-sm text-text-muted">
              No assistant found yet.{' '}
              <Link to="/settings" search={{ tab: 'assistant' }} className="font-medium text-brand underline underline-offset-2">
                Connect Claude
              </Link>{' '}
              to turn this on.
            </p>
          )}

          {claudeInstalled && !consentGranted && !consent.isLoading && (
            <p className="mt-3 text-sm text-text-muted">
              Your assistant needs permission to read your resume first.{' '}
              <Link to="/settings" search={{ tab: 'assistant' }} className="font-medium text-brand underline underline-offset-2">
                Turn on resume access
              </Link>
              .
            </p>
          )}

          <div className="mt-4">
            <Button onClick={start} disabled={run.isPending || !claudeInstalled || !consentGranted}>
              {run.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Wand2 className="mr-2 h-4 w-4" />}
              {run.isPending ? 'Your assistant is working…' : 'Find & rank my matches'}
            </Button>
          </div>

          {run.isPending && (
            <p className="mt-3 text-sm text-text-muted">
              Reading your resume and ranking jobs. This takes a minute or two; you can keep using the app.
            </p>
          )}

          {httpError && !run.isPending && (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              {httpError}
            </div>
          )}

          {outcome && !outcome.ok && !run.isPending && (
            <div className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200">
              {outcome.error || 'Your assistant did not return an answer. Try again.'}
            </div>
          )}

          {outcome && outcome.ok && !run.isPending && (
            <div className="mt-4 space-y-3 rounded-xl border border-border-default bg-bg-subtle/40 p-4">
              {renderMarkdown(outcome.result)}
              <p className="pt-1 text-xs text-text-muted">
                Ranked by your own Claude{typeof outcome.num_turns === 'number' ? ` in ${outcome.num_turns} steps` : ''}. Always confirm details on the source posting.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
