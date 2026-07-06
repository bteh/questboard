export const STATUS_OPTIONS = [
  'found', 'reviewed', 'applying', 'applied',
  'interviewing', 'offer', 'rejected', 'withdrawn',
] as const;

export type StatusOption = typeof STATUS_OPTIONS[number];

/** Properly capitalized display labels for status values */
export const STATUS_LABELS: Record<string, string> = {
  found: 'Found',
  reviewed: 'Reviewed',
  applying: 'Applying',
  applied: 'Applied',
  interviewing: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
};

/** Properly capitalized display labels for recommendation values */
export const RECOMMENDATION_LABELS: Record<string, string> = {
  STRONG_APPLY: 'Strong Apply',
  APPLY: 'Apply',
  MAYBE: 'Maybe',
  SKIP: 'Skip',
};

interface BadgeColors {
  bg: string;
  text: string;
  darkBg: string;
  darkText: string;
}

// Warm palette badge presets. Sage = positive / progress (the app's one green),
// danger = negative (the app's one red). Amber is kept inline where it applies.
const SAGE_BADGE: BadgeColors = { bg: '#E3EDE7', text: '#3F6B54', darkBg: '#25382E', darkText: '#8FC2A4' };
const DANGER_BADGE: BadgeColors = { bg: '#F6DFDC', text: '#A23A30', darkBg: '#3A211E', darkText: '#E9A69E' };
const AMBER_BADGE: BadgeColors = { bg: '#FEF3C7', text: '#92400E', darkBg: '#78350F', darkText: '#FDE68A' };
const TEAL_BADGE: BadgeColors = { bg: '#DCE9EA', text: '#3A6E73', darkBg: '#22383A', darkText: '#8FBEC2' };
const CLAY_BADGE: BadgeColors = { bg: '#F3E1D6', text: '#A85A33', darkBg: '#3E271A', darkText: '#DDA985' };
const OLIVE_BADGE: BadgeColors = { bg: '#ECEBD4', text: '#61662B', darkBg: '#39381C', darkText: '#C6C787' };

export const STATUS_COLORS: Record<string, BadgeColors> = {
  found:        { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' },
  reviewed:     SAGE_BADGE,
  applying:     AMBER_BADGE,
  applied:      SAGE_BADGE,
  interviewing: SAGE_BADGE,
  offer:        SAGE_BADGE,
  rejected:     DANGER_BADGE,
  withdrawn:    { bg: '#F1F5F9', text: '#64748B', darkBg: '#334155', darkText: '#94A3B8' },
};

export const STATUS_DOT_COLORS: Record<string, string> = {
  found: '#94A3B8',
  reviewed: '#3F6B54',
  applying: '#E0872F',
  applied: '#3F6B54',
  interviewing: '#3F6B54',
  offer: '#3F6B54',
  rejected: '#94A3B8',
  withdrawn: '#94A3B8',
};

export const RECOMMENDATION_COLORS: Record<string, BadgeColors> = {
  STRONG_APPLY: SAGE_BADGE,
  APPLY:        SAGE_BADGE,
  MAYBE:        AMBER_BADGE,
  SKIP:         DANGER_BADGE,
};

// Warm categorical hues so the 7 company tiers stay distinguishable on-palette.
export const COMPANY_TYPE_COLORS: Record<string, BadgeColors> = {
  'FAANG+':         AMBER_BADGE,
  'Big Tech':       CLAY_BADGE,
  'Elite Startup':  TEAL_BADGE,
  'Growth Stage':   SAGE_BADGE,
  'Early Startup':  OLIVE_BADGE,
  'Midsize':        { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' },
  'Enterprise':     { bg: '#E2E8F0', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' },
};

export const COMPANY_TYPES = [
  'FAANG+', 'Big Tech', 'Elite Startup', 'Growth Stage',
  'Early Startup', 'Midsize', 'Enterprise', 'Unknown',
] as const;

/** Plain-language descriptions for company type labels */
export const COMPANY_TYPE_DESCRIPTIONS: Record<string, string> = {
  'FAANG+': 'Top-tier global companies (Google, Apple, Meta, etc.)',
  'Big Tech': 'Large, well-known technology companies',
  'Elite Startup': 'Well-funded startups with strong reputations',
  'Growth Stage': 'Fast-growing companies gaining traction',
  'Early Startup': 'Newer companies, often under 50 employees',
  'Midsize': 'Established companies, typically 200–5,000 employees',
  'Enterprise': 'Large established corporations',
  'Unknown': 'Company size not yet classified',
};

export const SCORE_DIMENSIONS = [
  { key: 'technical_score', label: 'Skills Match', tooltip: 'How well your experience and skills match the job requirements', weight: 0.25 },
  { key: 'leadership_score', label: 'Leadership', tooltip: 'Opportunities to lead, manage, or mentor others', weight: 0.15 },
  { key: 'career_progression_score', label: 'Career Growth', tooltip: 'Whether this role advances your career from your current level', weight: 0.15 },
  { key: 'platform_building_score', label: 'Growth & Scope', tooltip: 'Opportunity to build something new, expand a program, or shape a team', weight: 0.13 },
  { key: 'comp_potential_score', label: 'Compensation', tooltip: 'Expected pay relative to your target salary', weight: 0.12 },
  { key: 'company_trajectory_score', label: 'Company Outlook', tooltip: 'Company stability, growth trajectory, and market position', weight: 0.10 },
  { key: 'culture_fit_score', label: 'Culture & Benefits', tooltip: 'Remote work, benefits, work-life balance, and team culture', weight: 0.10 },
] as const;

export type Recommendation = 'STRONG_APPLY' | 'APPLY' | 'MAYBE' | 'SKIP';

export type CompanyType = typeof COMPANY_TYPES[number];

export const SORT_OPTIONS = [
  { value: 'overall_score', label: 'Match Score' },
  { value: 'date_found', label: 'Most Recent' },
  { value: 'company', label: 'Company A\u2013Z' },
  { value: 'job_title', label: 'Title A\u2013Z' },
] as const;
