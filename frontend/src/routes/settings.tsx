import { useState, useRef, useEffect, useMemo } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as rootRoute } from './__root';
import { Upload, CheckCircle2, Loader2, ChevronDown, Globe, ArrowRight, Search, DollarSign, X, FileText, Shield, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { PageHeader } from '@/components/layout/page-header';
import { useLLMStatus, useUpdateLLM, useTestConnection, useLLMPresets, useProviderModels, useProfiles, useProfilePreferences, useUpdateProfilePreferences } from '@/hooks/use-settings';
import { useResumeStatus, useUploadResume } from '@/hooks/use-resume';
import { useProfile } from '@/contexts/profile-context';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { getVisibleProviderGroups } from '@/lib/llm-providers';
import type { ProviderGroup } from '@/lib/llm-providers';
import type { LLMConfig, ProfilePreferences } from '@/types/settings';

export const Route = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  component: SettingsPage,
});

/** Section definitions for grouping providers visually. */
const SECTIONS: { key: string; label: string; subtitle: string; badges: ProviderGroup['badge'][] }[] = [
  { key: 'free', label: 'Free', subtitle: 'No credit card needed', badges: ['free'] },
  { key: 'paid', label: 'Paid API', subtitle: 'Pay per token', badges: ['api-key'] },
  { key: 'local', label: 'Local', subtitle: 'Run on your machine', badges: ['local'] },
  { key: 'internal', label: 'Internal', subtitle: 'Dev mode only', badges: ['internal'] },
];

function GroupCard({ group, isSelected, onClick }: { group: ProviderGroup; isSelected: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-lg border px-3.5 py-3 transition-all cursor-pointer group',
        isSelected
          ? 'border-brand bg-brand-light/50 shadow-sm ring-1 ring-brand/20'
          : 'border-border-default bg-bg-card hover:border-brand/40 hover:bg-bg-subtle',
      )}
    >
      <div className="flex items-center gap-3">
        {/* Radio circle */}
        <div className={cn(
          'h-4 w-4 shrink-0 rounded-full border-2 transition-all flex items-center justify-center',
          isSelected
            ? 'border-brand bg-brand'
            : 'border-text-muted group-hover:border-brand/60',
        )}>
          {isSelected && <div className="h-1.5 w-1.5 rounded-full bg-white" />}
        </div>

        <div className="min-w-0 flex-1">
          <span className="text-sm font-medium text-text-primary">{group.label}</span>
          <span className="text-xs text-text-muted ml-2 hidden sm:inline">{group.badgeLabel}</span>
        </div>
      </div>
    </button>
  );
}

