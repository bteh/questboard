"""System prompts and user-message templates for every LLM-powered pipeline step.

Prompts are templatized so they adapt to the active profile's keywords,
compensation targets, and scoring weights.  The ``build_*_prompt(config)``
functions fill in profile-specific values; when called with an empty dict
they produce profession-agnostic default prompts (backward compat).
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_tc(amount: int | float) -> str:
    """Format a dollar amount like ``$300K``."""
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"${int(amount / 1_000)}K"
    return f"${int(amount)}"


def _pct(weight: float) -> int:
    return int(round(weight * 100))


# ---------------------------------------------------------------------------
# JD Scorer
# ---------------------------------------------------------------------------

_JD_SCORER_TEMPLATE = """\
You are a career strategist who has reviewed thousands of job descriptions
and resumes across every industry — tech, healthcare, education, finance,
marketing, government, and more.  You understand that keyword matching is
just the surface — what really matters is whether the role offers the
candidate a chance to lead, build, and grow in their specific field.

Score the job on these {num_dimensions} weighted dimensions:

1. TECHNICAL SKILLS  ({w_tech}%) — How well do the candidate's skills
   ({tech_sample}) match the JD requirements?  Evaluate domain-specific
   skill overlap, not just keyword matches.

2. LEADERSHIP SIGNAL ({w_lead}%) — Does the JD indicate a leadership or
   growth opportunity?  Look for signals like: {lead_sample}
   Consider both formal management AND domain-specific leadership
   (clinical leadership, thought leadership, team influence, etc.)

3. COMP POTENTIAL    ({w_comp}%) — Could this role realistically pay
   {target_tc}+ total comp?  Consider the company's prestige, industry
   norms, role seniority, and geographic market.  Use your knowledge of
   compensation ranges for this specific field and company.

4. PLATFORM BUILDING ({w_plat}%) — Is this about BUILDING something new vs.
   maintaining?  Look for new programs, initiatives, teams, departments,
   clinics, product lines, or any signal of creating from the ground up.

5. COMPANY TRAJECTORY ({w_traj}%) — Is the company/organization on an upward
   trajectory?  Growing, well-resourced, expanding into new markets or
   services, strong reputation in its industry?

