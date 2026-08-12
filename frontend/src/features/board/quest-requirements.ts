/* A shared, honest requirements model for every Side Quest.

   "Application effort" means the setup/application work needed to pursue a
   quest. It deliberately does not claim how hard the quest is to win, how
   long approval takes, or how long the quest itself lasts.

   A source can provide application_effort, application_effort_note, and
   criteria in quest_json. Older rows still get a kind-level estimate and the
   existing kind requirement, both clearly labeled as typical rather than as
   posting-specific facts. */

import type { ApplicationResponse } from '@/types/application';

export type QuestEffortLevel = 'quick' | 'some_prep' | 'involved';
export type QuestRequirementBasis = 'listed' | 'typical';

export interface QuestEffort {
  level: QuestEffortLevel;
  label: string;
  time: string;
  note: string;
  basis: QuestRequirementBasis;
}

export interface QuestCriteria {
  items: string[];
  basis: QuestRequirementBasis;
}

export interface QuestRequirements {
  effort: QuestEffort;
  criteria: QuestCriteria;
}

const EFFORT_LABELS: Record<QuestEffortLevel, { label: string; time: string }> = {
  quick: { label: 'Quick', time: 'usually under 15 min' },
  some_prep: { label: 'Some prep', time: 'usually 15–45 min' },
  involved: { label: 'More involved', time: 'usually 45+ min or multiple steps' },
};

interface TypicalEffort {
  level: QuestEffortLevel;
  note: string;
}

/* Every non-work kind is named here, including kinds whose live supply is
   still small. These are setup patterns, not per-posting eligibility claims. */
const TYPICAL_EFFORT: Record<string, TypicalEffort> = {
  think: { level: 'quick', note: 'Complete a profile or eligibility screener.' },
  lookafter: {
    level: 'involved',
    note: 'Build a profile and expect verification, a background check, or a meet-and-greet.',
  },
  house: {
    level: 'some_prep',
    note: 'Open the account and set up the deposit, spend, or funding steps tied to the bonus.',
  },
  scholarship: {
    level: 'involved',
    note: 'Check eligibility and gather any transcripts, service records, essays, or references.',
  },
  skill: { level: 'some_prep', note: 'Prepare relevant samples and a short proposal or profile.' },
  perform: {
    level: 'some_prep',
    note: 'Prepare current photos, availability, and any requested self-tape or audition material.',
  },
  audience: { level: 'quick', note: 'Request tickets and confirm your availability and party size.' },
  body: {
    level: 'some_prep',
    note: 'Complete an eligibility screen before any consent or appointment steps.',
  },
  odd: { level: 'quick', note: 'Send a short response and confirm the task, place, and timing.' },
  deliver: {
    level: 'involved',
    note: 'Expect identity, license, insurance, vehicle, and background-check setup.',
  },
  flip: {
    level: 'some_prep',
    note: 'Create the account or listing, document the item, and check fees and comparable prices.',
  },
  speak: {
    level: 'involved',
    note: 'Prepare an abstract, speaker profile, and any requested talk outline or samples.',
  },
  pitch: {
    level: 'involved',
    note: 'Prepare the application plus a project summary, deck, demo, or team information.',
  },
  party: { level: 'quick', note: 'Confirm the group, date, and any host requirements.' },
};

function statedString(quest: ApplicationResponse['quest'], key: string): string {
  const value = quest?.[key];
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

function statedEffort(quest: ApplicationResponse['quest']): QuestEffortLevel | null {
  const value = statedString(quest, 'application_effort');
  return value === 'quick' || value === 'some_prep' || value === 'involved' ? value : null;
}

function criteriaItems(quest: ApplicationResponse['quest']): string[] {
  const raw = quest?.criteria;
  const values = Array.isArray(raw) ? raw : typeof raw === 'string' ? [raw] : [];
  return values
    .filter((value): value is string => typeof value === 'string')
    .map((value) => value.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .slice(0, 8);
}

/** Requirements for one Side Quest, or null for the Find Work lane. */
export function requirementsForQuest(
  app: ApplicationResponse,
  kind: string,
  typicalCriteria: string,
): QuestRequirements | null {
  if ((app.vertical || 'career') === 'career' || kind === 'work') return null;

  const typical = TYPICAL_EFFORT[kind] ?? {
    level: 'some_prep' as const,
    note: 'Review the posting and prepare the information or materials it requests.',
  };
  const listedLevel = statedEffort(app.quest);
  const level = listedLevel ?? typical.level;
  const display = EFFORT_LABELS[level];
  const listedNote = statedString(app.quest, 'application_effort_note');

  const structuredCriteria = criteriaItems(app.quest);
  const listedBring = statedString(app.quest, 'bring');
  const criteria = structuredCriteria.length
    ? { items: structuredCriteria, basis: 'listed' as const }
    : listedBring
      ? { items: [listedBring], basis: 'listed' as const }
      : { items: [typicalCriteria], basis: 'typical' as const };

  return {
    effort: {
      level,
      label: display.label,
      time: display.time,
      note: listedNote || typical.note,
      basis: listedLevel || listedNote ? 'listed' : 'typical',
    },
    criteria,
  };
}

/** One to three filled marks for the compact poster treatment. */
export function effortMarks(level: QuestEffortLevel): number {
  return level === 'quick' ? 1 : level === 'some_prep' ? 2 : 3;
}
