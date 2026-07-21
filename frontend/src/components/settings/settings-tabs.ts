/* Settings tab vocabulary, pinned by settings-tabs.test.ts. The Search tab
   became Restock when /search became /restock; old ?tab=search links keep
   working by mapping onto restock. */

export type SettingsTab = 'resume' | 'assistant' | 'restock' | 'auto-apply';

export const SETTINGS_TABS: SettingsTab[] = ['resume', 'assistant', 'restock', 'auto-apply'];

export function resolveSettingsTab(value: unknown): SettingsTab | undefined {
  if (value === 'search') return 'restock';
  if (typeof value === 'string' && (SETTINGS_TABS as string[]).includes(value)) {
    return value as SettingsTab;
  }
  return undefined;
}
