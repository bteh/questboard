// @vitest-environment jsdom
/* The board's job detail sheet: a fresh row shows exactly the facts, the
   description, and the door out, with no artifact folds at all. A row the
   pipeline drafted materials for gets collapsed folds below the
   description. The sheet reads the single-row detail fetch, so the folds
   arrive with the row itself. */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import type { ApplicationResponse } from '@/types/application';

let mockApp: ApplicationResponse | undefined;
vi.mock('@/hooks/use-applications', () => ({
  useApplication: () => ({ data: mockApp, isError: false }),
}));
vi.mock('@/hooks/use-scrapers', () => ({
  resolveSourceLabel: (source: string) => source,
}));

import { JobDetailSheet } from './job-detail-sheet';

function makeApp(overrides: Partial<ApplicationResponse> = {}): ApplicationResponse {
  return {
    id: 7,
    job_title: 'Staff Engineer',
    company: 'Acme',
    location: 'Portland, OR',
    job_url: 'https://example.com/job',
    source: 'lever',
    description: 'Build things.',
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
    status: 'new',
    date_found: null,
    date_applied: null,
    notes: '',
    contact_name: '',
    contact_email: '',
    referral_source: '',
    url_status: '',
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

afterEach(() => {
  cleanup();
  mockApp = undefined;
});

describe('JobDetailSheet artifacts', () => {
  it('shows no artifact folds on a fresh row', () => {
    mockApp = makeApp();
    const { container } = render(
      <JobDetailSheet jobId={7} labels={{}} onClose={() => {}} />,
    );
    expect(container.querySelectorAll('details').length).toBe(0);
    expect(screen.getByText('Build things.')).toBeTruthy();
    expect(screen.getByText('View original posting')).toBeTruthy();
  });

  it('shows collapsed folds when the row carries drafted materials', () => {
    mockApp = makeApp({
      cover_letter: 'Dear team, hello.',
      evaluation_report_json: JSON.stringify({
        requirements: [
          { requirement: '5 years of Go', strength: 'strong', evidence: '', mitigation: '' },
        ],
      }),
    });
    const { container } = render(
      <JobDetailSheet jobId={7} labels={{}} onClose={() => {}} />,
    );
    const folds = container.querySelectorAll('details');
    expect(folds.length).toBe(2);
    folds.forEach((fold) => expect(fold.hasAttribute('open')).toBe(false));
    /* the sheet's own furniture is untouched */
    expect(screen.getByText('Build things.')).toBeTruthy();
    expect(screen.getByText('View original posting')).toBeTruthy();
  });

  it('cleans stored markup out of the description and keeps the paragraphs', () => {
    mockApp = makeApp({
      description:
        '**Own** the pipeline.\n\n### Requirements\n<div class="content-intro">5 years with Python.</div>',
    });
    const { container } = render(
      <JobDetailSheet jobId={7} labels={{}} onClose={() => {}} />,
    );
    const desc = container.querySelector('.qb-jd-desc')!;
    expect(desc).toBeTruthy();
    expect(desc.textContent).not.toMatch(/\*\*|###|<div|content-intro/);
    expect(desc.textContent).toContain('Own the pipeline.');
    expect(desc.textContent).toContain('5 years with Python.');
    /* the sheet keeps line structure; pre-wrap CSS renders these as breaks */
    expect(desc.textContent).toContain('\n');
  });

  it('renders nothing extra while the detail fetch is still on its way', () => {
    mockApp = undefined;
    const { container } = render(
      <JobDetailSheet jobId={7} labels={{}} onClose={() => {}} />,
    );
    expect(container.querySelectorAll('details').length).toBe(0);
  });
});
