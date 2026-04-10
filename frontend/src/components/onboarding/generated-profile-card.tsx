import { useState } from 'react';
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Compass,
  ExternalLink,
  Loader2,
  MapPin,
  Sparkles,
  Tag,
  Target,
  TrendingUp,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { GeneratedProfile } from '@/types/workspace';

/**
 * Renders an LLM-generated profile next to (or instead of) the hardcoded
 * archetype templates in the ReadyToLaunchHero. The whole point is to
 * show the user that Launchboard tailored a profile *specifically for
 * them* — covering niches we never modeled — instead of forcing them
 * into the closest preset.
 *
 * UX principles:
 *   - Lead with the one-line "detected_archetype" so the user can
 *     immediately tell whether the LLM understood them
 *   - Surface confidence + reasoning so the user can sanity-check
 *   - Show what the LLM is going to use (scrapers, keywords, comp
 *     targets) so nothing is hidden
 *   - Make accepting it a single click; make picking a template
 *     instead obvious; make editing manually possible but secondary
 */
interface GeneratedProfileCardProps {
  profile: GeneratedProfile;
  isLoading?: boolean;
  onAccept: () => void;
  onPickTemplate?: () => void;
  acceptDisabled?: boolean;
}

const SENIORITY_LABELS: Record<string, string> = {
  entry: 'Entry level',
  mid: 'Mid level',
  senior: 'Senior',
  staff: 'Staff',
  principal: 'Principal',
  exec: 'Executive',
};

