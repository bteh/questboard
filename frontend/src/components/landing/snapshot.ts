/* A frozen snapshot of the real board, for the public download page.
 *
 * The download page is served with no backend (the app runs on your Mac),
 * so the live hooks the in-app board uses never resolve here. These rows are
 * REAL listings captured from the board on the date below, trimmed to the
 * fields the poster renders. Nothing is invented. Drifting fields
 * (date_posted, event dates) are nulled so a static page never asserts a
 * freshness that has since gone stale; the page states its own "as of" date
 * and says plainly that the app keeps this fresh on your machine.
 *
 * To refresh: re-pull a handful of real rows from /board and /board/summary,
 * update SNAPSHOT_AS_OF and SNAPSHOT_TOTALS to match.
 */

import type { ApplicationResponse } from '@/types/application';

export const SNAPSHOT_AS_OF = 'July 18, 2026';

/** Real totals from /board/summary on the snapshot date. quests = side-quest
 *  total (questTotal, career excluded); addedToday = side-quest new_today. */
export const SNAPSHOT_TOTALS = { quests: 2467, addedToday: 43 } as const;

/** Display labels for the sources in this snapshot (offline, no scraper API). */
export const SNAPSHOT_SOURCE_LABELS: Record<string, string> = {
  userinterviews: 'User Interviews',
  focusgroups_org: 'FocusGroups.org',
  urbansitter: 'UrbanSitter',
  castingnetworks: 'Casting Networks',
  builtin: 'Built In',
};

/* Shared defaults for the fields the poster type requires but the card never
   reads. Kept in one place so the real rows below stay readable. */
const BLANK = {
  is_remote: false,
  work_type: '',
  salary_currency: '',
  salary_min_annualized: null,
  salary_max_annualized: null,
  overall_score: null,
  technical_score: null,
  leadership_score: null,
  platform_building_score: null,
  comp_potential_score: null,
  company_trajectory_score: null,
  culture_fit_score: null,
  career_progression_score: null,
  recommendation: '',
  score_reasoning: '',
  key_strengths: [],
  key_gaps: [],
  funding_stage: null,
  total_funding: null,
  employee_count: null,
  company_type: '',
  company_intel_json: '',
  resume_tweaks_json: '',
  evaluation_report_json: '',
  cover_letter: '',
  application_method: '',
  profile: 'default',
  status: 'found',
  date_applied: null,
  notes: '',
  contact_name: '',
  contact_email: '',
  referral_source: '',
  url_status: 'alive',
  last_checked_at: null,
  user_feedback: '',
  feedback_notes: '',
  search_run_id: null,
  first_seen_run_id: null,
  created_at: null,
  updated_at: null,
  date_posted: null,
  date_confidence: 'missing' as const,
  event_start: null,
  event_end: null,
  is_rolling: false,
};

/** Three real side-quest listings, shown pinned in the hero window. */
export const SNAPSHOT_HERO = [
  {
    ...BLANK,
    id: 1252,
    vertical: 'think',
    job_title: 'In-Home Product Test',
    company: 'CCR Quant',
    location: 'multiple locations',
    job_url: 'https://www.userinterviews.com/projects/QhLywTK8lA/apply',
    source: 'userinterviews',
    description:
      'Unmoderated task. Takes 10 minutes. Pays $1500.00 via Visa gift card. Recruiting individuals for a 12-week at-home product test.',
    is_remote: true,
    salary_min: 1500,
    salary_max: 1500,
    salary_period: 'session',
    salary_source: 'reported',
    first_quest_ok: false,
  },
  {
    ...BLANK,
    id: 4043,
    vertical: 'study',
    job_title: 'Research Study on Personal Banking',
    company: 'FocusGroups.org',
    location: '',
    job_url:
      'https://focusgroups.org/category/interview-studies/research-study-on-personal-banking-250/d3c6ae22-63fc-4e87-b0d2-bc7c0bb8fe0d/',
    source: 'focusgroups_org',
    description: 'One-on-one interview on personal banking. Topic: finance.',
    salary_min: 250,
    salary_max: 250,
    salary_period: 'session',
    salary_source: 'reported',
    first_quest_ok: true,
  },
  {
    ...BLANK,
    id: 5045,
    vertical: 'lookafter',
    job_title: 'Sitter for 2 children (4 and 7 years)',
    company: 'Posted via UrbanSitter',
    location: 'Mountain View, CA',
    job_url: 'https://www.urbansitter.com/job/1470056',
    source: 'urbansitter',
    description:
      'Looking for a weekend sitter. Two easy boys who love cars, imaginative play, and snacks.',
    salary_min: null,
    salary_max: null,
    salary_period: '',
    salary_source: null,
    first_quest_ok: false,
  },
] as unknown as ApplicationResponse[];

/** One real career listing, shown beside a side quest in "two workflows". */
export const SNAPSHOT_CAREER = {
  ...BLANK,
  id: 5038,
  vertical: 'career',
  job_title: 'Manager, Industry Solutions Engineering (Data Science)',
  company: 'Microsoft',
  location: 'United States',
  job_url:
    'https://builtin.com/job/multidisciplinary-manager-industry-solutions-engineering-ise-data-science/10218421',
  source: 'builtin',
  description: '',
  is_remote: true,
  work_type: 'remote',
  salary_min: 143000,
  salary_max: 304000,
} as unknown as ApplicationResponse;
