import { Loader2 } from 'lucide-react';
import { SearchAreaSection } from '@/components/shared/search-area-section';
import { JobBoardOptionsSection } from '@/components/shared/job-board-options-section';
import { FilterToggleButton } from '@/components/shared/FilterToggleButton';
import { FilterChips } from '@/components/shared/FilterChips';
import { Textarea } from '@/components/ui/textarea';
import { Slider } from '@/components/ui/slider';
import { Skeleton } from '@/components/ui/skeleton';
import { cx } from '@questboard/ui';
import type { MatchStrictness, SearchRequest } from '@/types/search';
import type { OnboardingState, PlaceSelection } from '@/types/workspace';
import type { WorkplacePreference } from '@/lib/profile-preferences';
import type { ScraperSource } from '@/api/scrapers';
import { MatchStrictnessControl, SuggestLoadingState } from './search-leaf';
import './restock.css';

/* The restock form, trade paper: one paper card, hairline rows, mono data,
   the sage primary. Same fields, same handlers, same request as the old
   Search page; only the chrome changed. */

type ModeInfo = { label: string; desc: string; detail: string };

type SourceCategoryGroup = { label: string; cat: string; sources: ScraperSource[] };

interface SearchConfigFormProps {
  sourceCount: number;
  llmAvailable: boolean;
  showSources: boolean;
  setShowSources: (value: boolean) => void;
  sourcesByCategory: SourceCategoryGroup[];
  canSuggest: boolean | '' | undefined;
  roles: string;
  setRoles: (value: string) => void;
  keywords: string;
  setKeywords: (value: string) => void;
  handleSuggest: () => void;
  suggestPending: boolean;
  configLoading: boolean;
  filtersExpanded: boolean;
  setShowFilters: (value: boolean) => void;
  filterSummary: (string | null)[];
  locations: PlaceSelection[];
  setLocations: (places: PlaceSelection[]) => void;
  workplacePreference: WorkplacePreference;
  setWorkplacePreference: (value: WorkplacePreference) => void;
  includeLinkedInJobs: boolean;
  setIncludeLinkedInJobs: (value: boolean) => void;
  matchStrictness: MatchStrictness;
  setMatchStrictness: (value: MatchStrictness) => void;
  maxDays: number;
  setMaxDays: (value: number) => void;
  searchAreaOverridesSavedDefaults: boolean;
  applySavedSearchArea: () => void;
  handleSaveSearchAreaDefaults: () => void;
  savePreferencesPending: boolean;
  onboarding: OnboardingState | undefined;
  canUseResumeFallback: boolean;
  suggestedCompanies: string[];
  setSuggestedCompanies: (updater: (prev: string[]) => string[]) => void;
  selectedMode: SearchRequest['mode'];
  setSelectedMode: (value: SearchRequest['mode']) => void;
  modeLabels: Record<SearchRequest['mode'], ModeInfo>;
  handleStart: () => void;
  startSearchPending: boolean;
  missingSearchTerms: boolean;
  missingLocations: boolean;
  parsedRoles: string[];
  parsedKeywords: string[];
  usesRemoteFallback: boolean;
  startLabel: string;
}

