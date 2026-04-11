import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  CheckCircle2,
  ChevronRight,
  Cloud,
  Download,
  ExternalLink,
  HardDrive,
  Key,
  Loader2,
  Settings as SettingsIcon,
  Shield,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  useLLMPresets,
  useLLMStatus,
  useTestConnection,
  useUpdateLLM,
} from '@/hooks/use-settings';
import { cn } from '@/lib/utils';

type Path = 'choose' | 'local' | 'api-key' | 'advanced';

interface OllamaSetupStatus {
  status: 'idle' | 'installing' | 'pulling' | 'configuring' | 'ready' | 'error';
  step: string;
  progress: number;
  error: string;
  model: string;
}

const STEP_MESSAGES: Record<string, string> = {
  installing: 'Setting up local AI engine...',
  pulling: 'Downloading AI model...',
  configuring: 'Configuring Launchboard...',
  ready: 'Local AI is ready!',
};

/**
 * First-run AI setup wizard for the desktop app.
 *
 * Three paths inspired by Msty Studio's onboarding:
 *   1. Quick Start — auto-install Ollama + download phi4-mini
 *   2. API key — paste a Gemini/Groq/OpenAI key
 *   3. Advanced — go to Settings for custom endpoints
 *
 * In web dev mode (not desktop), this component should not render —
 * the parent should use InlineAiConnect instead.
 */
