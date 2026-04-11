import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  FileText,
  Key,
  Loader2,
  RefreshCw,
  Search,
  Server,
  XCircle,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useSystemHealth } from '@/hooks/use-system-health';
import type { Subsystem, SubsystemStatus } from '@/api/health';
import { cn } from '@/lib/utils';

interface SystemHealthPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when a fix_action is clicked (used to open other modals). */
  onOpenDiagnostic?: () => void;
}

const SUBSYSTEM_LABELS: Record<string, { label: string; Icon: typeof Server }> = {
  backend: { label: 'Backend', Icon: Server },
  ai: { label: 'AI', Icon: Brain },
  resume: { label: 'Resume', Icon: FileText },
  search: { label: 'Search', Icon: Search },
  keychain: { label: 'Key storage', Icon: Key },
};

const STATUS_STYLES: Record<SubsystemStatus, { bg: string; dot: string; text: string; Icon: typeof CheckCircle2 }> = {
  ok: { bg: 'bg-success/10', dot: 'bg-success', text: 'text-success', Icon: CheckCircle2 },
  warn: { bg: 'bg-warning/10', dot: 'bg-warning', text: 'text-warning', Icon: AlertTriangle },
  error: { bg: 'bg-danger/10', dot: 'bg-danger', text: 'text-danger', Icon: XCircle },
};

/**
 * Unified health dashboard. Shows the state of every subsystem at a
 * glance with one-click fix buttons. When something is broken, the
 * user sees EXACTLY what's wrong and EXACTLY what to do — no guessing.
 */
export function SystemHealthPanel({ open, onOpenChange, onOpenDiagnostic }: SystemHealthPanelProps) {
  const navigate = useNavigate();
  const { data, isLoading, refetch, isFetching } = useSystemHealth(open);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggleExpanded = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleFix = (kind: string) => {
    onOpenChange(false);
    switch (kind) {
      case 'open_diagnostic':
      case 'reconnect':
      case 'switch_provider':
        onOpenDiagnostic?.();
        break;
      case 'open_settings':
        navigate({ to: '/settings', search: { tab: 'ai' } });
        break;
      case 'open_search':
        navigate({ to: '/search' });
        break;
      case 'open_quick_start':
        navigate({ to: '/' });
        break;
      default:
        break;
    }
  };

  const handleCopyDiagnostics = () => {
    if (!data) return;
    const blob = JSON.stringify(data, null, 2);
    navigator.clipboard.writeText(blob).then(
      () => toast.success('Diagnostics copied to clipboard'),
      () => toast.error('Copy failed'),
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <div className="flex items-center justify-between gap-3">
            <DialogTitle>System Health</DialogTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
            >
              {isFetching ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </DialogHeader>

        {isLoading && !data ? (
          <div className="py-12 flex items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-text-muted" />
          </div>
        ) : data ? (
          <>
            {/* Overall status banner */}
            {data.overall !== 'ok' && (
              <div className={cn(
                'rounded-lg border px-3 py-2 text-xs font-medium',
                data.overall === 'error'
                  ? 'border-danger/30 bg-danger/10 text-danger'
                  : 'border-warning/30 bg-warning/10 text-warning',
              )}>
                {data.overall === 'error'
                  ? 'One or more subsystems need attention. Click the error rows below to fix.'
                  : 'Everything is working, but there are a few things to optimize.'}
              </div>
            )}

            {/* Subsystem rows */}
            <div className="space-y-1.5">
              {(Object.entries(data.subsystems) as [string, Subsystem][]).map(([key, sub]) => {
                const meta = SUBSYSTEM_LABELS[key] || { label: key, Icon: Server };
                const styles = STATUS_STYLES[sub.status];
                const isExpanded = expanded.has(key);

                return (
                  <div
                    key={key}
                    className="rounded-lg border border-border-default bg-bg-card overflow-hidden"
                  >
                    <button
                      type="button"
                      onClick={() => toggleExpanded(key)}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-bg-subtle transition-colors"
                    >
                      <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-lg', styles.bg)}>
                        <meta.Icon className={cn('h-4 w-4', styles.text)} />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-text-primary">{meta.label}</span>
                          <span className={cn('h-1.5 w-1.5 rounded-full', styles.dot)} />
                        </div>
                        <p className={cn('mt-0.5 text-xs truncate', sub.status === 'ok' ? 'text-text-tertiary' : styles.text)}>
                          {sub.summary}
                        </p>
                      </div>
                      {sub.fix_action && (
                        <Button
                          size="sm"
                          variant={sub.status === 'error' ? 'default' : 'outline'}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleFix(sub.fix_action!.kind);
                          }}
                        >
                          {sub.fix_action.label}
                        </Button>
                      )}
                      {isExpanded ? <ChevronDown className="h-4 w-4 shrink-0 text-text-muted" /> : <ChevronRight className="h-4 w-4 shrink-0 text-text-muted" />}
                    </button>
                    {isExpanded && sub.detail && (
                      <div className="border-t border-border-default bg-bg-subtle/40 px-3 py-2.5 text-[11px] leading-relaxed text-text-secondary">
                        {sub.detail}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Copy diagnostics for bug reports */}
            <div className="border-t border-border-default pt-3 flex items-center justify-between gap-3">
              <p className="text-[11px] text-text-muted">
                Include this info when reporting bugs
              </p>
              <Button size="sm" variant="outline" onClick={handleCopyDiagnostics}>
                <Copy className="h-3.5 w-3.5 mr-1.5" />
                Copy diagnostics
              </Button>
            </div>
          </>
        ) : (
          <p className="py-6 text-center text-sm text-text-muted">
            Could not load system health. Check your backend connection.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