export function GeneratedProfileCard({
  profile,
  isLoading,
  onAccept,
  onPickTemplate,
  acceptDisabled,
}: GeneratedProfileCardProps) {
  const [expanded, setExpanded] = useState(false);
  const confidencePct = Math.round((profile.confidence ?? 0) * 100);
  const seniorityLabel = SENIORITY_LABELS[profile.seniority_signal] ?? profile.seniority_signal;

  return (
    <div className="rounded-2xl border border-brand/30 bg-gradient-to-br from-brand-light/40 to-brand-light/10 p-5 shadow-sm">
      {/* Header — archetype + confidence */}
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand/15">
          <Brain className="h-5 w-5 text-brand" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-brand-light/60 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-brand">
              AI-tailored profile
            </span>
            {profile.cached && (
              <span className="rounded-full bg-text-muted/10 px-2 py-0.5 text-[10px] font-medium text-text-muted">
                cached
              </span>
            )}
            <span className="text-[10px] text-text-muted">
              {confidencePct}% confidence
            </span>
          </div>
          <h3 className="mt-1 text-sm font-semibold leading-snug text-text-primary">
            {profile.detected_archetype}
          </h3>
          <p className="mt-1.5 text-xs leading-relaxed text-text-tertiary">
            {profile.reasoning}
          </p>
        </div>
      </div>

      {/* Quick summary chips */}
      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
        <SummaryChip
          icon={<Target className="h-3.5 w-3.5" />}
          label="Career target"
          value={profile.career_target}
        />
        <SummaryChip
          icon={<TrendingUp className="h-3.5 w-3.5" />}
          label="Seniority signal"
          value={seniorityLabel}
        />
        <SummaryChip
          icon={<MapPin className="h-3.5 w-3.5" />}
          label="Search via"
          value={`${profile.enabled_scrapers.length} job source${profile.enabled_scrapers.length === 1 ? '' : 's'}`}
        />
        <SummaryChip
          icon={<Sparkles className="h-3.5 w-3.5" />}
          label="Comp target"
          value={
            profile.compensation.target_total_comp
              ? `$${(profile.compensation.target_total_comp / 1000).toFixed(0)}K`
              : '—'
          }
        />
      </div>

      {/* Expandable details */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mt-3 flex w-full items-center justify-between rounded-lg border border-border-default/60 bg-bg-card/80 px-3 py-2 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card"
      >
        <span>{expanded ? 'Hide details' : 'Show what the AI picked'}</span>
        {expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 rounded-lg border border-border-default/60 bg-bg-card/80 p-3">
          {/* Target roles */}
          {profile.target_roles.length > 0 && (
            <DetailSection icon={<Compass className="h-3 w-3" />} label="Target roles">
              <div className="flex flex-wrap gap-1">
                {profile.target_roles.map((role) => (
                  <span
                    key={role}
                    className="inline-flex items-center rounded-md bg-bg-subtle px-2 py-0.5 text-[11px] text-text-secondary ring-1 ring-border-default"
                  >
                    {role}
                  </span>
                ))}
              </div>
            </DetailSection>
          )}

          {/* Technical keywords */}
          {profile.keywords.technical.length > 0 && (
            <DetailSection icon={<Tag className="h-3 w-3" />} label="Technical keywords">
              <div className="flex flex-wrap gap-1">
                {profile.keywords.technical.slice(0, 12).map((kw) => (
                  <span
                    key={kw}
                    className="inline-flex items-center rounded-md bg-brand-light/30 px-2 py-0.5 text-[11px] text-text-secondary ring-1 ring-brand/20"
                  >
                    {kw}
                  </span>
                ))}
                {profile.keywords.technical.length > 12 && (
                  <span className="inline-flex items-center text-[10px] text-text-muted">
                    +{profile.keywords.technical.length - 12} more
                  </span>
                )}
              </div>
            </DetailSection>
          )}

          {/* Enabled scrapers */}
          {profile.enabled_scrapers.length > 0 && (
            <DetailSection icon={<Check className="h-3 w-3" />} label="Job sources">
              <p className="text-[11px] text-text-secondary leading-relaxed">
                {profile.enabled_scrapers.join(', ')}
              </p>
            </DetailSection>
          )}

          {/* External boards we don't yet scrape */}
          {profile.recommended_external_boards.length > 0 && (
            <DetailSection icon={<ExternalLink className="h-3 w-3" />} label="Niche boards to also check (manual)">
              <ul className="space-y-1">
                {profile.recommended_external_boards.map((url) => (
                  <li key={url}>
                    <a
                      href={url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-[11px] text-brand hover:underline"
                    >
                      {url.replace(/^https?:\/\//, '').replace(/\/$/, '')}
                      <ExternalLink className="h-3 w-3" />
                    </a>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}

          {/* Strengths + gaps */}
          {profile.primary_strengths.length > 0 && (
            <DetailSection label="What's strong on your resume">
              <ul className="space-y-1">
                {profile.primary_strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[11px] text-text-secondary">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-success" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}
          {profile.development_areas.length > 0 && (
            <DetailSection label="Where your resume is thin">
              <ul className="space-y-1">
                {profile.development_areas.map((s, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[11px] text-text-tertiary">
                    <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-amber-500" />
                    <span>{s}</span>
                  </li>
                ))}
              </ul>
            </DetailSection>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex flex-col gap-2 sm:flex-row">
        <Button
          onClick={onAccept}
          disabled={isLoading || acceptDisabled}
          className="flex-1"
        >
          {isLoading ? (
            <>
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              Saving…
            </>
          ) : (
            <>
              Use this AI-tailored profile
            </>
          )}
        </Button>
        {onPickTemplate && (
          <Button
            variant="outline"
            onClick={onPickTemplate}
            disabled={isLoading}
          >
            Pick a template instead
          </Button>
        )}
      </div>
    </div>
  );
}

interface SummaryChipProps {
  icon: React.ReactNode;
  label: string;
  value: string;
}

function SummaryChip({ icon, label, value }: SummaryChipProps) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border-default/60 bg-bg-card/70 px-2.5 py-2">
      <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-brand-light/40 text-brand">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-[9px] font-medium uppercase tracking-wide text-text-muted">{label}</p>
        <p className="truncate text-[11px] font-medium text-text-primary">{value}</p>
      </div>
    </div>
  );
}

interface DetailSectionProps {
  icon?: React.ReactNode;
  label: string;
  children: React.ReactNode;
}

function DetailSection({ icon, label, children }: DetailSectionProps) {
  return (
    <div>
      <div className={cn('mb-1 flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-text-muted')}>
        {icon}
        <span>{label}</span>
      </div>
      {children}
    </div>
  );
}
