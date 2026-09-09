import { useCallback, useMemo, useState } from 'react';
import type { useNavigate } from '@tanstack/react-router';
import { ChevronDown, Filter, Loader2, MapPin, Tag } from 'lucide-react';
import { toast } from 'sonner';

import { JobBoardOptionsSection } from '@/components/shared/job-board-options-section';
import { SearchAreaSection } from '@/components/shared/search-area-section';
import { TagListInput } from '@/components/shared/tag-list-input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useSaveWorkspacePreferences } from '@/hooks/use-workspace';
import { buildDefaultWorkspacePreferences, LEVEL_OPTIONS } from '@/lib/profile-preferences';
import { cn } from '@/lib/utils';
import type { OnboardingState, WorkspacePreferences } from '@/types/workspace';

const CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'INR', 'JPY', 'SGD'];
const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: '$', EUR: '€', GBP: '£', CAD: 'C$', AUD: 'A$', INR: '₹', JPY: '¥', SGD: 'S$',
};

interface SearchPrefsTabProps {
  onboarding: OnboardingState | undefined;
  navigate: ReturnType<typeof useNavigate>;
}

export function SearchPrefsTab({ onboarding, navigate }: SearchPrefsTabProps) {
  const savePreferences = useSaveWorkspacePreferences();
  const serverPrefs = useMemo(
    () => onboarding?.preferences ?? buildDefaultWorkspacePreferences(),
    [onboarding?.preferences],
  );
  const [prefsDraft, setPrefsDraft] = useState<WorkspacePreferences | null>(null);
  const prefsForm = prefsDraft ?? serverPrefs;
  const setPrefsForm = useCallback((next: WorkspacePreferences | ((prev: WorkspacePreferences) => WorkspacePreferences)) => {
    setPrefsDraft((prev) => {
      const base = prev ?? serverPrefs;
      return typeof next === 'function' ? next(base) : next;
    });
  }, [serverPrefs]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const handleSavePreferences = () => {
    // Companies are owned by the Companies tab now. Pass the freshest saved
    // list straight through (never the draft) so saving search prefs can't wipe
    // a company the user just added there.
    savePreferences.mutate({ ...prefsForm, companies: serverPrefs.companies }, {
      // Send them to the board's Find work lane, where "Get new jobs" applies
      // these defaults in place. The board is the home for the pull; the
      // standalone restock page is the advanced surface, not a save landing.
      onSuccess: () => toast.success('Preferences saved', {
        action: { label: 'Get new jobs', onClick: () => navigate({ to: '/board', search: { v: 'work' } }) },
      }),
      onError: () => toast.error('Could not save your preferences. Try again in a minute.'),
    });
  };

  return (
    <>
    <p className="text-sm text-text-secondary">
      Set what every restock looks for. Save at the bottom when you are done.
    </p>

    {/* What you're looking for */}
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Tag className="h-4 w-4" />
          What you're looking for
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-1.5">
          <Label>Target roles</Label>
          <p className="text-xs text-text-muted">Titles you want next, not the ones you had. This is what the board matches jobs against. Breaking in? Try Data Analyst, IT Support Specialist, Sales Development Representative, Customer Success Associate.</p>
          <TagListInput
            value={prefsForm.roles}
            onChange={(roles) => setPrefsForm((prev) => ({ ...prev, roles }))}
            placeholder="The title you want next, then press Enter"
          />
        </div>

        <div className="space-y-1.5">
          <Label>Keywords</Label>
          <TagListInput
            value={prefsForm.keywords}
            onChange={(keywords) => setPrefsForm((prev) => ({ ...prev, keywords }))}
            placeholder="e.g. Kubernetes, then press Enter"
          />
        </div>

        <div className="space-y-1.5">
          <Label>Target companies</Label>
          <p className="text-xs text-text-muted">
            Managed in the Companies tab now, so a company you add always drives the pull.
            {prefsForm.companies.length > 0
              ? ` Watching ${prefsForm.companies.length} ${prefsForm.companies.length === 1 ? 'company' : 'companies'}.`
              : ''}
          </p>
          <button
            type="button"
            onClick={() => navigate({ to: '/settings', search: { tab: 'companies' } })}
            className="text-sm font-medium text-brand underline underline-offset-2"
          >
            Manage companies
          </button>
        </div>
      </CardContent>
    </Card>

    {/* Where */}
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <MapPin className="h-4 w-4" />
          Where
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <SearchAreaSection
          preferredPlaces={prefsForm.preferred_places}
          onPreferredPlacesChange={(preferred_places) => setPrefsForm((prev) => ({ ...prev, preferred_places }))}
          workplacePreference={prefsForm.workplace_preference}
          onWorkplacePreferenceChange={(workplace_preference) => setPrefsForm((prev) => ({ ...prev, workplace_preference }))}
          context="settings"
        />

        <JobBoardOptionsSection
          includeLinkedInJobs={prefsForm.include_linkedin_jobs}
          onIncludeLinkedInJobsChange={(include_linkedin_jobs) => setPrefsForm((prev) => ({ ...prev, include_linkedin_jobs }))}
          context="settings"
        />
      </CardContent>
    </Card>

    {/* Filters */}
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Filter className="h-4 w-4" />
          Filters and salary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Minimum salary</Label>
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
              </span>
              <Input
                type="number"
                className="pl-7"
                value={prefsForm.compensation.min_base ?? ''}
                onChange={(event) => setPrefsForm((prev) => ({
                  ...prev,
                  compensation: { ...prev.compensation, min_base: event.target.value === '' ? null : Number(event.target.value) },
                }))}
                placeholder="80,000"
              />
            </div>
            <p className="text-xs text-text-muted">Jobs below this are filtered out.</p>
          </div>
          <div className="space-y-1.5">
            <Label>Target salary</Label>
            <div className="relative">
              <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
              </span>
              <Input
                type="number"
                className="pl-7"
                value={prefsForm.compensation.target_total_comp ?? ''}
                onChange={(event) => setPrefsForm((prev) => ({
                  ...prev,
                  compensation: { ...prev.compensation, target_total_comp: event.target.value === '' ? null : Number(event.target.value) },
                }))}
                placeholder="150,000"
              />
            </div>
            <p className="text-xs text-text-muted">Your assistant uses this when ranking your matches.</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Posted within</Label>
          <Select value={String(prefsForm.max_days_old)} onValueChange={(value) => setPrefsForm((prev) => ({ ...prev, max_days_old: Number(value) }))}>
            <SelectTrigger className="h-9 w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 day</SelectItem>
              <SelectItem value="3">3 days</SelectItem>
              <SelectItem value="7">7 days</SelectItem>
              <SelectItem value="14">14 days</SelectItem>
              <SelectItem value="30">30 days</SelectItem>
              <SelectItem value="60">60 days</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label>Match strictness</Label>
          <div
            role="radiogroup"
            aria-label="Match strictness"
            className="inline-grid grid-cols-3 gap-1 rounded-lg border border-border-default bg-bg-card p-1"
          >
            {(['loose', 'balanced', 'strict'] as const).map((value) => {
              const selected = prefsForm.match_strictness === value;
              const hint = value === 'loose'
                ? 'Wider net: more results, looser matches'
                : value === 'balanced'
                  ? 'The default; fits most people'
                  : 'Tight matches only, fewer results';
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  title={hint}
                  onClick={() => setPrefsForm((prev) => ({ ...prev, match_strictness: value }))}
                  className={cn(
                    'rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand',
                    selected
                      ? 'bg-brand-light/60 text-brand'
                      : 'text-text-tertiary hover:text-text-secondary',
                  )}
                >
                  {value}
                </button>
              );
            })}
          </div>
        </div>

        {/* ── Advanced (collapsed by default) ──────────────── */}
        <div className="border-t border-border-default pt-4">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center gap-1.5 text-sm font-medium text-text-secondary hover:text-text-primary"
          >
            <ChevronDown className={cn('h-4 w-4 transition-transform', showAdvanced && 'rotate-180')} />
            Advanced options
          </button>

          {showAdvanced && (
            <div className="mt-4 space-y-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label>Current title</Label>
                  <Input
                    value={prefsForm.current_title}
                    onChange={(event) => setPrefsForm((prev) => ({ ...prev, current_title: event.target.value }))}
                    placeholder="e.g. Senior Engineer"
                  />
                  <p className="text-xs text-text-muted">Helps your assistant judge level fit.</p>
                </div>
                <div className="space-y-1.5">
                  <Label>Current level</Label>
                  <Select
                    value={prefsForm.current_level}
                    onValueChange={(value) => setPrefsForm((prev) => ({ ...prev, current_level: value ?? prev.current_level }))}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {LEVEL_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-3">
                <div className="space-y-1.5">
                  <Label>Currency</Label>
                  <Select
                    value={prefsForm.compensation.currency}
                    onValueChange={(currency) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: { ...prev.compensation, currency: currency ?? prev.compensation.currency },
                    }))}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CURRENCIES.map((currency) => (
                        <SelectItem key={currency} value={currency}>{currency}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Pay period</Label>
                  <Select
                    value={prefsForm.compensation.pay_period}
                    onValueChange={(pay_period) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: {
                        ...prev.compensation,
                        pay_period: pay_period ?? prev.compensation.pay_period,
                      },
                    }))}
                  >
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="hourly">Hourly</SelectItem>
                      <SelectItem value="monthly">Monthly</SelectItem>
                      <SelectItem value="annual">Annual</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label>Current compensation</Label>
                  <div className="relative">
                    <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                      {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                    </span>
                    <Input
                      type="number"
                      className="pl-7"
                      value={prefsForm.compensation.current_comp ?? ''}
                      onChange={(event) => setPrefsForm((prev) => ({
                        ...prev,
                        compensation: { ...prev.compensation, current_comp: event.target.value === '' ? null : Number(event.target.value) },
                      }))}
                    />
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <Label>Absolute minimum (hard floor)</Label>
                <div className="relative w-48">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm text-text-muted">
                    {CURRENCY_SYMBOLS[prefsForm.compensation.currency] ?? '$'}
                  </span>
                  <Input
                    type="number"
                    className="pl-7"
                    value={prefsForm.compensation.min_acceptable_tc ?? ''}
                    onChange={(event) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: { ...prev.compensation, min_acceptable_tc: event.target.value === '' ? null : Number(event.target.value) },
                    }))}
                  />
                </div>
                <p className="text-xs text-text-muted">If set, jobs below this are completely hidden. Stricter than minimum salary.</p>
              </div>

              <div className="space-y-3">
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="include-equity"
                    checked={prefsForm.compensation.include_equity}
                    onCheckedChange={(checked) => setPrefsForm((prev) => ({
                      ...prev,
                      compensation: { ...prev.compensation, include_equity: !!checked },
                    }))}
                  />
                  <div>
                    <Label htmlFor="include-equity">Count equity toward total compensation</Label>
                    <p className="mt-0.5 text-xs text-text-muted">Useful for startup roles with stock options.</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Checkbox
                    id="exclude-staffing"
                    checked={prefsForm.exclude_staffing_agencies}
                    onCheckedChange={(checked) => setPrefsForm((prev) => ({
                      ...prev,
                      exclude_staffing_agencies: !!checked,
                    }))}
                  />
                  <div>
                    <Label htmlFor="exclude-staffing">Exclude staffing agencies</Label>
                    <p className="mt-0.5 text-xs text-text-muted">Filter out listings from known recruitment firms.</p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        <Button onClick={handleSavePreferences} disabled={savePreferences.isPending}>
          {savePreferences.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
          Save preferences
        </Button>
      </CardContent>
    </Card>
    </>
  );
}
