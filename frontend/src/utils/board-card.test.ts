import { describe, expect, it } from 'vitest';
import {
  annualBounds,
  boardMeta,
  formatStatedPay,
  parseAmount,
  toBoardCard,
  withinPayCeiling,
} from './board-card';
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

function reportJson(strong: number, partial: number, missing: number): string {
  const requirements = [
    ...Array.from({ length: strong }, (_, i) => requirement('strong', i)),
    ...Array.from({ length: partial }, (_, i) => requirement('partial', strong + i)),
    ...Array.from({ length: missing }, (_, i) => requirement('missing', strong + partial + i)),
  ];
  return JSON.stringify({
    archetype: '',
    tldr: '',
    requirements,
    top_gaps: [],
    recommended_framing: '',
    red_flags: [],
  });
}

describe('career card grammar', () => {
  it('role is the title; the company leads the meta line, source secondary, remote once', () => {
    const card = toBoardCard(
      makeApp({ job_title: 'Senior Data Engineer', company: 'Acme', is_remote: true }),
      'BuiltIn',
    );
    expect(card.title).toBe('Senior Data Engineer');
    expect(card.meta).toContain('Acme, via BuiltIn');
    expect(card.meta).toContain('remote');
    // remote is stated once (on the meta), never repeated
    expect(card.meta.match(/remote/g) ?? []).toHaveLength(1);
  });

  it('a remote row shows its stated scope, never a bare "remote" lie', () => {
    const scoped = toBoardCard(
      makeApp({ is_remote: true, location: 'Remote, India' }),
      'Himalayas',
    );
    expect(scoped.meta).toContain('remote (India)');
    const us = toBoardCard(
      makeApp({ is_remote: true, location: 'Remote - USA' }),
      'Himalayas',
    );
    expect(us.meta).toContain('remote (USA)');
    // bare wording stays plain, and never renders empty parens
    const bare = toBoardCard(makeApp({ is_remote: true, location: 'Remote' }), 'x');
    expect(bare.meta).toContain('remote');
    expect(bare.meta).not.toContain('(');
  });

  it('never prints a JSON-key placeholder as the company', () => {
    // A mis-mapped scraper once stored the literal "name"; the card must read
    // as if no company was stated, leading with the source instead.
    const card = toBoardCard(
      makeApp({ job_title: 'Strategy Consultant', company: 'name', is_remote: true }),
      'Himalayas',
    );
    expect(card.meta).not.toContain('name,');
    expect(card.meta.startsWith('Himalayas')).toBe(true);
    expect(card.meta).toContain('remote');
  });
});

describe('needs line', () => {
  it('reports coverage when a real evaluation report exists', () => {
    const card = toBoardCard(makeApp({ evaluation_report_json: reportJson(7, 0, 2) }));
    expect(card.needs).toBe('Needs: resume, covers 7 of 9 requirements');
    expect(card.fit?.missing).toBe(2);
  });

  it('says just "Needs: resume" when no report exists', () => {
    const card = toBoardCard(makeApp());
    expect(card.needs).toBe('Needs: resume');
    expect(card.fit).toBeNull();
    expect(card.report).toBeNull();
  });

  it('never invents coverage from a malformed report', () => {
    const card = toBoardCard(makeApp({ evaluation_report_json: '{not json' }));
    expect(card.needs).toBe('Needs: resume');
    expect(card.fit).toBeNull();
  });

  it('counts only strong matches as covered', () => {
    const card = toBoardCard(makeApp({ evaluation_report_json: reportJson(3, 2, 4) }));
    expect(card.needs).toBe('Needs: resume, covers 3 of 9 requirements');
    expect(card.fit?.missing).toBe(4);
  });
});