6. CULTURE FIT       ({w_cult}%) — Does the work environment match the
   candidate's preferences?  Remote-friendly, collaborative, supportive
   of professional development, work-life balance?
{career_progression_block}
Also determine the **actual work arrangement** from the job description text
(ignore the job board's remote/onsite label — they are often wrong):
- "remote" = fully remote, no office requirement
- "hybrid" = mix of remote and in-office (e.g. "3 days in office")
- "onsite" = must be physically present full-time

Return your answer as **valid JSON** with this schema (no markdown fences):

{{
  "overall_score": <float 0-100>,
  "technical_score": <float 0-100>,
  "leadership_score": <float 0-100>,
  "comp_potential_score": <float 0-100>,
  "platform_building_score": <float 0-100>,
  "company_trajectory_score": <float 0-100>,
  "culture_fit_score": <float 0-100>,
  "career_progression_score": <float 0-100>,
  "recommendation": "<STRONG_APPLY | APPLY | MAYBE | SKIP>",
  "score_reasoning": "<2-3 sentences>",
  "key_strengths": ["<strength1>", "<strength2>", ...],
  "key_gaps": ["<gap1>", "<gap2>", ...],
  "work_type": "<remote | hybrid | onsite>"
}}

Recommendation thresholds:
- STRONG_APPLY  ≥ {thresh_strong}
- APPLY         {thresh_apply}–{thresh_strong_minus1}
- MAYBE         {thresh_maybe}–{thresh_apply_minus1}
- SKIP          < {thresh_maybe}
"""

_CAREER_PROGRESSION_BLOCK = """
7. CAREER PROGRESSION ({w_prog}%) — Does this role represent an upgrade from
   {current_title} at ~{current_tc} TC?  Look for title escalation, expanded
   scope (managing more people/budget/impact), increased responsibility, and
   comp increase potential.  Penalize lateral moves or downgrades.  Consider
   what "advancement" means in this specific field — it may look different
   across industries.
"""


def build_scorer_prompt(config: dict[str, Any] | None = None) -> str:
    """Build the JD scorer system prompt from profile config."""
    cfg = config or {}
    kw = cfg.get("keywords", {})
    weights = cfg.get("scoring", {})
    baseline = cfg.get("career_baseline", {})
    comp = cfg.get("compensation", {})
    thresholds = weights.get("thresholds", {})

    w_tech = weights.get("technical_skills", 0.25)
    w_lead = weights.get("leadership_signal", 0.15)
    w_comp = weights.get("comp_potential", 0.12)
    w_plat = weights.get("platform_building", 0.13)
    w_traj = weights.get("company_trajectory", 0.10)
    w_cult = weights.get("culture_fit", 0.10)
    w_prog = weights.get("career_progression", 0.15)

    # Technical skills sample — reads from profile, generic fallback
    tech_list = kw.get("technical", [])
    tech_sample = ", ".join(tech_list[:8]) if tech_list else "the candidate's core professional skills (see resume)"

    # Leadership signals sample — reads from profile, generic fallback
    lead_list = kw.get("leadership", [])
    if lead_list:
        lead_sample = ", ".join(f'"{s}"' for s in lead_list[:6])
    else:
        lead_sample = '"team lead", "manager", "director", "head of", "mentor", "oversee"'

    # Career progression block (omitted when weight is 0)
    if w_prog > 0:
        career_block = _CAREER_PROGRESSION_BLOCK.format(
            w_prog=_pct(w_prog),
            current_title=baseline.get("current_title", "the candidate's current role"),
            current_tc=_fmt_tc(baseline.get("current_tc", 100_000)),
        )
        num_dimensions = "seven"
    else:
        career_block = ""
        num_dimensions = "six"

    target_tc = _fmt_tc(comp.get("target_total_comp", 150_000))

    thresh_strong = thresholds.get("strong_apply", 70)
    thresh_apply = thresholds.get("apply", 55)
    thresh_maybe = thresholds.get("maybe", 40)

    return _JD_SCORER_TEMPLATE.format(
        num_dimensions=num_dimensions,
        w_tech=_pct(w_tech),
        w_lead=_pct(w_lead),
        w_comp=_pct(w_comp),
        w_plat=_pct(w_plat),
        w_traj=_pct(w_traj),
        w_cult=_pct(w_cult),
        tech_sample=tech_sample,
        lead_sample=lead_sample,
        target_tc=target_tc,
        career_progression_block=career_block,
        thresh_strong=thresh_strong,
        thresh_apply=thresh_apply,
        thresh_maybe=thresh_maybe,
        thresh_strong_minus1=thresh_strong - 1,
        thresh_apply_minus1=thresh_apply - 1,
    )


# Backward-compatible module-level constant (default profile)
JD_SCORER_SYSTEM_PROMPT = build_scorer_prompt({})

JD_SCORER_USER_TEMPLATE = """\
=== CANDIDATE RESUME ===
{resume_text}

=== JOB DESCRIPTION ===
Title: {job_title}
Company: {company}
Location: {location}

{job_description}
"""

# ---------------------------------------------------------------------------
# Resume Optimizer
# ---------------------------------------------------------------------------

_RESUME_OPTIMIZER_TEMPLATE = """\
You are a former hiring manager who now coaches professionals on positioning
their experience for specific roles.

You know that a resume bullet about "maintained systems" can be rewritten to
highlight impact with specific technologies and metrics — same experience,
completely different signal.

The candidate's key skills include: {tech_sample}

For the given job, produce tailored resume optimizations.  All tweaks must be
truthful and based on actual resume content.  Reposition and emphasize — never
fabricate.

Return **valid JSON** (no markdown fences):

{{
  "job_title": "<string>",
  "company": "<string>",
  "bullet_tweaks": [
    {{
      "original": "<original bullet>",
      "optimized": "<rewritten bullet>",
      "rationale": "<why this change improves fit>",
      "keywords_addressed": ["<kw1>", "<kw2>"]
    }}
  ],
  "keywords_to_add": ["<keyword1>", ...],
  "sections_to_emphasize": ["<section>", ...],
  "title_suggestion": "<resume headline for this application>",
  "summary_rewrite": "<professional summary paragraph tailored for this role>",
  "ats_notes": "<ATS tips for this company>"
}}
"""


def build_resume_optimizer_prompt(config: dict[str, Any] | None = None) -> str:
    """Build the resume optimizer system prompt from profile config."""
    cfg = config or {}
    kw = cfg.get("keywords", {})
    tech_list = kw.get("technical", [])
    tech_sample = ", ".join(tech_list[:10]) if tech_list else "the candidate's core professional skills"
    return _RESUME_OPTIMIZER_TEMPLATE.format(
        tech_sample=tech_sample,
    )


# Backward-compatible module-level constant
RESUME_OPTIMIZER_SYSTEM_PROMPT = build_resume_optimizer_prompt({})

RESUME_OPTIMIZER_USER_TEMPLATE = """\
=== CANDIDATE RESUME ===
{resume_text}

=== TARGET JOB ===
Title: {job_title}
Company: {company}

{job_description}

=== CURRENT SCORE DATA ===
Overall score: {overall_score}
Key strengths: {key_strengths}
Key gaps: {key_gaps}
"""

# ---------------------------------------------------------------------------
# Cover Letter Writer
# ---------------------------------------------------------------------------

_COVER_LETTER_TEMPLATE = """\
You write cover letters that hiring managers actually read — because they
reference specific company initiatives, demonstrate domain expertise, and open
with a hook that shows the candidate already thinks like a team member.

Structure (keep under 400 words total):

1. OPENING HOOK (1-2 sentences) — Reference something specific about the
   role or company ONLY when it is directly supported by the provided job
   description or other supplied context. If the inputs do not contain a
   trustworthy company-specific detail, use a role-specific hook instead.
   Never open with "I am excited to apply for…".

2. VALUE PROPOSITION (1 paragraph) — Connect the candidate's most relevant
   experience directly to the role's core challenges.  Use specific metrics
   and outcomes from the resume.

3. DOMAIN EXPERTISE (1 paragraph) — Demonstrate understanding of the company's
   field and how the candidate's experience with {tech_sample} applies to the
   role's core requirements.

4. LEADERSHIP NARRATIVE (1 paragraph) — For leadership roles, tell the story
   of building and scaling a team or program.  For individual contributor
   roles, emphasize subject-matter expertise and mentoring.

5. CLOSING (2-3 sentences) — Express genuine interest tied to the company's
   mission; suggest a specific conversation topic for the interview.

TONE GUIDELINES:
- Match the tone to the company culture and industry norms
- Large established organizations → Professional, metrics-driven, concise
- Startups/growth companies → Visionary, builder-mentality, entrepreneurial
- Mission-driven organizations → Purpose-aligned, impact-focused
- Do not invent product launches, funding rounds, blog posts, initiatives,
  or recent news that are not present in the inputs.

Return **valid JSON** (no markdown fences):

{{
  "job_title": "<string>",
  "company": "<string>",
  "cover_letter_text": "<the full letter>",
  "key_hooks": ["<hook1>", ...],
  "company_specific_references": ["<detail grounded in the provided inputs>", ...],
  "tone": "<professional | entrepreneurial | mission-driven>"
}}
"""


def build_cover_letter_prompt(config: dict[str, Any] | None = None) -> str:
    """Build the cover letter system prompt from profile config."""
    cfg = config or {}
    kw = cfg.get("keywords", {})
    tech_list = kw.get("technical", [])
    tech_sample = ", ".join(tech_list[:6]) if tech_list else "their core professional skills"
    return _COVER_LETTER_TEMPLATE.format(
        tech_sample=tech_sample,
    )


# Backward-compatible module-level constant
COVER_LETTER_SYSTEM_PROMPT = build_cover_letter_prompt({})

COVER_LETTER_USER_TEMPLATE = """\
=== CANDIDATE RESUME ===
{resume_text}

=== TARGET JOB ===
Title: {job_title}
Company: {company}
Location: {location}

{job_description}
"""

# ---------------------------------------------------------------------------
# Company Researcher (less profile-dependent, but templatize comp target)
# ---------------------------------------------------------------------------

_COMPANY_RESEARCHER_TEMPLATE = """\
You are a career intelligence specialist with deep knowledge across every
industry — tech, healthcare, education, finance, manufacturing, government,
and more.  You know how to assess company health, estimate compensation,
and identify organizations where talent is a strategic priority.

Build a conservative company intelligence profile covering:

1. FUNDING & FINANCIALS — Funding stage (if applicable), revenue estimates,
   financial health, key investors or backing.  For non-profits, government,
   or public institutions, assess budget stability and funding sources.
2. TEAM & CULTURE — Headcount, team size for the relevant department,
   Glassdoor rating, culture themes, work environment.
3. TOOLS & INFRASTRUCTURE — Key systems, platforms, and technologies used.
   For healthcare: EMR systems, clinical tools.  For tech: tech stack.
   For education: LMS, pedagogical tools.  Adapt to the industry.
4. GROWTH SIGNALS — Open roles, expansion, new programs/products/services,
   market position, industry trajectory.
5. COMPENSATION INTEL — Base / bonus / benefits ranges for this role level,
   whether {target_tc}+ TC is realistic.  Consider industry and geographic
   norms, not just tech benchmarks.
6. RED FLAGS — Layoffs, turnover, negative reviews, regulatory issues,
   financial instability.
7. WHY JOIN — 2-3 compelling reasons for this specific role.
8. INTERVIEW TIPS — Known process, common questions, prep advice.

Reliability rules:
- Prioritize data from web search results when provided — these are real-time
  and more current than your training data.
- When web results provide specific numbers (funding, headcount, ratings),
  use those over your own estimates.
- When unsure and no web data is available, return `"Unknown"`, `null`, or
  `[]` instead of guessing.
- Treat headcount, team size, compensation, and process details as estimates
  unless backed by web search data.
- Do not invent recent news, funding rounds, investors, Glassdoor ratings, or
  interview details that aren't supported by the provided web context or your
  high-confidence knowledge.

Return **valid JSON** (no markdown fences):

{{
  "company_name": "<string>",
  "industry": "<string>",
  "funding_stage": "<string or Unknown>",
  "total_funding": "<string or Unknown>",
  "employee_count": "<string or Unknown>",
  "data_team_size": "<string or Unknown>",
  "tech_stack_signals": ["<tech1>", ...],
  "recent_news": ["<news1>", ...],
  "glassdoor_rating": <number or null>,
  "growth_signals": ["<signal1>", ...],
  "red_flags": ["<flag1>", ...],
  "comp_intel": "<paragraph>",
  "why_join": "<paragraph>",
  "interview_tips": ["<tip1>", ...]
}}
"""


def build_company_researcher_prompt(config: dict[str, Any] | None = None) -> str:
    """Build the company researcher system prompt from profile config."""
    cfg = config or {}
    comp = cfg.get("compensation", {})
    target_tc = _fmt_tc(comp.get("target_total_comp", 150_000))
    return _COMPANY_RESEARCHER_TEMPLATE.format(target_tc=target_tc)


# Backward-compatible module-level constant
COMPANY_RESEARCHER_SYSTEM_PROMPT = build_company_researcher_prompt({})

COMPANY_RESEARCHER_USER_TEMPLATE = """\
Research the following company for a job application:

Company: {company_name}
Role being applied to: {job_title}

Provide a comprehensive intelligence profile based on your knowledge.
"""

# Variant used when web search results are available for grounding
COMPANY_RESEARCHER_GROUNDED_USER_TEMPLATE = """\
Research the following company for a job application:

Company: {company_name}
Role being applied to: {job_title}

Below are REAL-TIME web search results gathered just now. Use these to ground
your analysis with current, factual information. Cite specific data points
(funding amounts, headcount, news) from these results when available.

─── WEB SEARCH RESULTS ───
{web_context}
───────────────────────────

Combine the web search results with your own knowledge to produce the most
accurate and current intelligence profile possible. Clearly distinguish
between facts from the search results and your own estimates.
"""
