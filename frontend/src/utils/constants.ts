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

export const STATUS_COLORS: Record<string, BadgeColors> = {
  found:        { bg: '#F1F5F9', text: '#334155', darkBg: '#334155', darkText: '#CBD5E1' },
  reviewed:     { bg: '#E0E7FF', text: '#3730A3', darkBg: '#312E81', darkText: '#A5B4FC' },
  applying:     { bg: '#FEF3C7', text: '#92400E', darkBg: '#78350F', darkText: '#FDE68A' },
  applied:      { bg: '#DBEAFE', text: '#1E40AF', darkBg: '#1E3A5F', darkText: '#93C5FD' },
  interviewing: { bg: '#DCFCE7', text: '#166534', darkBg: '#14532D', darkText: '#86EFAC' },
  offer:        { bg: '#D1FAE5', text: '#065F46', darkBg: '#064E3B', darkText: '#6EE7B7' },
  rejected:     { bg: '#FEE2E2', text: '#991B1B', darkBg: '#7F1D1D', darkText: '#FCA5A5' },
  withdrawn:    { bg: '#F1F5F9', text: '#64748B', darkBg: '#334155', darkText: '#94A3B8' },
};

export const STATUS_DOT_COLORS: Record<string, string> = {
  found: '#94A3B8',
  reviewed: '#6366F1',
  applying: '#F59E0B',
  applied: '#3B82F6',
  interviewing: '#10B981',
  offer: '#10B981',
  rejected: '#94A3B8',
  withdrawn: '#94A3B8',
};

export const RECOMMENDATION_COLORS: Record<string, BadgeColors> = {
  STRONG_APPLY: { bg: '#DCFCE7', text: '#166534', darkBg: '#14532D', darkText: '#86EFAC' },
  APPLY:        { bg: '#DBEAFE', text: '#1E40AF', darkBg: '#1E3A5F', darkText: '#93C5FD' },
  MAYBE:        { bg: '#FEF3C7', text: '#92400E', darkBg: '#78350F', darkText: '#FDE68A' },
  SKIP:         { bg: '#FEE2E2', text: '#991B1B', darkBg: '#7F1D1D', darkText: '#FCA5A5' },
};

export const COMPANY_TYPE_COLORS: Record<string, BadgeColors> = {
  'FAANG+':         { bg: '#FEF3C7', text: '#92400E', darkBg: '#78350F', darkText: '#FDE68A' },
  'Big Tech':       { bg: '#DBEAFE', text: '#1E40AF', darkBg: '#1E3A5F', darkText: '#93C5FD' },
  'Elite Startup':  { bg: '#E0E7FF', text: '#3730A3', darkBg: '#312E81', darkText: '#A5B4FC' },
  'Growth Stage':   { bg: '#DCFCE7', text: '#166534', darkBg: '#14532D', darkText: '#86EFAC' },
  'Early Startup':  { bg: '#F0FDF4', text: '#14532D', darkBg: '#14532D', darkText: '#86EFAC' },
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
  { key: 'technical_score', label: 'Skills Match', tooltip: 'How well your skills match the job requirements', weight: 0.25 },
  { key: 'leadership_score', label: 'Leadership', tooltip: 'Opportunities to lead, manage, or grow into leadership', weight: 0.15 },
  { key: 'career_progression_score', label: 'Career Growth', tooltip: 'Whether this role is a step up from your current position', weight: 0.15 },
  { key: 'platform_building_score', label: 'Builder Opportunity', tooltip: 'Chance to build something new or shape a team from early stages', weight: 0.13 },
  { key: 'comp_potential_score', label: 'Compensation', tooltip: 'Expected pay relative to your target salary', weight: 0.12 },
  { key: 'company_trajectory_score', label: 'Company Growth', tooltip: 'Company stability, growth trajectory, and market position', weight: 0.10 },
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