export function AiSetupWizard() {
  const navigate = useNavigate();
  const { data: llm } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const updateLLM = useUpdateLLM();
  const testConnection = useTestConnection();

  const [path, setPath] = useState<Path>('choose');
  const [apiKey, setApiKey] = useState('');
  const [setupStatus, setSetupStatus] = useState<OllamaSetupStatus | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  const isWorking = updateLLM.isPending || testConnection.isPending;

  // If AI just became available, show success
  if (llm?.available && path !== 'local') {
    return (
      <div className="rounded-2xl border border-success/30 bg-success/5 p-5">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-success/15">
            <CheckCircle2 className="h-5 w-5 text-success" />
          </div>
          <div>
            <p className="text-sm font-semibold text-text-primary">AI is ready</p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              Jobs will be scored across 7 dimensions against your resume.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ── Quick Start: auto-install Ollama ──────────────────────────────────

  const startLocalSetup = useCallback(async () => {
    setPath('local');
    setSetupStatus({ status: 'installing', step: 'Starting setup...', progress: 0, error: '', model: 'phi4-mini' });

    // Fire the setup (returns immediately, runs in background thread)
    try {
      const resp = await fetch('/api/v1/settings/ollama/setup', { method: 'POST' });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: 'Setup failed' }));
        setSetupStatus((s) => s ? { ...s, status: 'error', error: err.detail || 'Setup failed' } : s);
        return;
      }
    } catch {
      setSetupStatus({ status: 'error', step: 'Connection failed', progress: 0, error: 'Could not reach the backend. Make sure the app is running.', model: '' });
      return;
    }

    // Poll for progress immediately — the setup runs in the background
    pollRef.current = setInterval(async () => {
      try {
        const statusResp = await fetch('/api/v1/settings/ollama/setup-status');
        const status: OllamaSetupStatus = await statusResp.json();
        setSetupStatus(status);

        if (status.status === 'ready' || status.status === 'error') {
          clearInterval(pollRef.current);
          if (status.status === 'ready') {
            toast.success('Local AI is ready!');
          }
        }
      } catch {
        // polling error — ignore, will retry
      }
    }, 1500);
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ── API Key: auto-detect provider from key format ────────────────────

  const detectProvider = (key: string): string | null => {
    const trimmed = key.trim();
    if (trimmed.startsWith('AIza')) return 'gemini';
    if (trimmed.startsWith('gsk_')) return 'groq';
    if (trimmed.startsWith('sk-ant-')) return 'anthropic-api';
    if (trimmed.startsWith('sk-')) return 'openai-api';
    return null;
  };

  const connectWithKey = () => {
    const trimmed = apiKey.trim();
    if (!trimmed) { toast.error('Paste an API key first.'); return; }

    const provider = detectProvider(trimmed);
    if (!provider) { toast.error("Couldn't detect the provider from your key. Try Settings → AI for manual setup."); return; }

    const preset = presets?.find((p) => p.name === provider);
    if (!preset) { toast.error(`${provider} preset not found.`); return; }

    updateLLM.mutate(
      { provider, base_url: preset.base_url, api_key: trimmed, model: preset.model },
      {
        onSuccess: () => {
          testConnection.mutate(undefined, {
            onSuccess: (result) => {
              if (result.success) {
                toast.success(`Connected to ${preset.label}!`);
                setApiKey('');
              } else {
                toast.error(result.message || 'Connection failed — check your key.');
              }
            },
          });
        },
      },
    );
  };

  // ── Choose path ──────────────────────────────────────────────────────

  if (path === 'choose') {
    return (
      <div className="space-y-3">
        <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand-light/30 to-brand-light/5 p-5">
          <div className="space-y-1.5 text-center">
            <p className="text-sm font-semibold text-text-primary">
              Set up AI for smarter job matching
            </p>
            <p className="text-xs text-text-tertiary">
              AI scores each job across 7 dimensions against your resume.
              Without it, you get basic keyword matching.
            </p>
          </div>

          <div className="mt-4 space-y-2">
            {/* Quick Start — local AI */}
            <button
              type="button"
              onClick={startLocalSetup}
              className="flex w-full items-center gap-3 rounded-xl border border-brand/30 bg-bg-card p-3.5 text-left transition-all hover:border-brand/50 hover:shadow-sm"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/10">
                <HardDrive className="h-5 w-5 text-brand" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">Quick Start — Local AI</span>
                  <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600">
                    Free
                  </span>
                  <span className="rounded-full bg-brand-light/60 px-2 py-0.5 text-[10px] font-medium text-brand">
                    Recommended
                  </span>
                </div>
                <p className="mt-0.5 text-[11px] text-text-tertiary">
                  Downloads a small AI model (~2.5 GB) that runs on your computer.
                  Private, free forever, no accounts needed.
                </p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
            </button>

            {/* API key */}
            <button
              type="button"
              onClick={() => setPath('api-key')}
              className="flex w-full items-center gap-3 rounded-xl border border-border-default bg-bg-card p-3.5 text-left transition-all hover:border-brand/30 hover:shadow-sm"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-bg-subtle">
                <Cloud className="h-5 w-5 text-text-muted" />
              </div>
              <div className="min-w-0 flex-1">
                <span className="text-sm font-medium text-text-primary">I have an API key</span>
                <p className="mt-0.5 text-[11px] text-text-tertiary">
                  Gemini (free), Groq (free), OpenAI, or Anthropic. Paste your key and go.
                </p>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />
            </button>

            {/* Advanced */}
            <button
              type="button"
              onClick={() => navigate({ to: '/settings', search: { tab: 'ai' } })}
              className="flex w-full items-center gap-3 rounded-xl border border-border-default bg-bg-card p-3 text-left transition-all hover:border-brand/30"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-subtle">
                <SettingsIcon className="h-4 w-4 text-text-muted" />
              </div>
              <div className="min-w-0 flex-1">
                <span className="text-xs font-medium text-text-secondary">
                  Advanced — custom endpoint, existing Ollama, or subscription proxy
                </span>
              </div>
              <ChevronRight className="h-3.5 w-3.5 shrink-0 text-text-muted" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Local AI setup progress ──────────────────────────────────────────

  if (path === 'local') {
    const s = setupStatus;
    const isError = s?.status === 'error';
    const isReady = s?.status === 'ready';
    const progressPct = Math.round((s?.progress ?? 0) * 100);

    return (
      <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand-light/30 to-brand-light/5 p-5">
        <div className="flex items-start gap-3">
          <div className={cn(
            'flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
            isError ? 'bg-danger/15' : isReady ? 'bg-success/15' : 'bg-brand/15',
          )}>
            {isError ? (
              <XCircle className="h-5 w-5 text-danger" />
            ) : isReady ? (
              <CheckCircle2 className="h-5 w-5 text-success" />
            ) : (
              <Download className="h-5 w-5 animate-pulse text-brand" />
            )}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-text-primary">
              {isReady ? 'Local AI is ready!' : isError ? 'Setup failed' : 'Setting up local AI...'}
            </p>
            <p className="mt-0.5 text-xs text-text-tertiary">
              {s?.step || STEP_MESSAGES[s?.status ?? 'installing'] || 'Preparing...'}
            </p>

            {!isReady && !isError && (
              <div className="mt-3">
                <Progress value={progressPct} className="h-2" />
                <p className="mt-1 text-[10px] text-text-muted">{progressPct}%</p>
              </div>
            )}

            {isError && s?.error && (
              <div className="mt-2 space-y-2">
                <p className="text-xs text-danger">{s.error}</p>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={startLocalSetup}>
                    Try again
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => setPath('api-key')}>
                    Use an API key instead
                  </Button>
                </div>
              </div>
            )}

            {isReady && (
              <div className="mt-2 flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
                <Shield className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                <p>AI runs entirely on your computer. Nothing leaves your machine.</p>
              </div>
            )}
          </div>
        </div>

        {!isReady && !isError && (
          <button
            type="button"
            onClick={() => { if (pollRef.current) clearInterval(pollRef.current); setPath('choose'); }}
            className="mt-3 text-[10px] text-text-muted transition-colors hover:text-text-secondary"
          >
            Cancel and choose a different option
          </button>
        )}
      </div>
    );
  }

  // ── API key path ─────────────────────────────────────────────────────

  if (path === 'api-key') {
    const detected = apiKey.trim() ? detectProvider(apiKey.trim()) : null;
    const detectedLabel = detected === 'gemini' ? 'Google Gemini' : detected === 'groq' ? 'Groq' : detected === 'openai-api' ? 'OpenAI' : detected === 'anthropic-api' ? 'Anthropic Claude' : null;

    return (
      <div className="rounded-2xl border border-brand/20 bg-gradient-to-br from-brand-light/30 to-brand-light/5 p-5">
        <div className="flex items-center gap-2.5 mb-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand/10">
            <Key className="h-4 w-4 text-brand" />
          </div>
          <div>
            <p className="text-sm font-semibold text-text-primary">Paste your API key</p>
            <p className="text-[11px] text-text-tertiary">
              We'll auto-detect the provider from your key format.
            </p>
          </div>
        </div>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Input
              type="password"
              placeholder="Paste API key here..."
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && apiKey.trim()) connectWithKey(); }}
              className="h-9 text-xs"
              autoComplete="off"
              autoFocus
            />
            {detectedLabel && (
              <p className="text-[11px] text-success font-medium">
                <Sparkles className="inline h-3 w-3 mr-0.5" />
                Detected: {detectedLabel}
              </p>
            )}
          </div>

          <Button
            size="sm"
            className="w-full"
            onClick={connectWithKey}
            disabled={isWorking || !apiKey.trim()}
          >
            {isWorking ? (
              <><Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> Connecting...</>
            ) : (
              'Connect'
            )}
          </Button>

          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-text-muted">
            <span className="font-medium text-text-secondary">Free keys:</span>
            <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-brand hover:underline">
              Gemini <ExternalLink className="h-2.5 w-2.5" />
            </a>
            <a href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 text-brand hover:underline">
              Groq <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </div>

          <div className="flex items-start gap-1.5 text-[10px] leading-relaxed text-text-muted">
            <Shield className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
            <p>Your key stays on this computer and is only sent to that provider.</p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setPath('choose')}
          className="mt-3 text-[10px] text-text-muted transition-colors hover:text-text-secondary"
        >
          ← Back to options
        </button>
      </div>
    );
  }

  return null;
}
