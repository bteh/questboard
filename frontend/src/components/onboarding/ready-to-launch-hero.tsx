import { useNavigate } from '@tanstack/react-router';
import {
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  MapPin,
  Settings as SettingsIcon,
  Sparkles,
  Tag,
} from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { ConnectAiPopover } from '@/components/onboarding/connect-ai-popover';
import { useSearchContext } from '@/contexts/search-context';
import { useLLMStatus } from '@/hooks/use-settings';
import { useOnboardingState, useStartOnboardingSearch } from '@/hooks/use-workspace';
import { getSearchAreaSummary } from '@/lib/search-area';
import {
  buildSearchRunSnapshot,
  buildSearchSnapshotMetadataFromPreferences,
} from '@/lib/search-preferences';
import type { SearchRunSnapshot } from '@/types/search';

/**
 * "Ready to launch" state shown on the dashboard between completing the
 * onboarding wizard and starting the very first search. The wizard now
 * SAVES preferences and routes here so the user owns the moment of
 * clicking Start instead of feeling rushed past their settings.
 *
 * Visible when:
 * - workspace has saved preferences (resume uploaded or roles/keywords set)
 * - no search has ever been started (`has_started_search === false`)
 * - the search context is idle
 */
export function ReadyToLaunchHero() {
  const navigate = useNavigate();
  const { data: onboarding } = useOnboardingState();
  const { data: llm } = useLLMStatus();
  const { activate } = useSearchContext();
  const startOnboardingSearch = useStartOnboardingSearch();

  if (!onboarding?.preferences) return null;

  const prefs = onboarding.preferences;
  const aiAvailable = llm?.available ?? false;
  const resumeFilename = onboarding.resume.exists ? onboarding.resume.filename : null;
  const searchAreaSummary = getSearchAreaSummary(
    prefs.workplace_preference,
    prefs.preferred_places,
    'onboarding',
  );

  const handleStart = () => {
    startOnboardingSearch.mutate(prefs, {
      onSuccess: (result) => {
        const snapshot: SearchRunSnapshot = buildSearchRunSnapshot({
          profile: 'workspace',
          request: {
            mode: 'search_score',
            roles: prefs.roles,
            locations: prefs.preferred_places.map((place) => place.label),
            keywords: prefs.keywords,
            companies: prefs.companies,
            include_remote: prefs.workplace_preference !== 'location_only',
            workplace_preference: prefs.workplace_preference,
            max_days_old: prefs.max_days_old,
            include_linkedin_jobs: prefs.include_linkedin_jobs,
            use_ai: aiAvailable,
          },
          metadata: buildSearchSnapshotMetadataFromPreferences(prefs),
        });
        activate(result.run_id, 'search_score', snapshot);
        try {
          window.localStorage.setItem('launchboard:first-run-pending', '1');
        } catch {
          // localStorage may be disabled in some sandboxed shells; non-fatal.
        }
        toast.success(
          aiAvailable ? 'Starting your AI-ranked search…' : 'Starting your search…',
        );
        navigate({ to: '/search' });
      },
      onError: (error) =>
        toast.error(error instanceof Error ? error.message : 'Failed to start search'),
    });
  };

  const isStarting = startOnboardingSearch.isPending;

  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4">
      <div className="w-full max-w-2xl space-y-8">
        <div className="space-y-3 text-center">
          <h1 className="text-balance text-4xl font-semibold tracking-tight text-text-primary sm:text-5xl">
            You're ready to launch
          </h1>
          <p className="mx-auto max-w-md text-balance text-sm leading-relaxed text-text-tertiary sm:text-base">
            Review your search below. Click start when you're ready and we'll search 14+ job boards
            in the background.
          </p>
        </div>

        {/* Setup summary */}
        <div className="space-y-3 rounded-2xl border border-border-default bg-bg-card p-5 shadow-sm">
          <SummaryRow
            icon={<FileText className="h-4 w-4 text-text-muted" />}
            label="Resume"
            value={resumeFilename ?? 'Not uploaded'}
            ok={!!resumeFilename}
          />
          <SummaryRow
            icon={<Tag className="h-4 w-4 text-text-muted" />}
            label="Target roles"
            value={prefs.roles.length > 0 ? prefs.roles.slice(0, 3).join(', ') + (prefs.roles.length > 3 ? ` +${prefs.roles.length - 3}` : '') : 'Will use resume'}
            ok={prefs.roles.length > 0 || !!resumeFilename}
          />
          <SummaryRow
            icon={<MapPin className="h-4 w-4 text-text-muted" />}
            label="Where"
            value={searchAreaSummary.shortLabel}
            ok={prefs.preferred_places.length > 0 || prefs.workplace_preference !== 'location_only'}
          />
          <SummaryRow
            icon={<Sparkles className="h-4 w-4 text-text-muted" />}
            label="AI ranking"
            value={aiAvailable ? (llm?.label ?? 'Connected') : 'Not connected (basic ranking)'}
            ok={aiAvailable}
            optional
          />
        </div>

        {/* Primary CTA */}
        <div className="space-y-3">
          <Button
            onClick={handleStart}
            disabled={isStarting}
            className="h-12 w-full text-base"
            size="lg"
          >
            {isStarting ? (
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
            ) : null}
            Start your first search
            {!isStarting && <ArrowRight className="ml-2 h-5 w-5" />}
          </Button>

          <div className="flex items-center justify-center gap-4 text-xs">
            <button
              type="button"
              onClick={() => navigate({ to: '/settings', search: { tab: 'search' } })}
              className="inline-flex items-center gap-1.5 text-text-muted transition-colors hover:text-text-secondary"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              Edit search settings
            </button>
            {!aiAvailable && (
              <>
                <span className="text-border-default">·</span>
                <ConnectAiPopover side="bottom" align="center">
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 text-text-muted transition-colors hover:text-text-secondary"
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    Connect AI for better ranking
                  </button>
                </ConnectAiPopover>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface SummaryRowProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  ok: boolean;
  optional?: boolean;
}

function SummaryRow({ icon, label, value, ok, optional }: SummaryRowProps) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-subtle">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
        <p className="truncate text-sm text-text-secondary">{value}</p>
      </div>
      {ok ? (
        <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
      ) : optional ? (
        <span className="text-[10px] font-medium uppercase tracking-wide text-text-muted">Optional</span>
      ) : null}
    </div>
  );
}