function SettingsPage() {
  const { data: llm, isLoading: llmLoading } = useLLMStatus();
  const { data: presets } = useLLMPresets();
  const { data: resume } = useResumeStatus();
  const { data: profiles } = useProfiles();
  const { profile, setProfile } = useProfile();

  const devMode = typeof window !== 'undefined' && (
    localStorage.getItem('launchboard-dev-mode') === 'true'
    || ['localhost', '127.0.0.1', '0.0.0.0'].includes(window.location.hostname)
  );
  const providerGroups = getVisibleProviderGroups(devMode);

  const groupedSections = useMemo(() => {
    return SECTIONS
      .map((section) => ({
        section,
        groups: providerGroups.filter((g) => section.badges.includes(g.badge)),
      }))
      .filter(({ groups }) => groups.length > 0);
  }, [providerGroups]);

  const updateLLM = useUpdateLLM();
  const testConn = useTestConnection();
  const uploadResume = useUploadResume();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [config, setConfig] = useState<LLMConfig>({ provider: '', base_url: '', api_key: '', model: '' });
  const [selectedGroupId, setSelectedGroupId] = useState<string>('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // Sync local form state when server data first loads
  useEffect(() => {
    if (llm && presets) {
      const preset = presets.find((p) => p.name === llm.provider);
      const group = providerGroups.find((g) => g.presetNames.includes(llm.provider));
      // eslint-disable-next-line react-hooks/set-state-in-effect -- form initialization from async data
      setConfig({
        provider: llm.provider,
        base_url: preset?.base_url || '',
        api_key: '',
        model: llm.model,
      });
      if (group) setSelectedGroupId(group.id);
    }
  }, [llm, presets, providerGroups]);

  const handleGroupSelect = (group: ProviderGroup) => {
    setSelectedGroupId(group.id);
    // Pick the first matching backend preset for this group
    const presetName = group.presetNames[0];
    const preset = presets?.find((p) => p.name === presetName);
    if (preset) {
      setConfig((prev) => ({
        ...prev,
        provider: preset.name,
        base_url: preset.base_url,
        model: preset.model,
        api_key: preset.needs_api_key ? prev.api_key : '',
      }));
    }
  };

  // For groups with multiple backend presets (e.g., 2 Claude proxies), let user pick
  const selectedGroup = providerGroups.find((g) => g.id === selectedGroupId);
  const selectedPreset = presets?.find((p) => p.name === config.provider);
  const groupPresets = selectedGroup
    ? presets?.filter((p) => selectedGroup.presetNames.includes(p.name)) || []
    : [];

  // Fetch live models from the provider's /models endpoint
  const needsKey = selectedPreset?.needs_api_key ?? false;
  const canFetchModels = !!config.base_url && (!needsKey || !!config.api_key);
  const { data: liveModels, isFetching: modelsFetching } = useProviderModels(
    config.base_url,
    config.api_key,
    canFetchModels,
  );

  const handleSaveAndTest = () => {
    updateLLM.mutate(config, {
      onSuccess: () => {
        testConn.mutate(undefined, {
          onSuccess: (res) => {
            if (res.success) {
              toast.success('Connected successfully', {
                description: `${res.provider} · ${res.model}`,
              });
            } else {
              toast.error('Connection failed', {
                description: res.message,
              });
            }
          },
          onError: () => toast.error('Connection test failed'),
        });
      },
      onError: (err) => toast.error('Failed to save config', {
        description: err instanceof Error ? err.message : 'Unknown error',
      }),
    });
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    uploadResume.mutate(file, {
      onSuccess: () => toast.success('Resume uploaded'),
      onError: () => toast.error('Upload failed'),
    });
  };

  const { data: prefsData } = useProfilePreferences();
  const updatePrefs = useUpdateProfilePreferences();
  const [prefsForm, setPrefsForm] = useState<ProfilePreferences>({
    current_title: '',
    current_level: ['mid'],
    current_tc: 100_000,
    min_base: 80_000,
    target_total_comp: 150_000,
    auto_apply_enabled: false,
    auto_apply_dry_run: true,
    scoring_technical: 0.25,
    scoring_leadership: 0.15,
    scoring_career_progression: 0.15,
    scoring_platform: 0.13,
    scoring_comp: 0.12,
    scoring_trajectory: 0.10,
    scoring_culture: 0.10,
    threshold_strong_apply: 70,
    threshold_apply: 55,
    threshold_maybe: 40,
    exclude_staffing_agencies: true,
    include_equity: true,
    min_acceptable_tc: null,
  });
  const [prefsInitialized, setPrefsInitialized] = useState(false);

  useEffect(() => {
    if (prefsData?.preferences && !prefsInitialized) {
      // Merge with defaults so missing fields don't become undefined
      setPrefsForm((prev) => ({ ...prev, ...prefsData.preferences }));
      setPrefsInitialized(true);
    }
  }, [prefsData, prefsInitialized]);

  const handleProfileSwitch = (name: string) => {
    setProfile(name);
    setPrefsInitialized(false);
  };

  const handleSavePrefs = () => {
    updatePrefs.mutate(prefsForm, {
      onSuccess: () => toast.success('Preferences saved'),
      onError: () => toast.error('Failed to save preferences'),
    });
  };

  const navigate = useNavigate();
  const isSaving = updateLLM.isPending || testConn.isPending;

  const llmDone = llm?.available === true;
  const prefsDone = prefsData?.preferences?.current_title !== '';
  const resumeDone = resume?.exists === true;
  const allDone = llmDone && resumeDone;

  return (
    <div>
      <PageHeader title="Settings" description="Configure your job search agent" />

      <div className="max-w-2xl space-y-8">
        {/* Profile switcher */}
        {profiles && profiles.length > 1 && (
          <div className="flex items-center gap-3">
            <Users className="h-4 w-4 text-text-muted shrink-0" />
            <Label className="text-sm font-medium text-text-secondary shrink-0">Profile</Label>
            <div className="flex flex-wrap gap-2">
              {profiles.map((p) => (
                <button
                  key={p.name}
                  type="button"
                  onClick={() => handleProfileSwitch(p.name)}
                  className={cn(
                    'rounded-full px-3 py-1 text-sm font-medium transition-all cursor-pointer',
                    profile === p.name
                      ? 'bg-brand text-white shadow-sm'
                      : 'bg-bg-subtle text-text-secondary hover:bg-bg-muted',
                  )}
                >
                  {p.display_name}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Setup progress — compact step indicators */}
        <div className="flex items-center gap-3">
          <StepDot step={1} done={llmDone} active={!llmDone} />
          <div className={cn('h-px flex-1', llmDone ? 'bg-success' : 'bg-border-default')} />
          <StepDot step={2} done={!!prefsDone} active={llmDone && !prefsDone} />
          <div className={cn('h-px flex-1', prefsDone ? 'bg-success' : 'bg-border-default')} />
          <StepDot step={3} done={resumeDone} active={!!prefsDone && !resumeDone} />
          <div className={cn('h-px flex-1', allDone ? 'bg-success' : 'bg-border-default')} />
          <StepDot step={4} done={allDone} active={llmDone && resumeDone} label="Search" />
        </div>

        {/* ── Step 1: LLM Provider ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold',
                  llmDone ? 'bg-success/15 text-success' : 'bg-brand-light text-brand',
                )}>
                  {llmDone ? <CheckCircle2 className="h-5 w-5" /> : '1'}
                </div>
                <div>
                  <CardTitle className="text-base">Connect an AI Provider</CardTitle>
                  <p className="text-sm text-text-tertiary">Powers job scoring, cover letters, and company research.</p>
                </div>
              </div>
              {llmDone && (
                <span className="text-xs text-success font-medium bg-success/10 rounded-full px-2.5 py-1">Connected</span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-5">
              {/* Provider cards grouped by section */}
              {llmLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-14 w-full" />)}
                </div>
              ) : (
                <div className="space-y-5">
                  {groupedSections.map(({ section, groups }) => (
                    <div key={section.key}>
                      <div className="flex items-center gap-2 mb-2">
                        <h4 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider">{section.label}</h4>
                        <span className="text-[10px] text-text-muted font-normal normal-case">{section.subtitle}</span>
                        <div className="flex-1 h-px bg-border-default" />
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {groups.map((g) => (
                          <GroupCard
                            key={g.id}
                            group={g}
                            isSelected={selectedGroupId === g.id}
                            onClick={() => handleGroupSelect(g)}
                          />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Selected provider description */}
              {selectedGroup && (
                <div className="rounded-lg bg-bg-subtle border border-border-default px-3.5 py-3">
                  <p className="text-xs text-text-secondary leading-relaxed">{selectedGroup.description}</p>
                </div>
              )}

              {/* Configure section (only when a group is selected) */}
              {selectedGroup && (
                <div className="space-y-5 border-t border-border-default pt-5">
                  {/* Proxy variant picker (only when group has multiple backend presets) */}
                  {groupPresets.length > 1 && (
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">Proxy</Label>
                      <div className="flex gap-2">
                        {groupPresets.map((p) => (
                          <button
                            key={p.name}
                            type="button"
                            onClick={() => setConfig((prev) => ({
                              ...prev,
                              provider: p.name,
                              base_url: p.base_url,
                              model: prev.model || p.model,
                            }))}
                            className={cn(
                              'rounded-lg border px-3 py-2 text-xs transition-all flex-1 cursor-pointer',
                              config.provider === p.name
                                ? 'border-brand bg-brand-light text-brand font-medium shadow-sm'
                                : 'border-border-default text-text-secondary hover:border-brand/40 hover:bg-bg-subtle hover:shadow-sm',
                            )}
                          >
                            <div className="font-medium">{p.label.replace(/^.*\(/, '').replace(/\)$/, '')}</div>
                            <div className="text-text-muted mt-0.5 font-mono">{p.base_url}</div>
                          </button>
                        ))}
                      </div>
                      <p className="text-xs text-text-muted">
                        Choose which proxy you have running locally.
                      </p>
                    </div>
                  )}

                  {/* API Key (only for providers that need it) — before model so live fetch works */}
                  {selectedPreset?.needs_api_key && (
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">API Key</Label>
                      <Input
                        type="password"
                        value={config.api_key}
                        onChange={(e) => setConfig((p) => ({ ...p, api_key: e.target.value }))}
                        placeholder={selectedGroup?.apiKeyPlaceholder || 'Your API key'}
                        className="h-10"
                      />
                      <p className="text-xs text-text-muted">
                        Stored locally — never sent anywhere except to your chosen provider.
                      </p>
                    </div>
                  )}

                  {/* Model Selection */}
                  <div className="space-y-3">
                    <Label className="text-sm font-medium">Model</Label>

                    {/* Suggested models (hardcoded, always visible) */}
                    {selectedGroup.models.length > 0 && (
                      <div>
                        <p className="text-[11px] text-text-muted mb-1.5">Suggested</p>
                        <div className="flex flex-wrap gap-2">
                          {selectedGroup.models.map((m) => (
                            <button
                              key={m.id}
                              type="button"
                              onClick={() => setConfig((p) => ({ ...p, model: m.id }))}
                              className={cn(
                                'inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-all cursor-pointer',
                                config.model === m.id
                                  ? 'border-brand bg-brand-light text-brand font-medium shadow-sm'
                                  : 'border-border-default text-text-secondary hover:border-brand/40 hover:bg-bg-subtle hover:shadow-sm',
                              )}
                            >
                              {m.name}
                              {m.tag && (
                                <span className={cn(
                                  'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                                  config.model === m.id
                                    ? 'bg-brand/20 text-brand'
                                    : 'bg-bg-muted text-text-muted',
                                )}>
                                  {m.tag}
                                </span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Live models from provider API */}
                    {modelsFetching && (
                      <div className="flex items-center gap-2 text-xs text-text-muted">
                        <Loader2 className="h-3 w-3 animate-spin" />
                        Loading models from provider...
                      </div>
                    )}
                    {liveModels && liveModels.length > 0 && (
                      <div>
                        <p className="text-[11px] text-text-muted mb-1.5">
                          All models from provider
                          <span className="text-success ml-1">Live</span>
                        </p>
                        <div className="max-h-40 overflow-y-auto rounded-lg border border-border-default bg-bg-card">
                          {liveModels.map((m) => (
                            <button
                              key={m.id}
                              type="button"
                              onClick={() => setConfig((p) => ({ ...p, model: m.id }))}
                              className={cn(
                                'w-full text-left px-3 py-1.5 text-xs font-mono border-b border-border-default last:border-b-0 transition-colors cursor-pointer',
                                config.model === m.id
                                  ? 'bg-brand-light text-brand font-medium'
                                  : 'text-text-secondary hover:bg-bg-subtle',
                              )}
                            >
                              {m.id}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    <div>
                      <Input
                        value={config.model}
                        onChange={(e) => setConfig((p) => ({ ...p, model: e.target.value }))}
                        placeholder={selectedPreset?.model || 'Or type a model ID'}
                        className="h-9 text-xs font-mono text-text-muted"
                      />
                      <p className="text-xs text-text-muted mt-1">
                        Pick above or type any model ID your provider supports.
                      </p>
                    </div>
                  </div>

                  {/* Advanced: Base URL (collapsed by default) */}
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowAdvanced(!showAdvanced)}
                      className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors cursor-pointer"
                    >
                      <ChevronDown className={cn('h-3 w-3 transition-transform', showAdvanced && 'rotate-180')} />
                      Advanced settings
                    </button>
                    {showAdvanced && (
                      <div className="mt-3 space-y-2">
                        <Label className="text-sm font-medium flex items-center gap-1.5">
                          <Globe className="h-3.5 w-3.5 text-text-muted" />
                          Base URL
                        </Label>
                        <Input
                          value={config.base_url}
                          onChange={(e) => setConfig((p) => ({ ...p, base_url: e.target.value }))}
                          placeholder={selectedPreset?.base_url || 'http://localhost:11434/v1'}
                          className="h-10 font-mono text-xs"
                        />
                        <p className="text-xs text-text-muted">
                          Pre-filled from provider. Only change if you have a custom endpoint.
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Save & Test */}
                  <div className="pt-2">
                    <Button onClick={handleSaveAndTest} disabled={isSaving} className="w-full sm:w-auto">
                      {isSaving ? (
                        <>
                          <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                          {updateLLM.isPending ? 'Saving...' : 'Testing connection...'}
                        </>
                      ) : (
                        'Save & Test Connection'
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* ── Step 2: Career & Compensation ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold',
                  prefsDone ? 'bg-success/15 text-success' : 'bg-brand-light text-brand',
                )}>
                  {prefsDone ? <CheckCircle2 className="h-5 w-5" /> : '2'}
                </div>
                <div>
                  <CardTitle className="text-base">Career & Compensation</CardTitle>
                  <p className="text-sm text-text-tertiary">Helps us find jobs that match your experience level and salary expectations.</p>
                </div>
              </div>
              {prefsDone && (
                <span className="text-xs text-success font-medium bg-success/10 rounded-full px-2.5 py-1">Configured</span>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Current Title</Label>
                <Input
                  value={prefsForm.current_title}
                  onChange={(e) => setPrefsForm((p) => ({ ...p, current_title: e.target.value }))}
                  placeholder="e.g. Marketing Manager, Nurse, Software Engineer"
                  className="h-9"
                />
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-text-secondary">Current Total Pay</Label>
                  <Input
                    type="number"
                    value={prefsForm.current_tc}
                    onChange={(e) => setPrefsForm((p) => ({ ...p, current_tc: Number(e.target.value) }))}
                    className="h-9 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-text-secondary">Minimum Salary</Label>
                  <Input
                    type="number"
                    value={prefsForm.min_base}
                    onChange={(e) => setPrefsForm((p) => ({ ...p, min_base: Number(e.target.value) }))}
                    className="h-9 text-sm"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-xs font-medium text-text-secondary">Target Total Pay</Label>
                  <Input
                    type="number"
                    value={prefsForm.target_total_comp}
                    onChange={(e) => setPrefsForm((p) => ({ ...p, target_total_comp: Number(e.target.value) }))}
                    className="h-9 text-sm"
                  />
                </div>
              </div>

              {/* ── Auto-Apply ── */}
              <div className="border-t border-border-default pt-4 space-y-3">
                <div className="flex items-center gap-2">
                  <Shield className="h-4 w-4 text-text-muted" />
                  <Label className="text-sm font-medium">Auto-Apply</Label>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-text-secondary">Enable auto-apply</p>
                    <p className="text-xs text-text-muted">Automatically submit applications for strong matches via Greenhouse/Lever.</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setPrefsForm((p) => ({ ...p, auto_apply_enabled: !p.auto_apply_enabled }))}
                    className={cn(
                      'relative inline-flex h-6 w-11 items-center rounded-full transition-colors cursor-pointer',
                      prefsForm.auto_apply_enabled ? 'bg-brand' : 'bg-bg-muted',
                    )}
                  >
                    <span
                      className={cn(
                        'inline-block h-4 w-4 rounded-full bg-white transition-transform shadow-sm',
                        prefsForm.auto_apply_enabled ? 'translate-x-6' : 'translate-x-1',
                      )}
                    />
                  </button>
                </div>

                {prefsForm.auto_apply_enabled && (
                  <div className="flex items-center justify-between rounded-lg border border-border-default bg-bg-subtle px-3.5 py-3">
                    <div>
                      <p className="text-sm text-text-secondary">Dry run mode</p>
                      <p className="text-xs text-text-muted">When enabled, logs what would happen without actually submitting applications.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setPrefsForm((p) => ({ ...p, auto_apply_dry_run: !p.auto_apply_dry_run }))}
                      className={cn(
                        'relative inline-flex h-6 w-11 items-center rounded-full transition-colors cursor-pointer',
                        prefsForm.auto_apply_dry_run ? 'bg-brand' : 'bg-bg-muted',
                      )}
                    >
                      <span
                        className={cn(
                          'inline-block h-4 w-4 rounded-full bg-white transition-transform shadow-sm',
                          prefsForm.auto_apply_dry_run ? 'translate-x-6' : 'translate-x-1',
                        )}
                      />
                    </button>
                  </div>
                )}
              </div>

              <Button onClick={handleSavePrefs} disabled={updatePrefs.isPending} className="w-full sm:w-auto">
                {updatePrefs.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <DollarSign className="h-4 w-4 mr-2" />
                    Save Preferences
                  </>
                )}
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* ── Step 3: Resume ── */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold',
                  resumeDone ? 'bg-success/15 text-success' : 'bg-brand-light text-brand',
                )}>
                  {resumeDone ? <CheckCircle2 className="h-5 w-5" /> : '3'}
                </div>
                <div>
                  <CardTitle className="text-base">Upload Your Resume</CardTitle>
                  <p className="text-sm text-text-tertiary">Used to score job matches and generate tailored cover letters.</p>
                </div>
              </div>
              {resumeDone && (
                <CheckCircle2 className="h-5 w-5 text-success shrink-0" />
              )}
            </div>
          </CardHeader>
          <CardContent>
            <input type="file" ref={fileInputRef} accept=".pdf" className="hidden" onChange={handleFileUpload} />
            {resumeDone && resume ? (
              <div className="flex items-center gap-3 rounded-lg border border-success/20 bg-success/5 px-4 py-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-500/10 shrink-0">
                  <FileText className="h-5 w-5 text-red-500" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-text-primary truncate" title={resume.filename}>{resume.filename}</p>
                  <p className="text-xs text-text-muted">
                    {resume.file_size > 0
                      ? resume.file_size >= 1_048_576
                        ? `${(resume.file_size / 1_048_576).toFixed(1)} MB`
                        : `${Math.round(resume.file_size / 1024)} KB`
                      : 'PDF'}
                  </p>
                </div>
                <button
                  type="button"
                  className="text-xs font-medium text-brand hover:text-brand-dark transition-colors shrink-0"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadResume.isPending}
                >
                  {uploadResume.isPending ? 'Uploading...' : 'Replace'}
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="w-full rounded-lg border-2 border-dashed border-border-default p-8 text-center transition-colors hover:border-brand hover:bg-brand-light/30 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadResume.isPending}
              >
                {uploadResume.isPending ? (
                  <Loader2 className="h-8 w-8 mx-auto text-brand animate-spin mb-3" />
                ) : (
                  <Upload className="h-8 w-8 mx-auto text-text-muted mb-3" />
                )}
                <p className="text-sm font-medium text-text-primary">
                  {uploadResume.isPending ? 'Uploading...' : 'Click to upload your resume (PDF)'}
                </p>
                <p className="text-xs text-text-muted mt-1">PDF format, up to 10MB</p>
              </button>
            )}
          </CardContent>
        </Card>

        {/* ── Step 4: Ready to go CTA ── */}
        <Card className={cn(
          'transition-all',
          allDone
            ? 'border-success/30 bg-success/5'
            : 'border-border-default',
        )}>
          <CardContent className="py-6">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold',
                  allDone ? 'bg-success/15 text-success' : 'bg-bg-muted text-text-muted',
                )}>
                  {allDone ? <CheckCircle2 className="h-5 w-5" /> : '4'}
                </div>
                <div>
                  <p className={cn('text-sm font-medium', allDone ? 'text-success' : 'text-text-secondary')}>
                    {allDone ? 'You\'re all set!' : 'Run your first search'}
                  </p>
                  <p className={cn('text-xs', allDone ? 'text-success/80' : 'text-text-muted')}>
                    {allDone
                      ? 'Your agent is ready to find and score jobs.'
                      : !llmDone
                        ? 'Connect an AI provider first.'
                        : 'Upload your resume to enable personalized scoring.'
                    }
                  </p>
                </div>
              </div>
              <Button
                onClick={() => navigate({ to: '/search' })}
                disabled={!allDone}
                className="shrink-0"
              >
                <Search className="h-4 w-4 mr-2" />
                Run Search
                <ArrowRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function StepDot({ step, done, active, label }: { step: number; done: boolean; active: boolean; label?: string }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={cn(
        'flex h-7 w-7 items-center justify-center rounded-full text-xs font-bold transition-all',
        done ? 'bg-success text-white' : active ? 'bg-brand text-white' : 'bg-bg-muted text-text-muted',
      )}>
        {done ? <CheckCircle2 className="h-4 w-4" /> : step}
      </div>
      {label && <span className="text-[10px] text-text-muted">{label}</span>}
    </div>
  );
}
