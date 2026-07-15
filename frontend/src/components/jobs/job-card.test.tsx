// @vitest-environment jsdom
/* Score provenance honesty on the card: a keyword-scored row never wears
   the AI-grade recommendation stamp. It gets a muted "rough keyword match"
   note instead, because the offline scale stamps STRONG_APPLY at lenient
   thresholds. AI-scored rows keep today's treatment exactly. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ApplicationResponse } from '@/types/application';

vi.mock('@/hooks/use-applications', () => ({
  useDeleteApplication: () => ({ mutate: vi.fn(), isPending: false }),
  useUpdateFeedback: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('./apply-drawer', () => ({ ApplyDrawer: () => null }));
vi.mock('./job-detail', () => ({ JobDetail: () => null }));

import { JobCard } from './job-card';

function makeApp(overrides: Partial<ApplicationResponse> = {}): ApplicationResponse {
  return {
    id: 1,
    job_title: 'Data Engineer',
    company: 'Acme',
    location: 'Chicago',
    job_url: 'https://example.com/jobs/1',
    source: 'greenhouse',
    description: '',
    is_remote: false,
    work_type: '',
    salary_min: null,
    salary_max: null,
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
    date_found: null,
    date_applied: null,
    notes: '',
    contact_name: '',
    contact_email: '',
    referral_source: '',
    url_status: 'unknown',
    last_checked_at: null,
    user_feedback: '',
    feedback_notes: '',
    search_run_id: null,
    first_seen_run_id: null,
    created_at: null,
    updated_at: null,
    ...overrides,
  };
}

afterEach(cleanup);

describe('score provenance on the job card', () => {
  it('a keyword-scored row shows the rough-match note, never the strong stamp', () => {
    render(
      <JobCard
        app={makeApp({
          recommendation: 'STRONG_APPLY',
          score_source: 'keyword',
          overall_score: 47,
        })}
      />,
    );
    expect(screen.getByText('rough keyword match')).toBeTruthy();
    expect(screen.queryByText('Strong Apply')).toBeNull();
  });

  it('an AI-scored row keeps the stamp and never the note', () => {
    render(
      <JobCard
        app={makeApp({
          recommendation: 'STRONG_APPLY',
          score_source: 'ai',
          overall_score: 82,
        })}
      />,
    );
    expect(screen.getByText('Strong Apply')).toBeTruthy();
    expect(screen.queryByText('rough keyword match')).toBeNull();
  });

  it('a row without provenance renders as before (startup backfill fills it)', () => {
    render(
      <JobCard
        app={makeApp({ recommendation: 'STRONG_APPLY', overall_score: 71 })}
      />,
    );
    expect(screen.getByText('Strong Apply')).toBeTruthy();
    expect(screen.queryByText('rough keyword match')).toBeNull();
  });
});
