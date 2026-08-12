/* Settings tab vocabulary, pinned by settings-tabs.test.ts. The Search tab
   became Restock when /search became /restock; old ?tab=search links keep
   working by mapping onto restock. The Auto-apply tab is gone (PRODUCT.md
   bans mass auto-apply); old ?tab=auto-apply links drop to the default. */

export type SettingsTab = 'resume' | 'assistant' | 'restock' | 'companies' | 'privacy';

export const SETTINGS_TABS: SettingsTab[] = ['resume', 'assistant', 'restock', 'companies', 'privacy'];

export function resolveSettingsTab(value: unknown): SettingsTab | undefined {
  if (value === 'search') return 'restock';
  if (typeof value === 'string' && (SETTINGS_TABS as string[]).includes(value)) {
    return value as SettingsTab;
  }
  return undefined;
}