describe('pay honesty', () => {
  it('shows no pay line at all when the record has no salary data', () => {
    const card = toBoardCard(makeApp());
    expect(card.pay).toBeUndefined();
    expect(card.payUnit).toBeUndefined();
  });

  it('shows the stated range without provenance claims when source is unknown', () => {
    const card = toBoardCard(makeApp({ salary_min: 160000, salary_max: 190000 }));
    expect(card.pay).toBe('$160–190k');
    expect(card.payUnit).toBe('');
  });

  it('marks parsed-from-description pay as estimated', () => {
    const card = toBoardCard(
      makeApp({ salary_min: 160000, salary_max: 190000, salary_source: 'parsed_from_description' }),
    );
    expect(card.payUnit).toContain('estimated from description');
  });

  it('does not mark reported pay as estimated', () => {
    const card = toBoardCard(
      makeApp({
        salary_min: 160000,
        salary_max: 190000,
        salary_source: 'reported',
        salary_period: 'yearly',
      }),
    );
    expect(card.pay).toBe('$160–190k');
    expect(card.payUnit).toBe('a year');
  });

  it('displays raw stated hourly numbers, never the derived annualized figure', () => {
    const card = toBoardCard(
      makeApp({
        salary_min: 80,
        salary_max: 95,
        salary_period: 'hourly',
        salary_min_annualized: 166400,
        salary_max_annualized: 197600,
      }),
    );
    expect(card.pay).toBe('$80–95');
    expect(card.payUnit).toBe('/hr');
  });

  it('formats one-sided ranges', () => {
    expect(formatStatedPay(170000, null)).toBe('$170k+');
    expect(formatStatedPay(null, 95000)).toBe('up to $95k');
    expect(formatStatedPay(null, null)).toBe('');
  });

  it('collapses an equal-bounds range to one figure', () => {
    expect(formatStatedPay(60, 60)).toBe('$60');
    expect(formatStatedPay(200000, 200000)).toBe('$200k');
  });

  it('shows the stated currency, never a dollar-sign lie', () => {
    expect(formatStatedPay(160000, 190000, 'EUR')).toBe('€160–190k');
    expect(formatStatedPay(170000, null, 'GBP')).toBe('£170k+');
    expect(formatStatedPay(null, 95000, 'CHF')).toBe('up to CHF 95k');
    /* no currency stated keeps today's dollar rendering */
    expect(formatStatedPay(160000, 190000, null)).toBe('$160–190k');
  });

  it('carries salary_currency onto the career card pay', () => {
    const card = toBoardCard(
      makeApp({ salary_min: 160000, salary_max: 190000, salary_currency: 'EUR' }),
    );
    expect(card.pay).toBe('€160–190k');
  });

  it('carries salary_currency onto quest pay', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'study',
        salary_min: 100,
        salary_max: 125,
        salary_currency: 'GBP',
        salary_period: 'session',
        quest: {},
      }),
    );
    expect(card.pay).toBe('£100–125');
    expect(card.payUnit).toBe('a session');
  });
});

describe('posted label honesty', () => {
  it('says nothing about freshness when date confidence is missing', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86_400_000).toISOString();
    const meta = boardMeta(
      makeApp({ date_posted: threeDaysAgo, date_confidence: 'missing' }),
    );
    expect(meta).not.toContain('posted');
    expect(meta).toBe('greenhouse, Chicago');
  });

  it('says nothing about freshness when there is no date at all', () => {
    const meta = boardMeta(makeApp());
    expect(meta).not.toContain('posted');
  });

  it('shows the true age when the date is verifiable', () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86_400_000).toISOString();
    const meta = boardMeta(
      makeApp({ date_posted: threeDaysAgo, date_confidence: 'exact', is_remote: true }),
    );
    expect(meta).toBe('greenhouse, posted 3 days ago, remote');
  });

  it('prefers the passed source label', () => {
    const meta = boardMeta(makeApp(), 'Greenhouse');
    expect(meta).toBe('Greenhouse, Chicago');
  });
});

describe('status mapping', () => {
  it('renders the applied stamp with its date when a timestamp exists', () => {
    const card = toBoardCard(
      makeApp({ status: 'applied', date_applied: '2026-06-30T12:00:00Z' }),
    );
    expect(card.applied).toBe('Applied, Jun 30');
  });

  it('renders the applied stamp without inventing a date', () => {
    const card = toBoardCard(makeApp({ status: 'applied', date_applied: null }));
    expect(card.applied).toBe('Applied');
  });

  it('maps the clipped status to a clipped card', () => {
    const card = toBoardCard(
      makeApp({ status: 'clipped', updated_at: '2026-07-06T12:00:00Z' }),
    );
    expect(card.clippedDate).toBe('Jul 6');
    expect(card.applied).toBeUndefined();
  });

  it('still maps the legacy reviewed status to a clipped card', () => {
    const card = toBoardCard(
      makeApp({ status: 'reviewed', updated_at: '2026-07-06T12:00:00Z' }),
    );
    expect(card.clippedDate).toBe('Jul 6');
    expect(card.applied).toBeUndefined();
  });

  it('leaves found rows unclipped', () => {
    const card = toBoardCard(makeApp());
    expect(card.clippedDate).toBeUndefined();
    expect(card.applied).toBeUndefined();
  });
});

describe('score provenance', () => {
  it('carries score_source onto the career card', () => {
    const keyword = toBoardCard(makeApp({ score_source: 'keyword' }));
    expect(keyword.scoreSource).toBe('keyword');
    const ai = toBoardCard(makeApp({ score_source: 'ai' }));
    expect(ai.scoreSource).toBe('ai');
  });

  it('maps missing provenance to null, never a guess', () => {
    const card = toBoardCard(makeApp());
    expect(card.scoreSource).toBeNull();
  });
});

