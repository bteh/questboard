import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Download,
  ExternalLink,
  HardDrive,
  Loader2,
  RefreshCw,
  Shield,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  useLLMPresets,
  useLLMStatus,
  useTestConnection,
  useUpdateLLM,
} from '@/hooks/use-settings';
import { POPULAR_PROVIDER_CHOICES, type PopularProviderName } from '@/lib/llm-choice';
import { openExternalClick } from '@/lib/open-external';
import { cn } from '@/lib/utils';

interface AiDiagnosticModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * The single source of truth for AI connection management and recovery.
 *
 * Replaces the old ConnectAiPopover's small, hidden-behind-click UX with
 * a full Dialog that ALWAYS explains the current state in plain language,
 * tests the connection on demand, and offers one-click fixes:
 *
 *   - "Test connection now" — runs a real 1-token completion (force=true)
 *   - Provider quick-switch tabs — one click to change providers
 *   - Quick Start local AI — auto-installs Ollama + phi4-mini
 *   - Plain-language error + fix button when things break
 *
 * Design principle: a user who is stuck should never have to guess.
 * The current error is shown with the next action they should take,
 * and clicking that action either fixes the problem or takes them
 * directly to the place that can.
 */
export function AiDiagnosticModal({ open, onOpenChange }: AiDiagnosticModalProps) {
  const navigate = useNavigate();
  const { data: llm, refetch: refetchLLM } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();

  const [selectedProvider, setSelectedProvider] = useState<PopularProviderName>('gemini');
  const [userSelectedTab, setUserSelectedTab] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [quickStartStatus, setQuickStartStatus] = useState<{
    status: 'idle' | 'installing' | 'pulling' | 'configuring' | 'ready' | 'error';
    step: string;
    progress: number;
    error: string;
    model: string;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = undefined;
    }
  }, []);

  // Clear interval on unmount
  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  // Clear interval when the modal is closed — the component stays mounted
  // but we don't want background polling running while hidden.
  useEffect(() => {
    if (!open) stopPolling();
  }, [open, stopPolling]);

  const isConnected = !!llm?.available;
  const isBroken = !!llm?.configured && !llm?.available;
  const isWorking = updateLLM.isPending || testConnection.isPending;
  const quickStartActive = quickStartStatus && quickStartStatus.status !== 'idle' && quickStartStatus.status !== 'ready';

  // ── Auto-detect provider from API key format ────────────────────────
  const detectProviderFromKey = (key: string): PopularProviderName | null => {
    const k = key.trim();
    if (k.startsWith('AIza')) return 'gemini';
    if (k.startsWith('gsk_')) return 'groq';
    if (k.startsWith('sk-ant-')) return 'anthropic-api';
    if (k.startsWith('sk-')) return 'openai-api';
    return null;
  };

  const prevKeyLenRef = useRef(0);

  const handleKeyChange = (value: string) => {
    setApiKey(value);
    const trimmed = value.trim();

    // Auto-detect provider from key format (only if user hasn't picked a tab)
    if (!userSelectedTab && trimmed.length >= 20) {
      const detected = detectProviderFromKey(trimmed);
      if (detected && detected !== selectedProvider) setSelectedProvider(detected);
    }

    // Test-on-paste: if the input jumped from ~0 to 20+ chars in one
    // change, the user probably pasted a full key. Auto-connect so
    // they see instant feedback without clicking "Connect".
    const wasPaste = prevKeyLenRef.current < 5 && trimmed.length >= 20;
    prevKeyLenRef.current = trimmed.length;

    if (wasPaste && detectProviderFromKey(trimmed)) {
      // Pass the key directly — React state hasn't updated yet
      setTimeout(() => handleConnect(trimmed), 0);
    }
  };

  const handleSelectProvider = (name: PopularProviderName) => {
    setSelectedProvider(name);
    setUserSelectedTab(true);
    setApiKey('');
  };

  // ── Quick Start local AI (inline) ─────────────────────────────────
  const startQuickStart = useCallback(async () => {
    // Clear any prior polling before starting — prevents duplicate
    // intervals from stacking on repeated Retry clicks.
    stopPolling();
    setQuickStartStatus({ status: 'installing', step: 'Starting setup...', progress: 0, error: '', model: 'phi4-mini' });
    try {
      const resp = await fetch(
        (import.meta.env.VITE_API_URL || '/api/v1') + '/settings/ollama/setup',
        { method: 'POST', credentials: 'include' },
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Setup failed' }));
        setQuickStartStatus((s) => s ? { ...s, status: 'error', error: err.detail || 'Setup failed' } : s);
        return;
      }
    } catch {
      setQuickStartStatus({ status: 'error', step: 'Connection failed', progress: 0, error: 'Could not reach the backend.', model: '' });
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(
          (import.meta.env.VITE_API_URL || '/api/v1') + '/settings/ollama/setup-status',
          { credentials: 'include' },
        );
        const status = await r.json();
        setQuickStartStatus(status);
        if (status.status === 'ready') {
          stopPolling();
          toast.success('Local AI is ready!');
          refetchLLM();
        } else if (status.status === 'error') {
          stopPolling();
        }
      } catch {
        // ignore polling errors
      }
    }, 1500);
  }, [refetchLLM, stopPolling]);

  // ── Actions ────────────────────────────────────────────────────────
  const handleTestConnection = useCallback(() => {
    testConnection.mutate(undefined, {
      onSuccess: (result) => {
        if (result.success) {
          toast.success('Connected successfully');
          refetchLLM();
        } else {
          toast.error(result.message || 'Connection failed');
        }
      },
    });
  }, [testConnection, refetchLLM]);

  const handleDisconnect = () => {
    updateLLM.mutate(
      { provider: '', base_url: '', api_key: '', model: '' },
      {
        onSuccess: () => {
          toast.success('Disconnected. Pick a new provider below.');
          refetchLLM();
        },
      },
    );
  };

  const handleConnect = (keyOverride?: string) => {
    const trimmed = (keyOverride ?? apiKey).trim();
    if (!trimmed && selectedProvider !== 'ollama') {
      toast.error('Paste an API key first.');
      return;
    }
    const detected = detectProviderFromKey(trimmed);
    const provider = detected || selectedProvider;
    const preset = presets?.find((p) => p.name === provider);
    if (!preset) {
      toast.error(`${provider} preset not available`);
      return;
    }
    const config = provider === 'ollama'
      ? { provider: 'ollama', base_url: 'http://localhost:11434/v1', api_key: 'ollama', model: 'phi4-mini' }
      : { provider, base_url: preset.base_url, api_key: trimmed, model: preset.model };

    updateLLM.mutate(config, {
      onSuccess: () => {
        testConnection.mutate(undefined, {
          onSuccess: (result) => {
            if (result.success) {
              toast.success(`Connected to ${POPULAR_PROVIDER_CHOICES[selectedProvider].title}`);
              setApiKey('');
              refetchLLM();
            } else {
              toast.error(result.message || 'Connection failed — check your key');
              refetchLLM();
            }
          },
          onError: (err) =>
            toast.error(err instanceof Error ? err.message : 'Connection test failed — is the backend running?'),
        });
      },
      onError: (err) =>
        toast.error(err instanceof Error ? err.message : 'Could not save settings — is the backend running?'),
    });
  };

  const handleAction = (kind: string) => {
    onOpenChange(false);
    switch (kind) {
      case 'open_quick_start':
        navigate({ to: '/' });
        break;
      case 'open_settings':
        navigate({ to: '/settings', search: { tab: 'ai' } });
        break;
      case 'open_search':
        navigate({ to: '/search' });
        break;
      case 'switch_provider':
        // Modal stays open — user picks a new provider below
        onOpenChange(true);
        setSelectedProvider('gemini');
        break;
      default:
        break;
    }
  };

  // ── Derived state ──────────────────────────────────────────────────
  const err = llm?.error;
  const statusIcon = isConnected ? (
    <CheckCircle2 className="h-5 w-5 text-success" />
  ) : isBroken ? (
    <XCircle className="h-5 w-5 text-danger" />
  ) : (
    <AlertTriangle className="h-5 w-5 text-warning" />
  );

  const statusBgClass = isConnected
    ? 'bg-success/15'
    : isBroken
      ? 'bg-danger/15'
      : 'bg-warning/15';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>AI Connection</DialogTitle>
        </DialogHeader>

        {/* ── Status card ─────────────────────────────────────────── */}
        <div className={cn('rounded-xl border border-border-default p-4', statusBgClass)}>
          <div className="flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-bg-card">
              {statusIcon}
            </div>
            <div className="min-w-0 flex-1">
              {isConnected ? (
                <>
                  <p className="text-sm font-semibold text-text-primary">
                    Connected to {llm?.label || llm?.provider}
                  </p>
                  <p className="mt-0.5 text-xs text-text-tertiary">
                    Model: <span className="font-mono">{llm?.model}</span>
                  </p>
                </>
              ) : isBroken ? (
                <>
                  <p className="text-sm font-semibold text-text-primary">
                    {err?.title || 'AI is not responding'}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-text-secondary">
                    {err?.message || "Your AI provider is configured but not answering. Try a different provider below."}
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-text-primary">
                    AI is not connected
                  </p>
                  <p className="mt-0.5 text-xs text-text-tertiary">
                    Connect a provider below to enable AI scoring. Search still works without AI.
                  </p>
                </>
              )}
            </div>
          </div>

          {/* Action row when connected or broken */}
          <div className="mt-3 flex flex-wrap gap-2">
            {isConnected && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleTestConnection}
                  disabled={isWorking}
                >
                  {isWorking ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
                  Test connection
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleDisconnect}
                  disabled={isWorking}
                >
                  Disconnect
                </Button>
              </>
            )}
            {isBroken && err?.next_action && (
              <Button size="sm" onClick={() => handleAction(err.next_action.kind)}>
                {err.next_action.label}
                <ArrowRight className="ml-1.5 h-3.5 w-3.5" />
              </Button>
            )}
            {isBroken && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleTestConnection}
                  disabled={isWorking}
                >
                  {isWorking ? <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5 mr-1.5" />}
                  Test again
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleDisconnect}
                  disabled={isWorking}
                >
                  Disconnect
                </Button>
              </>
            )}
          </div>
        </div>

        {/* ── Connect or switch provider ──────────────────────────── */}
        {!isConnected && (
          <div className="space-y-3">
            <p className="text-xs font-medium uppercase tracking-wide text-text-muted">
              {isBroken ? 'Switch to a different provider' : 'Connect a provider'}
            </p>

            {/* Provider tabs */}
            <div className="flex gap-1 rounded-lg border border-border-default bg-bg-subtle p-0.5">
              {(['gemini', 'groq', 'openai-api', 'anthropic-api'] as PopularProviderName[]).map((name) => {
                const active = selectedProvider === name;
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => handleSelectProvider(name)}
                    className={cn(
                      'flex-1 rounded-md px-2 py-1.5 text-[11px] font-medium transition-colors',
                      active ? 'bg-bg-card text-text-primary shadow-sm' : 'text-text-muted hover:text-text-secondary',
                    )}
                  >
                    {name === 'gemini' ? 'Gemini' : name === 'groq' ? 'Groq' : name === 'openai-api' ? 'OpenAI' : 'Claude'}
                  </button>
                );
              })}
            </div>

            <div className="flex items-center gap-2">
              <span className={cn(
                'rounded-full px-2 py-0.5 text-[10px] font-semibold',
                POPULAR_PROVIDER_CHOICES[selectedProvider].badgeClassName,
              )}>
                {POPULAR_PROVIDER_CHOICES[selectedProvider].badge}
              </span>
            </div>

            <p className="text-[11px] leading-relaxed text-text-muted">
              {POPULAR_PROVIDER_CHOICES[selectedProvider].description}
            </p>

            {(() => {
              const keyUrl =
                selectedProvider === 'gemini' ? 'https://aistudio.google.com/apikey'
                : selectedProvider === 'groq' ? 'https://console.groq.com/keys'
                : selectedProvider === 'openai-api' ? 'https://platform.openai.com/api-keys'
                : 'https://console.anthropic.com/settings/keys';
              return (
                <a
                  href={keyUrl}
                  onClick={openExternalClick(keyUrl)}
                  className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline cursor-pointer"
                >
                  Get a {POPULAR_PROVIDER_CHOICES[selectedProvider].title} key
                  <ExternalLink className="h-3 w-3" />
                </a>
              );
            })()}

            <Input
              type="password"
              placeholder={
                selectedProvider === 'gemini' ? 'AIzaSy...'
                : selectedProvider === 'groq' ? 'gsk_...'
                : selectedProvider === 'openai-api' ? 'sk-...'
                : 'sk-ant-...'
              }
              value={apiKey}
              onChange={(e) => handleKeyChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && apiKey.trim() && !isWorking) handleConnect(); }}
              className="h-9 text-xs"
              autoComplete="off"
              autoFocus
            />

            <Button
              onClick={() => handleConnect()}
              disabled={isWorking || !apiKey.trim()}
              className="w-full"
            >
              {isWorking ? (
                <><Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> Connecting…</>
              ) : (
                <>Connect {POPULAR_PROVIDER_CHOICES[selectedProvider].title}</>
              )}
            </Button>

            <div className="flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
              <Shield className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
              <p>Your key stays on this computer and is only sent to {POPULAR_PROVIDER_CHOICES[selectedProvider].title}.</p>
            </div>
          </div>
        )}

        {/* ── Quick Start local AI (inline, not navigation) ───────── */}
        {!isConnected && (
          <div className={cn(
            'rounded-xl border p-3',
            quickStartStatus?.status === 'error' ? 'border-danger/30 bg-danger/5'
              : quickStartStatus?.status === 'ready' ? 'border-success/30 bg-success/5'
              : 'border-border-default bg-bg-subtle/40',
          )}>
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand/10">
                {quickStartStatus?.status === 'error' ? <XCircle className="h-4 w-4 text-danger" />
                  : quickStartStatus?.status === 'ready' ? <CheckCircle2 className="h-4 w-4 text-success" />
                  : quickStartActive ? <Download className="h-4 w-4 animate-pulse text-brand" />
                  : <HardDrive className="h-4 w-4 text-brand" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold text-text-primary">
                  {quickStartStatus?.status === 'ready' ? 'Local AI is ready!'
                    : quickStartStatus?.status === 'error' ? 'Setup failed'
                    : quickStartActive ? 'Setting up local AI...'
                    : 'Or use local AI (no account needed)'}
                </p>
                <p className="mt-0.5 text-[11px] text-text-muted">
                  {quickStartStatus?.step || 'Downloads a small model that runs on your computer. Private, free forever.'}
                </p>
                {quickStartActive && (
                  <Progress value={Math.round((quickStartStatus?.progress ?? 0) * 100)} className="mt-2 h-1.5" />
                )}
                {quickStartStatus?.status === 'error' && quickStartStatus.error && (
                  <p className="mt-1 text-[11px] text-danger">{quickStartStatus.error}</p>
                )}
              </div>
              {!quickStartActive && quickStartStatus?.status !== 'ready' && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={startQuickStart}
                >
                  {quickStartStatus?.status === 'error' ? 'Retry' : 'Quick Start'}
                </Button>
              )}
            </div>
          </div>
        )}

        {/* ── Footer link to health panel ─────────────────────────── */}
        <div className="border-t border-border-default pt-3">
          <button
            type="button"
            onClick={() => {
              onOpenChange(false);
              window.dispatchEvent(new CustomEvent('launchboard:open-health'));
            }}
            className="text-[11px] text-text-muted hover:text-text-secondary"
          >
            <Sparkles className="inline h-3 w-3 mr-1" />
            Open System Health for full diagnostics
          </button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
