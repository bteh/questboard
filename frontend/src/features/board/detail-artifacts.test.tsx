// @vitest-environment jsdom
/* The generated-artifact folds under the job detail sheet: draft cover
   letter, application kit, requirement check, company notes. Each fold
   renders only when its stored field holds usable data, arrives collapsed,
   and carries a caveat naming it generated work. Malformed JSON renders
   nothing and never crashes the sheet. The legacy scores and the
   Strong Apply style recommendation never appear here. */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ApplicationResponse } from '@/types/application';

import { DetailArtifacts } from './detail-artifacts';

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

const KIT_JSON = JSON.stringify({
  title_suggestion: 'Staff Platform Engineer',
  summary_rewrite: 'Engineer with ten years building platforms.',
  bullet_tweaks: [
    {
      original_bullet: 'Worked on infrastructure.',
      tweaked_bullet: 'Built the deploy pipeline serving 40 teams.',
      rationale: 'Names the scope.',
      target_keywords: ['pipeline'],
    },
  ],
  keywords_to_add: ['Kubernetes', 'Terraform'],
});

const REPORT_JSON = JSON.stringify({
  archetype: 'Platform builder',
  tldr: 'Solid overlap.',
  requirements: [
    {
      requirement: '5 years of Go',
      strength: 'strong',
      evidence: 'Led Go services at Acme.',
      mitigation: '',
    },
    {
      requirement: 'Kubernetes in production',
      strength: 'missing',
      evidence: '',
      mitigation: 'Mention the cluster migration.',
    },
  ],
  top_gaps: [],
  recommended_framing: '',
  red_flags: [],
});

const INTEL_JSON = JSON.stringify({
  funding_stage: 'Series B',
  employee_count: '200',
  recent_news: ['Raised a round in May'],
  nested_thing: { hidden: 'should not render' },
});

let writeText: ReturnType<typeof vi.fn>;

beforeEach(() => {
  writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
});

afterEach(() => {
  cleanup();
});

describe('DetailArtifacts', () => {
  it('renders nothing when no artifacts are stored', () => {
    const { container } = render(<DetailArtifacts app={makeApp()} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when every JSON field is malformed', () => {
    const { container } = render(
      <DetailArtifacts
        app={makeApp({
          resume_tweaks_json: 'not json{',
          evaluation_report_json: '{{nope',
          company_intel_json: '[broken',
        })}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders nothing when the JSON parses but holds nothing usable', () => {
    const { container } = render(
      <DetailArtifacts
        app={makeApp({
          cover_letter: '   ',
          resume_tweaks_json: '{}',
          evaluation_report_json: JSON.stringify({ requirements: [] }),
          company_intel_json: '{}',
        })}
      />,
    );
    expect(container.innerHTML).toBe('');
  });

  it('shows a collapsed draft cover letter fold with its caveat', () => {
    const { container } = render(
      <DetailArtifacts app={makeApp({ cover_letter: 'Dear team, I would like to apply.' })} />,
    );
    expect(screen.getByText(/draft cover letter/i)).toBeTruthy();
    expect(screen.getByText('Dear team, I would like to apply.')).toBeTruthy();
    expect(screen.getByText(/generated draft/i)).toBeTruthy();
    expect(screen.getByText(/not verified/i)).toBeTruthy();
    const fold = container.querySelector('details');
    expect(fold).toBeTruthy();
    expect(fold!.hasAttribute('open')).toBe(false);
  });

  it('shows the application kit with copy per field', () => {
    render(<DetailArtifacts app={makeApp({ resume_tweaks_json: KIT_JSON })} />);
    expect(screen.getByText(/application kit/i)).toBeTruthy();
    expect(screen.getByText('Staff Platform Engineer')).toBeTruthy();
    expect(screen.getByText('Engineer with ten years building platforms.')).toBeTruthy();
    expect(screen.getByText('Built the deploy pipeline serving 40 teams.')).toBeTruthy();
    expect(screen.getByText(/Kubernetes, Terraform/)).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: /copy suggested title/i }));
    expect(writeText).toHaveBeenCalledWith('Staff Platform Engineer');
    fireEvent.click(screen.getByRole('button', { name: /copy keywords/i }));
    expect(writeText).toHaveBeenCalledWith('Kubernetes, Terraform');
  });

  it('shows requirement check rows with the stored strength words', () => {
    render(<DetailArtifacts app={makeApp({ evaluation_report_json: REPORT_JSON })} />);
    expect(screen.getByText(/requirement check/i)).toBeTruthy();
    expect(screen.getByText('5 years of Go')).toBeTruthy();
    expect(screen.getByText('Kubernetes in production')).toBeTruthy();
    expect(screen.getByText('strong')).toBeTruthy();
    expect(screen.getByText('missing')).toBeTruthy();
    expect(screen.getByText('Led Go services at Acme.')).toBeTruthy();
    expect(screen.getByText('Mention the cluster migration.')).toBeTruthy();
  });

  it('shows company notes as labeled generated notes, skipping nested objects', () => {
    const { container } = render(
      <DetailArtifacts app={makeApp({ company_intel_json: INTEL_JSON })} />,
    );
    expect(screen.getByText(/company notes/i)).toBeTruthy();
    expect(screen.getByText('funding stage')).toBeTruthy();
    expect(screen.getByText('Series B')).toBeTruthy();
    expect(screen.getByText('Raised a round in May')).toBeTruthy();
    expect(screen.getByText(/generated notes/i)).toBeTruthy();
    expect(container.textContent).not.toContain('should not render');
  });

  it('keeps every fold collapsed by default when all artifacts exist', () => {
    const { container } = render(
      <DetailArtifacts
        app={makeApp({
          cover_letter: 'Dear team,',
          resume_tweaks_json: KIT_JSON,
          evaluation_report_json: REPORT_JSON,
          company_intel_json: INTEL_JSON,
        })}
      />,
    );
    const folds = container.querySelectorAll('details');
    expect(folds.length).toBe(4);
    folds.forEach((fold) => {
      expect(fold.hasAttribute('open')).toBe(false);
    });
  });

  it('never shows the legacy score or the recommendation stamp', () => {
    const { container } = render(
      <DetailArtifacts
        app={makeApp({
          cover_letter: 'Dear team,',
          evaluation_report_json: REPORT_JSON,
          overall_score: 88,
          technical_score: 91,
          recommendation: 'STRONG_APPLY',
          score_reasoning: 'High keyword overlap.',
        })}
      />,
    );
    const text = container.textContent ?? '';
    expect(text).not.toContain('88');
    expect(text).not.toContain('91');
    expect(text).not.toContain('STRONG_APPLY');
    expect(text).not.toContain('Strong Apply');
    expect(text).not.toContain('High keyword overlap.');
    expect(text.toLowerCase()).not.toContain('match score');
  });
});
