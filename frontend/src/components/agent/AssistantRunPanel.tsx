import { Fragment, useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { useQueryClient } from '@tanstack/react-query';
import { Check, ExternalLink, Loader2, Sparkles, Wand2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useAgentClients, useRunAgent } from '@/hooks/use-agent-clients';
import { useAgentConsent } from '@/hooks/use-agent-consent';
import { useApplications } from '@/hooks/use-applications';
import { isDesktopApp } from '@/lib/platform';
import type { AgentFitVerdict, ApplicationResponse } from '@/types/application';
import type { AgentRunResult } from '@/types/resume';

// Terse words that match the poster badge's vocabulary (one verdict, one word
// everywhere). The rank shows separately as the card's leading number.
const FIT_LABEL: Record<AgentFitVerdict, string> = {
  strong: 'strong',
  good: 'good',
  reach: 'reach',
  skip: 'skip',
};
const FIT_ORDER: Record<AgentFitVerdict, number> = { strong: 0, good: 1, reach: 2, skip: 3 };
const FIT_BADGE_CLS: Record<AgentFitVerdict, string> = {
  strong: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  good: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  reach: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  skip: 'bg-black/5 text-text-muted dark:bg-white/10',
};

/** Sort the agent's judged rows: by rank when present, else by verdict, skips last. */
function byFit(a: ApplicationResponse, b: ApplicationResponse): number {
  const fa = a.agent_fit!;
  const fb = b.agent_fit!;
  const ra = fa.rank ?? 999;
  const rb = fb.rank ?? 999;
  if (ra !== rb) return ra - rb;
  return FIT_ORDER[fa.verdict] - FIT_ORDER[fb.verdict];
}

function payLine(a: ApplicationResponse): string {
  // Prefer the annualized values; the raw salary_min/max can be an hourly or
  // monthly rate, which the $k formatter (÷1000) would render as "$0k".
  const min = a.salary_min_annualized ?? a.salary_min ?? null;
  const max = a.salary_max_annualized ?? a.salary_max ?? null;
  const k = (n: number) => `$${Math.round(n / 1000)}k`;
  if (min && max) return `${k(min)}–${k(max)}`;
  if (min) return `${k(min)}+`;
  if (max) return `up to ${k(max)}`;
  return 'pay not listed';
}

/** One ranked opportunity, the assistant's verdict + why, linking to the posting. */
function RankedCard({ app }: { app: ApplicationResponse }) {
  const fit = app.agent_fit!;
  return (
    <div className="rounded-xl border border-border-default bg-bg-card p-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-text-primary">
            {fit.rank ? <span className="text-text-muted">{fit.rank}. </span> : null}
            {app.job_title}
          </p>
          <p className="truncate text-xs text-text-muted">
            {app.company}
            {app.location ? ` · ${app.location}` : ''} · {payLine(app)}
          </p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 font-mono text-[10.5px] font-semibold ${FIT_BADGE_CLS[fit.verdict]}`}>
          {FIT_LABEL[fit.verdict]}
        </span>
      </div>
      {fit.why && <p className="mt-2 text-sm leading-relaxed text-text-secondary">{fit.why}</p>}
      {fit.caveat && <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Watch for: {fit.caveat}</p>}
      {app.job_url && (
        <a
          href={app.job_url}
          target="_blank"
          rel="noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand underline underline-offset-2"
        >
          Open posting <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

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
      // Only link safe schemes; a model-supplied javascript:/data: URL renders
      // as plain text, never a clickable link.
      if (/^(https?:|mailto:)/i.test(linked[2])) {
        return (
          <a key={i} href={linked[2]} target="_blank" rel="noreferrer" className="text-brand underline underline-offset-2">
            {linked[1]}
          </a>
        );
      }
      return <Fragment key={i}>{linked[1]}</Fragment>;
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

// The real phases of a run, with a rough time each one starts. The last phase
// (ranking) is the long one and stays active until the result lands, so the
// card never shows a fake "done".
const RUN_STEPS = [
  { at: 0, label: 'Reading your resume' },
  { at: 8, label: 'Pulling fresh postings' },
  { at: 100, label: 'Ranking against your experience' },
];

/** A live progress card during the ~1-2 min run: a running clock and the
 *  current phase, so the wait shows activity instead of a still spinner. */
function RunProgress() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const currentIdx = RUN_STEPS.reduce((acc, step, i) => (elapsed >= step.at ? i : acc), 0);
  const mm = Math.floor(elapsed / 60);
  const ss = String(elapsed % 60).padStart(2, '0');
  return (
    <div className="mt-4 rounded-xl border border-brand/25 bg-brand/5 p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-medium text-text-primary">
          <Loader2 className="h-4 w-4 animate-spin text-brand" />
          Your assistant is working
        </span>
        <span className="font-mono text-xs tabular-nums text-text-muted">
          {mm}:{ss}
        </span>
      </div>
      <ul className="mt-3 space-y-2">
        {RUN_STEPS.map((step, i) => {
          const done = i < currentIdx;
          const active = i === currentIdx;
          return (
            <li
              key={step.label}
              className={`flex items-center gap-2.5 text-sm ${active ? 'text-text-primary' : done ? 'text-text-secondary' : 'text-text-muted'}`}
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                {done ? (
                  <Check className="h-3.5 w-3.5 text-emerald-600" />
                ) : active ? (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-brand" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-text-muted/40" />
                )}
              </span>
              <span>
                {step.label}
                {active && i === RUN_STEPS.length - 1 && (
                  <span className="text-text-muted"> (the long part)</span>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-3 text-xs text-text-muted">
        Takes three to five minutes. You can keep using the app.
      </p>
    </div>
  );
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
  const queryClient = useQueryClient();
  // The assistant writes its verdict onto the board rows (set_work_fit); read
  // them back to show the ranked cards and to reflect the badges on posters.
  const board = useApplications({ vertical: 'career', page_size: 100 });
  const [outcome, setOutcome] = useState<AgentRunResult | null>(null);
  const [httpError, setHttpError] = useState<string | null>(null);

  if (!isDesktopApp()) return null;

  const ranked = (board.data?.items ?? []).filter((a) => a.agent_fit).sort(byFit);

  const claude = clients.data?.clients.find((c) => c.id === 'claude');
  const claudeInstalled = claude?.installed ?? false;
  const consentGranted = consent.data?.granted ?? false;

  const start = () => {
    setHttpError(null);
    setOutcome(null);
    run.mutate(
      { task: 'find_and_rank', client: 'claude' },
      {
        onSuccess: (data) => {
          setOutcome(data);
          // Pull the fresh verdicts onto the board (poster badges) and into the
          // ranked cards below.
          void queryClient.invalidateQueries({ queryKey: ['applications'] });
        },
        onError: (error) => setHttpError(error instanceof Error ? error.message : 'Something went wrong. Try again in a minute.'),
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
            It reads your resume, adds job titles you might not think to search for, pulls
            fresh postings, and ranks every job on the board with reasons. Runs in your own
            Claude, at no cost from Questboard. Takes three to five minutes.
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

          {run.isPending && <RunProgress />}

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
            <div className="mt-4 space-y-3">
              {ranked.length > 0 && outcome.result && (
                <p className="text-sm font-medium text-text-primary">{outcome.result}</p>
              )}
              {ranked.length > 0 ? (
                <>
                  <div className="space-y-2.5">
                    {ranked.map((app) => (
                      <RankedCard key={app.id} app={app} />
                    ))}
                  </div>
                  <p className="text-xs text-text-muted">
                    Ranked by your own Claude{typeof outcome.num_turns === 'number' ? ` in ${outcome.num_turns} steps` : ''}.
                    These verdicts also show on the board posters below. Always confirm details on the source posting.
                  </p>
                </>
              ) : (
                // Ran fine, but no per-job verdicts came back (older agent, or it
                // answered in prose). Show its reply so nothing is lost.
                <div className="rounded-xl border border-border-default bg-bg-subtle/40 p-4">
                  {renderMarkdown(outcome.result)}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
