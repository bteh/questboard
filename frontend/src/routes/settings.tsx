import { useRef } from 'react';
import { createRoute, Link, useNavigate } from '@tanstack/react-router';
import { Route as appRoute } from './app';

import { AssistantTab } from '@/components/settings/AssistantTab';
import { CompaniesTab } from '@/components/settings/CompaniesTab';
import { ResumeTab } from '@/components/settings/ResumeTab';
import { SearchPrefsTab } from '@/components/settings/SearchPrefsTab';
import {
  SETTINGS_TABS,
  resolveSettingsTab,
  type SettingsTab,
} from '@/components/settings/settings-tabs';
import { useOnboardingState } from '@/hooks/use-workspace';
import { cx } from '@questboard/ui';
import '@/components/settings/settings.css';

/* Settings, trade paper: four tabs via ?tab=. The restock tab (id kept for
   old links; ?tab=search also maps onto it) is labeled "Search defaults".
   The tab contents keep their working forms. The footer holds the one link
   back out to the front page. */

export const Route = createRoute({
  getParentRoute: () => appRoute,
  path: '/settings',
  component: SettingsPage,
  validateSearch: (search: Record<string, unknown>) => ({
    tab: resolveSettingsTab(search.tab),
  }),
});

const TAB_LABELS: Record<SettingsTab, string> = {
  resume: 'Resume',
  assistant: 'Assistant',
  restock: 'Search defaults',
  companies: 'Companies',
};

function SettingsPage() {
  const navigate = useNavigate();
  const { tab: tabFromUrl } = Route.useSearch();
  const activeTab: SettingsTab = tabFromUrl ?? 'resume';
  const setActiveTab = (next: SettingsTab) => {
    navigate({ to: '/settings', search: { tab: next === 'resume' ? undefined : next } });
  };
  const { data: onboarding } = useOnboardingState();

  // Roving tabindex for ArrowLeft/ArrowRight keyboard navigation between tabs.
  const tabButtonRefs = useRef<Record<SettingsTab, HTMLButtonElement | null>>({
    resume: null,
    assistant: null,
    restock: null,
    companies: null,
  });
  const handleTabKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const delta = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (currentIndex + delta + SETTINGS_TABS.length) % SETTINGS_TABS.length;
    const nextTab = SETTINGS_TABS[nextIndex];
    setActiveTab(nextTab);
    tabButtonRefs.current[nextTab]?.focus();
  };

  return (
    <div className="qb-settings" style={{ maxWidth: 860, margin: '0 auto', padding: '0 44px 64px' }}>
      <div className="qb-settings-head">
        <h1>Settings</h1>
      </div>

      {/* One focused tab at a time; only the active tab's cards render. */}
      <nav className="qb-settings-tabs" role="tablist" aria-label="Settings sections">
        {SETTINGS_TABS.map((id, index) => {
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
              className={cx(isActive && 'qb-active')}
            >
              {TAB_LABELS[id]}
            </button>
          );
        })}
      </nav>

      <div
        className="qb-settings-panel"
        role="tabpanel"
        id={`settings-panel-${activeTab}`}
        aria-labelledby={`settings-tab-${activeTab}`}
        tabIndex={0}
      >
        {activeTab === 'resume' && <ResumeTab onboarding={onboarding} navigate={navigate} />}

        {activeTab === 'assistant' && <AssistantTab />}

        {activeTab === 'restock' && (
          <SearchPrefsTab onboarding={onboarding} navigate={navigate} />
        )}

        {activeTab === 'companies' && <CompaniesTab />}
      </div>

      <div className="qb-settings-foot">
        <Link to="/welcome" className="qb-textlink" style={{ fontSize: 13.5 }}>
          See the front page
        </Link>
      </div>
    </div>
  );
}
