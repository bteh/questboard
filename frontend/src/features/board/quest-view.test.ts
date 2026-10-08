// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { QUEST_VIEW_KEY, resolveQuestView, saveQuestView } from './quest-view';

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('the Side Quests view choice', () => {
  it('defaults to the list', () => {
    expect(resolveQuestView(undefined)).toBe('list');
  });

  it('remembers the last pick for this viewer', () => {
    saveQuestView('wall');
    expect(window.localStorage.getItem(QUEST_VIEW_KEY)).toBe('wall');
    expect(resolveQuestView(undefined)).toBe('wall');
  });

  it('lets the URL win over the remembered pick', () => {
    saveQuestView('wall');
    expect(resolveQuestView('list')).toBe('list');
  });

  it('falls back to the list when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => saveQuestView('wall')).not.toThrow();
    expect(resolveQuestView(undefined)).toBe('list');
  });
});
