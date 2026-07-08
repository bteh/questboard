/**
 * Honesty cases for the rules-based quick read: every line comes from a
 * field the record states, and a missing field means the line is simply
 * absent, never guessed.
 */

import { describe, expect, it } from 'vitest';
import { quickRead, quickReadLines } from './quick-read';
import type { ApplicationResponse, RequirementMatch } from '@/types/application';

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

function requirement(strength: RequirementMatch['strength'], i: number): RequirementMatch {
  return { requirement: `req ${i}`, strength, evidence: '', mitigation: '' };
}

const daysAgo = (n: number) => new Date(Date.now() - n * 86_400_000).toISOString();

describe('quickRead honesty', () => {
  it('no stated pay means no pay line at all', () => {
    const text = quickRead(makeApp());
    expect(text).not.toMatch(/pay/i);
    expect(text).not.toContain('$');
  });

  it('stated pay renders the raw stated numbers with the unit', () => {
    const text = quickRead(
      makeApp({ salary_min: 160_000, salary_max: 190_000, salary_period: 'yearly' }),
    );
    expect(text).toContain('Pays $160–190k a year.');
  });

  it('parsed-from-description pay keeps the estimated marker', () => {
    const text = quickRead(
      makeApp({
        salary_min: 160_000,
        salary_max: 190_000,
        salary_period: 'yearly',
        salary_source: 'parsed_from_description',
      }),
    );
    expect(text).toContain('estimated from description');
  });

  it('missing post date makes no freshness claim', () => {
    const text = quickRead(makeApp({ date_posted: null }));
    expect(text).not.toMatch(/posted/i);
    expect(text).toContain('From greenhouse.');
  });

  it('missing-confidence dates say nothing even when a date string exists', () => {
    const text = quickRead(makeApp({ date_posted: daysAgo(3), date_confidence: 'missing' }));
    expect(text).not.toMatch(/posted/i);
  });

  it('a verifiable post date states the true age', () => {
    const text = quickRead(makeApp({ date_posted: daysAgo(3), date_confidence: 'exact' }));
    expect(text).toContain('Posted 3 days ago.');
  });

  it('remote wins the place line; no place means no place line', () => {
    expect(quickRead(makeApp({ is_remote: true }))).toContain('Remote.');
    const noPlace = quickRead(makeApp({ location: '' }));
    expect(noPlace).not.toContain('In ');
  });

  it('career rows carry the needs line the board computes', () => {
    const report = JSON.stringify({
      archetype: '',
      tldr: '',
      requirements: [requirement('strong', 0), requirement('strong', 1), requirement('missing', 2)],
      top_gaps: [],
      recommended_framing: '',
      red_flags: [],
    });
    const text = quickRead(makeApp({ evaluation_report_json: report }));
    expect(text).toContain('Needs: resume, covers 2 of 3 requirements.');
  });

  it('quest rows never claim a resume need and state only stated fields', () => {
    const text = quickRead(
      makeApp({
        vertical: 'study',
        quest: { healthy_volunteers: true, age_min: 18, age_max: 55 },
      }),
    );
    expect(text).not.toMatch(/resume/i);
    expect(text).toContain('Needs: screener only, healthy volunteers, ages 18 to 55.');
  });

  it('quest event dates use the vertical word; no date means no timing line', () => {
    const camera = quickRead(
      makeApp({ vertical: 'camera', event_start: '2026-07-14T12:00:00' }),
    );
    expect(camera).toContain('Taping Jul 14.');
    const none = quickRead(makeApp({ vertical: 'camera' }));
    expect(none).not.toContain('Taping');
  });

  it('rolling sign-up is stated when the source states it', () => {
    expect(quickRead(makeApp({ vertical: 'study', is_rolling: true }))).toContain(
      'Rolling sign-up.',
    );
  });

  it('a friendly source label replaces the raw source key', () => {
    expect(quickRead(makeApp(), 'Greenhouse')).toContain('From Greenhouse.');
  });

  it('a bare record still yields readable lines, never an empty answer', () => {
    const lines = quickReadLines(
      makeApp({ location: '', evaluation_report_json: '' }),
    );
    expect(lines.length).toBeGreaterThanOrEqual(1);
    expect(lines.length).toBeLessThanOrEqual(5);
    expect(lines[lines.length - 1]).toContain('From greenhouse.');
  });
});