describe('quest rows', () => {
  it('maps an unpaid camera event honestly: no pay line, no resume line', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'camera',
        job_title: 'Jimmy Kimmel Live audience',
        company: '1iota',
        source: 'oneiota',
        location: 'Los Angeles',
        first_quest_ok: true,
        event_start: '2026-07-14T12:00:00',
        quest: { show: 'Jimmy Kimmel Live', age_min: 18, max_tickets: 4 },
      }),
      '1iota',
    );
    expect(card.vertical).toBe('camera');
    /* company just restates the source, so the title stands alone */
    expect(card.title).toBe('Jimmy Kimmel Live audience');
    expect(card.pay).toBeUndefined();
    expect(card.payUnit).toBeUndefined();
    expect(card.meta).toBe('1iota, taping Jul 14, Los Angeles');
    expect(card.needs).toBe('Needs: ages 18 and up, up to 4 tickets');
    expect(card.needs).not.toContain('resume');
    expect(card.firstQuest).toBe(true);
    expect(card.fit).toBeNull();
    expect(card.report).toBeNull();
  });

  it('never repeats a counterparty the title already names', () => {
    /* speak rows: title "Speak at X", company X — a 2026-07-12 live
       poster read "Speak at X, X" before this rule */
    const card = toBoardCard(
      makeApp({
        job_title: 'Speak at Conf42 MLOps 2026',
        company: 'Conf42 MLOps 2026',
        vertical: 'speak',
        source: 'papercall',
      }),
      'PaperCall',
    );
    expect(card.title).toBe('Speak at Conf42 MLOps 2026');
  });

  it('renders session pay the mock way: "$125" with a "max" unit for up-to chips', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'study',
        company: 'FocusGroups.org',
        source: 'focusgroups_org',
        location: 'Chicago',
        salary_min: null,
        salary_max: 125,
        salary_period: 'session',
        salary_source: 'reported',
        quest: { age_min: 21, age_max: 45, category: 'Focus Group' },
      }),
    );
    expect(card.pay).toBe('$125');
    expect(card.payUnit).toBe('max');
    expect(card.needs).toBe('Needs: screener only, ages 21 to 45');
    expect(card.title).toBe('Data Engineer');
  });

  it('renders a stated session range with its period word', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'study',
        salary_min: 100,
        salary_max: 125,
        salary_period: 'session',
        quest: {},
      }),
    );
    expect(card.pay).toBe('$100–125');
    expect(card.payUnit).toBe('a session');
    expect(card.needs).toBe('Needs: screener only');
  });

  it('renders a casting day rate with its stated hours', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'camera',
        salary_min: 500,
        salary_max: 500,
        salary_period: 'daily',
        quest: { session_hours: 12, age_min: 18, age_max: 35, union: 'non-union' },
      }),
    );
    expect(card.pay).toBe('$500');
    expect(card.payUnit).toBe('/12 hr');
    expect(card.needs).toBe('Needs: ages 18 to 35, non-union');
  });

  it('labels rolling sign-ups in the meta instead of an event date', () => {
    const card = toBoardCard(
      makeApp({
        vertical: 'study',
        source: 'playtestcloud',
        is_rolling: true,
        is_remote: true,
        salary_min: 9,
        salary_max: 11,
        salary_period: 'hourly',
        quest: {},
      }),
    );
    expect(card.meta).toBe('playtestcloud, rolling sign-up, remote');
    expect(card.pay).toBe('$9–11');
    expect(card.payUnit).toBe('/hr');
  });

  it('says nothing in the needs line when the source stated nothing', () => {
    const card = toBoardCard(makeApp({ vertical: 'lens' }));
    expect(card.needs).toBe('');
    expect(card.firstQuest).toBeUndefined();
  });

  it('keeps rows without a vertical on the career shape', () => {
    expect(toBoardCard(makeApp()).vertical).toBe('career');
    expect(toBoardCard(makeApp({ vertical: 'weird' })).vertical).toBe('career');
    expect(toBoardCard(makeApp({ vertical: 'camera' })).vertical).toBe('camera');
  });

  it('gives every registry-known lane the quest shape, never a hand list', () => {
    /* regression: house/odd/flip once collapsed to career and rendered a
       degenerate "$300–300" range through the career pay formatter */
    const bonus = toBoardCard(
      makeApp({
        vertical: 'house',
        job_title: 'Chase $300 Bonus',
        company: 'Doctor of Credit',
        salary_min: 300,
        salary_max: 300,
      }),
    );
    expect(bonus.vertical).toBe('house');
    expect(bonus.pay).toBe('$300');
    expect(bonus.fit).toBeNull();

    const task = toBoardCard(makeApp({ vertical: 'odd', job_title: 'Assemble a desk' }));
    expect(task.vertical).toBe('odd');
    expect(task.needs).not.toContain('resume');
  });
});

describe('typed pay range helpers', () => {
  it('parses shorthand amounts', () => {
    expect(parseAmount('150k')).toBe(150000);
    expect(parseAmount('$1,500')).toBe(1500);
    expect(parseAmount(' 95 ')).toBe(95);
    expect(parseAmount('')).toBeNull();
    expect(parseAmount('abc')).toBeNull();
  });

  it('prefers annualized bounds for filtering', () => {
    const bounds = annualBounds(
      makeApp({ salary_min: 80, salary_max: 95, salary_min_annualized: 166400, salary_max_annualized: 197600 }),
    );
    expect(bounds).toEqual({ lo: 166400, hi: 197600 });
  });

  it('keeps unknown-pay rows inside any ceiling', () => {
    expect(withinPayCeiling(makeApp(), 100000)).toBe(true);
  });

  it('drops rows whose stated midpoint clears the ceiling', () => {
    const app = makeApp({ salary_min: 160000, salary_max: 190000 });
    expect(withinPayCeiling(app, 150000)).toBe(false);
    expect(withinPayCeiling(app, 175000)).toBe(true);
  });
});
