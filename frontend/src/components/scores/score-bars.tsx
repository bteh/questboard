import { SCORE_DIMENSIONS } from '@/utils/constants';
import { scoreColor, scoreColorHex } from '@/utils/colors';
import type { ApplicationResponse, ScoreEvidenceEntry } from '@/types/application';

interface ScoreBarsProps {
  app: ApplicationResponse;
}

const GRADIENT_MAP: Record<ReturnType<typeof scoreColor>, string> = {
  high: 'linear-gradient(90deg, #34D399, #10B981)',
  'mid-high': 'linear-gradient(90deg, #93C5FD, #3B82F6)',
  mid: 'linear-gradient(90deg, #FCD34D, #F59E0B)',
  low: 'linear-gradient(90deg, #FCA5A5, #EF4444)',
};

/** Score-column key -> evidence-dict key (set by the keyword scorer). */
const EVIDENCE_KEY_MAP: Record<string, string> = {
  technical_score: 'technical_skills',
  leadership_score: 'leadership_signal',
  career_progression_score: 'career_progression',
  platform_building_score: 'platform_building',
  comp_potential_score: 'comp_potential',
  company_trajectory_score: 'company_trajectory',
  culture_fit_score: 'culture_fit',
};

const MAX_MATCHED = 8;
const MAX_MISSING = 5;

/**
 * Matched/missing keyword chips under a dimension bar. Renders nothing when
 * there is no evidence for the dimension (older records, LLM-only scores).
 */
function EvidenceChips({ evidence }: { evidence: ScoreEvidenceEntry }) {
  const matched = Array.isArray(evidence.matched) ? evidence.matched : [];
  const missing = Array.isArray(evidence.missing_top) ? evidence.missing_top : [];
  if (matched.length === 0 && missing.length === 0) return null;

  const visibleMatched = matched.slice(0, MAX_MATCHED);
  const visibleMissing = missing.slice(0, MAX_MISSING);
  const hiddenMatched = matched.length - visibleMatched.length;

  return (
    <div className="flex flex-wrap items-center gap-1">
      {visibleMatched.map((term) => (
        <span
          key={`m-${term}`}
          title="Matched in the job description"
          className="inline-flex items-center rounded-full border border-success/20 bg-success/10 px-1.5 py-px text-[10px] leading-4 text-success"
        >
          {term}
        </span>
      ))}
      {hiddenMatched > 0 && (
        <span className="text-[10px] leading-4 text-text-muted">+{hiddenMatched} more</span>
      )}
      {visibleMissing.map((term) => (
        <span
          key={`x-${term}`}
          title="In the job description but not in your profile"
          className="inline-flex items-center rounded-full border border-red-200 bg-red-50 px-1.5 py-px text-[10px] leading-4 text-red-700/80 line-through decoration-red-300 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300/80 dark:decoration-red-800"
        >
          {term}
        </span>
      ))}
    </div>
  );
}

export function ScoreBars({ app }: ScoreBarsProps) {
  const scoreEvidence = app.score_evidence ?? null;

  return (
    <div className="space-y-2.5">
      {SCORE_DIMENSIONS.map(({ key, label, tooltip, weight }, index) => {
        const value = (app as unknown as Record<string, unknown>)[key] as number | null;
        const pct = value != null ? Math.min(value, 100) : 0;
        const level = scoreColor(value);
        const evidence = scoreEvidence?.[EVIDENCE_KEY_MAP[key] ?? key] ?? null;
        return (
          <div key={key} className="space-y-1">
            <div className="flex items-center gap-3">
              <div className="w-[140px] shrink-0 text-xs text-text-secondary" title={tooltip}>
                {label}
                <span className="text-text-muted ml-1 text-[10px]">{Math.round(weight * 100)}%</span>
              </div>
              <div className="flex-1 h-2.5 rounded-full bg-bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${pct}%`,
                    background: GRADIENT_MAP[level],
                    transition: `width 700ms cubic-bezier(0.4,0,0.2,1) ${index * 50}ms`,
                  }}
                />
              </div>
              <div
                className="w-8 text-right text-xs font-semibold tabular-nums"
                style={{ color: scoreColorHex(value) }}
              >
                {value != null ? Math.round(value) : '—'}
              </div>
            </div>
            {evidence && (
              <div className="pl-[152px] pr-11">
                <EvidenceChips evidence={evidence} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
