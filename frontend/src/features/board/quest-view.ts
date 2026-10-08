/* Side Quests list | wall choice. ?view= wins; without it the viewer's last
   pick comes back from localStorage, and the list is the default. */

export type QuestView = 'list' | 'wall';

export const QUEST_VIEW_KEY = 'questboard:quest-view';

export function normalizeQuestView(raw: unknown): QuestView | undefined {
  return raw === 'list' || raw === 'wall' ? raw : undefined;
}

export function readQuestView(): QuestView | undefined {
  try {
    return normalizeQuestView(window.localStorage.getItem(QUEST_VIEW_KEY));
  } catch {
    return undefined;
  }
}

export function saveQuestView(view: QuestView): void {
  try {
    window.localStorage.setItem(QUEST_VIEW_KEY, view);
  } catch {
    /* storage refused: the URL still carries the choice */
  }
}

export function resolveQuestView(fromUrl: QuestView | undefined): QuestView {
  return fromUrl ?? readQuestView() ?? 'list';
}