export function SearchConfigForm({
  sourceCount,
  llmAvailable,
  showSources,
  setShowSources,
  sourcesByCategory,
  canSuggest,
  roles,
  setRoles,
  keywords,
  setKeywords,
  handleSuggest,
  suggestPending,
  configLoading,
  filtersExpanded,
  setShowFilters,
  filterSummary,
  locations,
  setLocations,
  workplacePreference,
  setWorkplacePreference,
  includeLinkedInJobs,
  setIncludeLinkedInJobs,
  matchStrictness,
  setMatchStrictness,
  maxDays,
  setMaxDays,
  searchAreaOverridesSavedDefaults,
  applySavedSearchArea,
  handleSaveSearchAreaDefaults,
  savePreferencesPending,
  onboarding,
  canUseResumeFallback,
  suggestedCompanies,
  setSuggestedCompanies,
  selectedMode,
  setSelectedMode,
  modeLabels,
  handleStart,
  startSearchPending,
  missingSearchTerms,
  missingLocations,
  parsedRoles,
  parsedKeywords,
  usesRemoteFallback,
  startLabel,
}: SearchConfigFormProps) {
  return (
    <div className="qb-restock" style={{ maxWidth: 820, margin: '0 auto', padding: '0 44px 96px' }}>
      <div className="qb-restock-head">
        <h1>Restock the board</h1>
        <span className="qb-headnote">
          {sourceCount > 0 ? `${sourceCount} sources` : 'live sources'}
        </span>
      </div>
      <p className="qb-restock-sub">
        Pulls fresh quests straight from the sources onto the board. Nothing here changes what you already clipped.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {!llmAvailable && (
          <div className="qb-restock-note">
            <b>The board restocks and ranks on its own. No AI needed.</b> Connect Claude or Codex
            in Settings for resume-fit ranking.
          </div>
        )}

        {/* Source transparency */}
        {sourceCount > 0 && (
          <div>
            <button
              type="button"
              className="qb-sources-toggle"
              aria-expanded={showSources}
              onClick={() => setShowSources(!showSources)}
            >
              <span>
                Restocks from <span className="qb-num">{sourceCount}</span> sources:{' '}
                {sourcesByCategory.slice(0, 4).map((g) => g.sources[0].display_name).join(', ')}
                {sourceCount > 4 && ` and ${sourceCount - 4} more`}
              </span>
              <span aria-hidden="true">{showSources ? '−' : '+'}</span>
            </button>
            {showSources && (
              <div className="qb-sources-list">
                {sourcesByCategory.map((group) => (
                  <div key={group.label} className="qb-srcrow">
                    <span className="qb-srccat">{group.label}</span>
                    <span className="qb-srcnames">
                      {group.sources.map((s) => s.display_name).join(', ')}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="qb-restock-card">
          {configLoading ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-16 w-full" />)}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
              {/* Suggest CTA when fields are empty or sparse (1 role = fallback
                  from resume title). The keyword extractor gives ~15 terms even
                  without AI, so emptiness alone is not the signal. */}
              {((!roles && !keywords) || (roles && roles.length <= 1 && canSuggest)) && (suggestPending ? (
                <SuggestLoadingState />
              ) : canSuggest ? (
                <button type="button" className="qb-restock-note" onClick={handleSuggest}>
                  <b>Fill this in from your resume.</b> One click suggests roles, keywords,
                  and places.
                </button>
              ) : !llmAvailable && (
                <div className="qb-restock-note">
                  <b>
                    {canUseResumeFallback
                      ? 'Restock straight from your uploaded resume, or type roles below.'
                      : 'Type your target roles below to get going.'}
                  </b>
                  <div className="qb-notefoot">
                    {onboarding?.resume.exists
                      ? 'Your resume alone is enough for a first restock.'
                      : 'The board works without a resume or AI. Add them later.'}
                  </div>
                </div>
              ))}

              {/* Roles and keywords */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
                <div>
                  <label className="qb-flabel" htmlFor="restock-roles">Target roles</label>
                  <Textarea
                    id="restock-roles"
                    value={roles}
                    onChange={(e) => setRoles(e.target.value)}
                    rows={4}
                    placeholder="e.g. Marketing Manager&#10;Product Designer&#10;Nurse Practitioner"
                  />
                  <p className="qb-fhelp">Type one role per line.</p>
                </div>
                <div>
                  <label className="qb-flabel" htmlFor="restock-keywords">Keywords</label>
                  <Textarea
                    id="restock-keywords"
                    value={keywords}
                    onChange={(e) => setKeywords(e.target.value)}
                    rows={4}
                    placeholder="e.g. Project Management&#10;Patient Care&#10;Data Analysis"
                  />
                  <p className="qb-fhelp">Type one keyword per line.</p>
                </div>
              </div>

              {canSuggest && roles ? (
                <div>
                  <button
                    type="button"
                    className="qb-textlink"
                    style={{ fontSize: 13.5 }}
                    onClick={handleSuggest}
                    disabled={suggestPending}
                  >
                    {suggestPending ? 'Reading your resume...' : 'Re-fill from resume'}
                  </button>
                </div>
              ) : null}

              {/* Collapsible filters */}
              <div>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
                  <FilterToggleButton
                    open={filtersExpanded}
                    count={filterSummary.length}
                    onClick={() => setShowFilters(!filtersExpanded)}
                  />
                  {!filtersExpanded && filterSummary.length > 0 && (
                    <FilterChips
                      items={filterSummary
                        .filter((s): s is string => Boolean(s))
                        .map((s) => ({ key: s, label: '', display: s }))}
                    />
                  )}
                </div>
                {filtersExpanded && (
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                      gap: 18,
                      marginTop: 14,
                      paddingTop: 14,
                      borderTop: '1px solid var(--hair)',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                      <SearchAreaSection
                        preferredPlaces={locations}
                        onPreferredPlacesChange={setLocations}
                        workplacePreference={workplacePreference}
                        onWorkplacePreferenceChange={setWorkplacePreference}
                        context="search"
                      />
                      <JobBoardOptionsSection
                        includeLinkedInJobs={includeLinkedInJobs}
                        onIncludeLinkedInJobsChange={setIncludeLinkedInJobs}
                        context="search"
                      />
                    </div>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                      <div>
                        <span className="qb-flabel">Match strictness</span>
                        <MatchStrictnessControl value={matchStrictness} onChange={setMatchStrictness} />
                      </div>
                      <div>
                        <span className="qb-flabel">
                          Posted within <span className="qb-num" style={{ color: 'var(--ink)' }}>{maxDays} days</span>
                        </span>
                        <Slider
                          value={[maxDays]}
                          onValueChange={(v) => setMaxDays(Array.isArray(v) ? v[0] : v)}
                          min={1}
                          max={60}
                          step={1}
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {searchAreaOverridesSavedDefaults && (
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10, fontSize: 13, color: 'var(--mute)' }}>
                  <span>Overriding your saved defaults</span>
                  <span style={{ display: 'inline-flex', gap: 14 }}>
                    <button type="button" className="qb-plainbtn" style={{ fontSize: 13 }} onClick={applySavedSearchArea}>
                      Reset
                    </button>
                    <button
                      type="button"
                      className="qb-textlink"
                      style={{ fontSize: 13 }}
                      onClick={handleSaveSearchAreaDefaults}
                      disabled={savePreferencesPending}
                    >
                      {savePreferencesPending ? 'Saving...' : 'Save as default'}
                    </button>
                  </span>
                </div>
              )}

              {/* Resume status */}
              <div className="qb-resume-row">
                {onboarding?.resume.exists ? (
                  <>
                    <span style={{ color: 'var(--ink)' }} title={onboarding.resume.filename}>
                      Resume on file: {onboarding.resume.filename}
                    </span>
                    {onboarding.resume.file_size > 0 && (
                      <span className="qb-num">
                        {onboarding.resume.file_size >= 1_048_576
                          ? `${(onboarding.resume.file_size / 1_048_576).toFixed(1)} MB`
                          : `${Math.round(onboarding.resume.file_size / 1024)} KB`}
                      </span>
                    )}
                    {onboarding.resume.parse_warning && (
                      <span style={{ color: 'var(--clay)' }}>{onboarding.resume.parse_warning}</span>
                    )}
                  </>
                ) : (
                  <span>
                    No resume on file yet.{' '}
                    <a href="/settings" className="qb-textlink" style={{ fontSize: 13.5 }}>
                      Add one in Settings
                    </a>
                  </span>
                )}
              </div>

              {/* Target companies */}
              <div>
                <label
                  className="qb-flabel"
                  htmlFor="restock-company"
                  title="Restocks these companies' own career pages (Greenhouse, Lever, Ashby, Workday) directly."
                >
                  Target companies
                  {suggestedCompanies.length > 0 && (
                    <span className="qb-num" style={{ marginLeft: 8, fontSize: 12 }}>{suggestedCompanies.length}</span>
                  )}
                </label>
                <input
                  id="restock-company"
                  type="text"
                  placeholder="Add a company, press Enter"
                  style={{
                    width: '100%',
                    border: '1px solid var(--hair)',
                    background: 'var(--paper)',
                    borderRadius: 4,
                    padding: '8px 12px',
                    fontFamily: 'inherit',
                    fontSize: 13.5,
                    color: 'var(--ink)',
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      const value = (e.target as HTMLInputElement).value.trim();
                      if (value && !suggestedCompanies.some((c) => c.toLowerCase() === value.toLowerCase())) {
                        setSuggestedCompanies((prev) => [...prev, value]);
                        (e.target as HTMLInputElement).value = '';
                      }
                    }
                  }}
                />
                {suggestedCompanies.length > 0 && (
                  <div className="qb-tagrow" style={{ marginTop: 8 }}>
                    {suggestedCompanies.map((company) => (
                      <span key={company} className="qb-tag">
                        {company}
                        <button
                          type="button"
                          onClick={() => setSuggestedCompanies((prev) => prev.filter((c) => c !== company))}
                          aria-label={`Remove ${company}`}
                        >
                          &times;
                        </button>
                      </span>
                    ))}
                  </div>
                )}
                <p className="qb-fhelp">
                  {suggestedCompanies.length > 0
                    ? 'Their career pages get checked directly, on top of the job boards.'
                    : 'Optional: add a company to check its career page directly.'}
                </p>
              </div>

              {/* Mode selector */}
              <div>
                <span className="qb-flabel">What should the restock do?</span>
                <div className="qb-modes" role="radiogroup" aria-label="Restock mode">
                  {(['search_only', 'search_score'] as const).map((m) => {
                    const info = modeLabels[m];
                    const isSelected = selectedMode === m;
                    return (
                      <button
                        key={m}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        onClick={() => setSelectedMode(m)}
                        className={cx('qb-mode', isSelected && 'qb-active')}
                      >
                        <div className="qb-mlabel">{info.label}</div>
                        <div className="qb-mdesc">{info.desc}</div>
                      </button>
                    );
                  })}
                </div>
                <p className="qb-fhelp" style={{ marginTop: 8, lineHeight: 1.5 }}>
                  {modeLabels[selectedMode].detail}
                </p>
                {!llmAvailable && selectedMode === 'search_score' && (
                  <p className="qb-fhelp">
                    This run ranks with keyword and filter matching. Your connected assistant can rank by resume fit.
                  </p>
                )}
              </div>

              {/* Start */}
              <div>
                <button
                  type="button"
                  className="qb-btn-sage qb-lbig"
                  style={{ width: '100%' }}
                  onClick={handleStart}
                  disabled={startSearchPending || suggestPending || missingSearchTerms || missingLocations}
                >
                  {startSearchPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 inline animate-spin" aria-hidden="true" /> Starting...
                    </>
                  ) : suggestPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 inline animate-spin" aria-hidden="true" /> Reading your resume...
                    </>
                  ) : (
                    startLabel
                  )}
                </button>
                {missingSearchTerms && (
                  <p className="qb-fhelp" style={{ textAlign: 'center', marginTop: 8 }}>
                    Add at least one role. Type it in the roles box above.
                  </p>
                )}
                {!missingSearchTerms && missingLocations && (
                  <div style={{ marginTop: 10, textAlign: 'center' }}>
                    <p className="qb-fhelp">Add a place, or pick a remote option below.</p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 14, marginTop: 6 }}>
                      <button type="button" className="qb-textlink" style={{ fontSize: 13.5 }} onClick={() => setWorkplacePreference('remote_friendly')}>
                        Remote plus selected places
                      </button>
                      <button type="button" className="qb-textlink" style={{ fontSize: 13.5 }} onClick={() => setWorkplacePreference('remote_only')}>
                        Remote only
                      </button>
                    </div>
                  </div>
                )}
                {!missingSearchTerms && !missingLocations && parsedRoles.length === 0 && parsedKeywords.length === 0 && canUseResumeFallback && (
                  <p className="qb-fhelp" style={{ textAlign: 'center', marginTop: 8 }}>
                    No roles typed yet. This run reads them from your resume instead.
                  </p>
                )}
                {!missingSearchTerms && !missingLocations && usesRemoteFallback && (
                  <p className="qb-fhelp" style={{ textAlign: 'center', marginTop: 8 }}>
                    No place picked yet. This run keeps remote jobs from everywhere.
                  </p>
                )}
                {suggestedCompanies.length > 0 && !missingSearchTerms && !missingLocations && (
                  <p className="qb-fhelp" style={{ textAlign: 'center', marginTop: 8 }}>
                    Also restocking {suggestedCompanies.length} target {suggestedCompanies.length === 1 ? 'company' : 'companies'} directly.
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
