import { useRef } from 'react';
import { createRoute, useNavigate } from '@tanstack/react-router';
import { Route as appRoute } from './app';
import { LegacyFrame } from '@/components/layout/legacy-frame';
import {
  FileText,
  Rocket,
  Search,
  Sparkles,
} from 'lucide-react';

import { PageHeader } from '@/components/layout/page-header';
import { AiProviderTab } from '@/components/settings/AiProviderTab';
import { TheAiDownloadSection } from '@/components/settings/TheAiDownload';
import { AutoApplyTab } from '@/components/settings/AutoApplyTab';
import { ResumeTab } from '@/components/settings/ResumeTab';
import { SearchPrefsTab } from '@/components/settings/SearchPrefsTab';
import { useOnboardingState } from '@/hooks/use-workspace';
import { cn } from '@/lib/utils';

type SettingsTab = 'resume' | 'search' | 'ai' | 'auto-apply';

const SETTINGS_TABS: SettingsTab[] = ['resume', 'search', 'ai', 'auto-apply'];

function isSettingsTab(value: unknown): value is SettingsTab {
  return typeof value === 'string' && (SETTINGS_TABS as string[]).includes(value);
}

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/settings',
  component: () => (
    <LegacyFrame>
      <SettingsPage />
    </LegacyFrame>
  ),
  validateSearch: (search: Record<string, unknown>) => ({
    tab: isSettingsTab(search.tab) ? search.tab : undefined,
  }),
});

function SettingsPage() {
  const navigate = useNavigate();
  const { tab: tabFromUrl } = Route.useSearch();
  const activeTab: SettingsTab = tabFromUrl ?? 'resume';
  const setActiveTab = (next: SettingsTab) => {
    navigate({ to: '/settings', search: { tab: next === 'resume' ? undefined : next } });
  };
  const { data: onboarding } = useOnboardingState();

  const TAB_DEFS: Array<{ id: SettingsTab; label: string; icon: typeof FileText }> = [
    { id: 'resume', label: 'Resume', icon: FileText },
    { id: 'search', label: 'Search', icon: Search },
    { id: 'ai', label: 'AI provider', icon: Sparkles },
    { id: 'auto-apply', label: 'Auto-apply', icon: Rocket },
  ];

  // Roving tabindex for ArrowLeft/ArrowRight keyboard navigation between tabs.
  const tabButtonRefs = useRef<Record<SettingsTab, HTMLButtonElement | null>>({
    resume: null,
    search: null,
    ai: null,
    'auto-apply': null,
  });
  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const delta = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (currentIndex + delta + TAB_DEFS.length) % TAB_DEFS.length;
    const nextTab = TAB_DEFS[nextIndex].id;
    setActiveTab(nextTab);
    tabButtonRefs.current[nextTab]?.focus();
  };

  return (
    <div>
      <PageHeader title="Settings" />

      {/* Real top-level tabs; only the active tab's cards render below.
          The user only sees one focused page at a time instead of one
          1500-line scroll. */}
      <div className="mb-6 border-b border-border-default">
        <nav className="flex gap-1 overflow-x-auto" role="tablist" aria-label="Settings sections">
          {TAB_DEFS.map(({ id, label, icon: Icon }, index) => {
            const isActive = activeTab === id;
            return (
              <button
                key={id}
                type="button"
                role="tab"
                id={`settings-tab-${id}`}
                aria-controls={`settings-panel-${id}`}
                aria-selected={isActive}
                tabIndex={isActive ? 0 : -1}
                ref={(node) => {
                  tabButtonRefs.current[id] = node;
                }}
                onClick={() => setActiveTab(id)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
                className={cn(
                  'group inline-flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2.5 text-sm font-medium transition-colors -mb-px',
                  isActive
                    ? 'border-brand text-text-primary'
                    : 'border-transparent text-text-tertiary hover:text-text-primary',
                )}
              >
                <Icon className={cn('h-4 w-4 transition-colors', isActive ? 'text-brand' : 'text-text-muted group-hover:text-text-secondary')} />
                {label}
              </button>
            );
          })}
        </nav>
      </div>

      <div
        className="max-w-3xl space-y-6"
        role="tabpanel"
        id={`settings-panel-${activeTab}`}
        aria-labelledby={`settings-tab-${activeTab}`}
        tabIndex={0}
      >
        {/* ── Resume ──────────────────────────────────────────── */}
        {activeTab === 'resume' && <ResumeTab onboarding={onboarding} navigate={navigate} />}

        {/* ── Search tab: three smaller cards instead of one giant card ───── */}
        {activeTab === 'search' && (
          <SearchPrefsTab onboarding={onboarding} navigate={navigate} />
        )}

        {/* ── AI Provider ─────────────────────────────────────── */}
        {activeTab === 'ai' && (
          <>
            <TheAiDownloadSection />
            <AiProviderTab />
          </>
        )}

        {/* ── Auto-Apply ─────────────────────────────────────── */}
        {activeTab === 'auto-apply' && <AutoApplyTab />}
      </div>
    </div>
  );
}
