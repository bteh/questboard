import { describe, expect, it } from 'vitest';
import { SETTINGS_TABS, resolveSettingsTab } from './settings-tabs';

describe('resolveSettingsTab', () => {
  it('keeps every real tab', () => {
    for (const tab of SETTINGS_TABS) {
      expect(resolveSettingsTab(tab)).toBe(tab);
    }
  });

  it('maps the old search tab onto restock', () => {
    expect(resolveSettingsTab('search')).toBe('restock');
  });

  it('drops junk to the default', () => {
    expect(resolveSettingsTab('profile')).toBeUndefined();
    expect(resolveSettingsTab(42)).toBeUndefined();
    expect(resolveSettingsTab(undefined)).toBeUndefined();
  });

  it('drops the removed auto-apply tab to the default', () => {
    expect(resolveSettingsTab('auto-apply')).toBeUndefined();
  });
});
