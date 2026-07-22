import { useState } from 'react';
import { Link } from '@tanstack/react-router';
import { Bot, Check, Copy, Loader2, Plug, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAgentClients, useConnectAgent, useDisconnectAgent } from '@/hooks/use-agent-clients';
import { useAgentConsent, useSetAgentConsent } from '@/hooks/use-agent-consent';
import { isDesktopApp } from '@/lib/platform';
import { openExternal } from '@/lib/open-external';
import type { AgentClientStatus } from '@/types/resume';

/* The chat fallback for the board's "Find and rank with your assistant" run.
   The backend's find_and_rank task covers the same ground (read resume,
   sharpen roles via set_career_preferences, rank postings with reasons), but
   headless runs are Claude-only today, so this pasteable prompt is the only
   automatic-ish path for Codex users. Consent-gated. */
const SETUP_PROMPT =
  'Use my local Questboard MCP tools: read my resume, sharpen my target roles and broaden them with adjacent titles I might not think to search for, save them, refresh work with those roles, then find me matching work and tell me which postings fit my experience best and why.';

export function AssistantTab() {
  const clientsQuery = useAgentClients();
  const connect = useConnectAgent();
  const disconnect = useDisconnectAgent();
  const consent = useAgentConsent();
  const setConsent = useSetAgentConsent();
  const [copied, setCopied] = useState(false);

  const clients = clientsQuery.data?.clients ?? [];
  const noneInstalled = !clientsQuery.isLoading && clients.length > 0 && clients.every((client) => !client.installed);

  const handleConnect = (client: AgentClientStatus) => {
    connect.mutate(client.id, {
      onSuccess: (data) => toast.success(`${data.name} connected. Restart ${data.name} to use Questboard.`),
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not connect'),
    });
  };
  const handleDisconnect = (client: AgentClientStatus) => {
    disconnect.mutate(client.id, {
      onSuccess: (data) => toast.success(`${data.name} turned off`),
      onError: (error) => toast.error(error instanceof Error ? error.message : 'Could not turn off'),
    });
  };
  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(SETUP_PROMPT);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error('Copy failed. Select the text and copy it by hand.');
    }
  };

  if (!isDesktopApp()) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" /> Your assistant
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-text-secondary">
            Open Questboard on your Mac to connect Claude or Codex. The link runs on your own
            machine, so only the desktop app can set it up.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" /> Your assistant
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-text-secondary">
            Questboard finds and filters the work. Your own assistant (Claude or Codex) ranks jobs
            by resume fit and drafts notes. The link stays on your machine. No AI key, no cost
            from us.
          </p>

          <div className="space-y-2">
            {clientsQuery.isLoading ? (
              <p className="text-sm text-text-muted">Checking for assistants…</p>
            ) : (
              clients.map((client) => (
                <div
                  key={client.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-text-primary">{client.name}</p>
                    <p className="text-xs text-text-muted">
                      {!client.installed
                        ? 'Not found on this Mac'
                        : client.connected
                          ? 'Connected. Restart it to pick up changes.'
                          : 'Installed, not connected yet'}
                    </p>
                  </div>
                  {!client.installed ? (
                    <span className="text-xs text-text-tertiary">Install it first</span>
                  ) : client.connected ? (
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 text-xs font-medium text-brand">
                        <Check className="h-3.5 w-3.5" /> Connected
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={connect.isPending}
                        onClick={() => handleConnect(client)}
                      >
                        Reconnect
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={disconnect.isPending}
                        onClick={() => handleDisconnect(client)}
                      >
                        Turn off
                      </Button>
                    </div>
                  ) : (
                    <Button
                      size="sm"
                      disabled={connect.isPending}
                      onClick={() => handleConnect(client)}
                    >
                      {connect.isPending && connect.variables === client.id ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Plug className="mr-2 h-4 w-4" />
                      )}
                      Connect
                    </Button>
                  )}
                </div>
              ))
            )}
            {noneInstalled && (
              <p className="text-xs text-text-muted">
                No assistant found on this Mac. Questboard works with{' '}
                <button
                  type="button"
                  className="font-medium text-brand underline underline-offset-2"
                  onClick={() => void openExternal('https://claude.ai/code')}
                >
                  Claude Code
                </button>{' '}
                or Codex. Install one, then come back.
              </p>
            )}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4" /> Rank jobs by resume fit
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-3 rounded-xl border border-border-default bg-bg-subtle/40 p-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-text-primary">Let your assistant read your resume</p>
              <p className="text-xs text-text-muted">
                {consent.data?.granted
                  ? 'Allowed. It reads your resume to match roles. Questboard never sends it anywhere.'
                  : 'Off. Your assistant can browse jobs, but cannot read your resume until you allow it.'}
              </p>
            </div>
            <Button
              variant={consent.data?.granted ? 'outline' : 'default'}
              size="sm"
              disabled={setConsent.isPending || consent.isLoading}
              onClick={() =>
                setConsent.mutate(!consent.data?.granted, {
                  onSuccess: (data) =>
                    toast.success(data.granted ? 'Resume access allowed' : 'Resume access turned off'),
                  onError: (error) =>
                    toast.error(error instanceof Error ? error.message : 'Could not update access'),
                })
              }
            >
              {consent.data?.granted ? 'Turn off' : 'Allow'}
            </Button>
          </div>

          <p className="text-sm text-text-secondary">
            Then open{' '}
            <Link
              to="/board"
              search={{ v: 'work' }}
              className="font-medium text-brand underline underline-offset-2"
            >
              Find work
            </Link>{' '}
            on the board and click &ldquo;Find and rank with your assistant&rdquo;.
          </p>

          <details className="rounded-xl border border-border-default bg-bg-subtle/40 p-3">
            <summary className="cursor-pointer text-sm font-medium text-text-primary">
              Run it from chat instead
            </summary>
            <div className="mt-3 space-y-2">
              <p className="text-sm text-text-secondary">
                Paste this into Claude or Codex; it does the same run.
              </p>
              <div className="rounded-xl border border-border-default bg-bg-card p-3 text-sm leading-relaxed text-text-primary">
                {SETUP_PROMPT}
              </div>
              <Button variant="outline" size="sm" onClick={copyPrompt} disabled={!consent.data?.granted}>
                {copied ? <Check className="mr-2 h-4 w-4" /> : <Copy className="mr-2 h-4 w-4" />}
                {consent.data?.granted ? (copied ? 'Copied' : 'Copy prompt') : 'Allow resume access first'}
              </Button>
            </div>
          </details>
        </CardContent>
      </Card>
    </div>
  );
}
