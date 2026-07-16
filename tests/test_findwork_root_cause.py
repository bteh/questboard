"""Root-cause fixes for weak resume->job find-work results.

Two bugs, traced from the code and confirmed by an octo debate (2026-07-15):

1. Quota starvation (hosted managed-AI). Every search AI-scored up to 60 jobs
   with the SHARED platform LLM, draining the same daily quota the one-shot
   resume analysis needs to extract target_roles. Starved analysis left
   target_roles empty, which turned the role filter into a no-op, so the wrong
   jobs reached the board. In hosted managed-AI mode, job scoring must stay
   keyword-only (free, consistent) so the budget is reserved for the resume
   analysis that actually sets target_roles.

   NOTE: ai_score_top_n=0 means "AI-score ALL jobs" (the opposite of off), so
   the lever is a separate ``ai_score_jobs`` flag, not that number.

2. The role filter passed the whole scrape pool through whenever target_roles
   was empty. When only a current_title survives, the filter should bite on it
   instead of surfacing every unrelated job — while never zeroing the board.
"""
from __future__ import annotations


# ── Bug 1: hosted managed-AI reserves the shared LLM for resume analysis ──


def test_hosted_managed_ai_turns_off_per_job_ai_scoring(monkeypatch):
    monkeypatch.setenv("HOSTED_MODE", "true")
    monkeypatch.setenv("HOSTED_PLATFORM_MANAGED_AI", "true")
    from app.schemas.workspace import WorkspacePreferences
    from app.services.workspace_service import build_pipeline_config_override

    override = build_pipeline_config_override(WorkspacePreferences(), "ws1")
    # Per-job AI scoring is OFF so many concurrent searches can't drain the
    # shared quota the one-shot resume analysis needs.
    assert override["search_settings"]["ai_score_jobs"] is False


def test_desktop_keeps_per_job_ai_scoring(monkeypatch):
    monkeypatch.setenv("HOSTED_MODE", "false")
    from app.schemas.workspace import WorkspacePreferences
    from app.services.workspace_service import build_pipeline_config_override

    override = build_pipeline_config_override(WorkspacePreferences(), "ws1")
    # A desktop / BYOK user pays for their own AI, so per-job scoring stays on.
    assert override["search_settings"].get("ai_score_jobs", True) is True


def test_score_jobs_skips_ai_when_ai_score_jobs_false():
    """With the flag off, a configured LLM is NOT spent on per-job scoring."""
    from job_finder.pipeline import JobFinderPipeline

    class _FakeLLM:
        is_configured = True

    pipe = JobFinderPipeline(llm=_FakeLLM(), profile=None)
    pipe.config = {"search_settings": {"ai_score_jobs": False}}
    calls = {"ai": 0, "kw": 0}
    pipe._score_jobs_ai = lambda jobs, *a, **k: (calls.__setitem__("ai", calls["ai"] + 1) or jobs)
    pipe._score_jobs_keyword = lambda jobs, *a, **k: (calls.__setitem__("kw", calls["kw"] + 1) or jobs)

    jobs = [{"title": "Data Engineer", "company": "X", "url": "http://a"}]
    pipe.score_jobs(jobs, resume_text="resume", use_ai=True)

    assert calls["ai"] == 0  # the shared quota is not spent on job scoring
    assert calls["kw"] == 1


def test_score_jobs_uses_ai_when_flag_absent():
    """Default (desktop) still AI-scores when an LLM is configured."""
    from job_finder.pipeline import JobFinderPipeline

    class _FakeLLM:
        is_configured = True

    pipe = JobFinderPipeline(llm=_FakeLLM(), profile=None)
    pipe.config = {"search_settings": {}}
    calls = {"ai": 0, "kw": 0}
    pipe._score_jobs_ai = lambda jobs, *a, **k: (calls.__setitem__("ai", calls["ai"] + 1) or jobs)
    pipe._score_jobs_keyword = lambda jobs, *a, **k: (calls.__setitem__("kw", calls["kw"] + 1) or jobs)

    jobs = [{"title": "Data Engineer", "company": "X", "url": "http://a"}]
    pipe.score_jobs(jobs, resume_text="resume", use_ai=True)

    assert calls["ai"] == 1
    assert calls["kw"] == 0


# ── Bug 2: the role filter bites on current_title when target_roles is empty ──


def _pipeline_with(config: dict):
    from job_finder.pipeline import JobFinderPipeline

    pipe = JobFinderPipeline(llm=None, profile=None)
    pipe.config = config
    return pipe


def test_role_filter_falls_back_to_current_title():
    pipe = _pipeline_with(
        {"target_roles": [], "career_baseline": {"current_title": "Data Engineer"}}
    )
    jobs = [
        {"title": "Senior Data Engineer", "company": "Stripe", "url": "http://a"},
        {"title": "Registered Nurse - ICU", "company": "Kaiser", "url": "http://b"},
    ]
    titles = {j["title"] for j in pipe.filter_by_role(jobs)}
    assert "Senior Data Engineer" in titles
    assert "Registered Nurse - ICU" not in titles


def test_current_title_fallback_never_zeroes_the_board():
    # current_title matches nothing in the pool (a sourcing gap, not the
    # user's fault): keep the unfiltered set rather than show an empty board.
    pipe = _pipeline_with(
        {"target_roles": [], "career_baseline": {"current_title": "Data Engineer"}}
    )
    jobs = [
        {"title": "Registered Nurse - ICU", "company": "Kaiser", "url": "http://b"},
        {"title": "Line Cook", "company": "Cafe", "url": "http://c"},
    ]
    assert len(pipe.filter_by_role(jobs)) == 2


def test_no_roles_and_no_current_title_passes_everything():
    # Backward-compatible with the documented "no roles configured" fallback.
    pipe = _pipeline_with({"target_roles": []})
    jobs = [{"title": "Literally Anything", "company": "X", "url": "http://a"}]
    assert len(pipe.filter_by_role(jobs)) == 1


# ── Bug 3: out of tokens must degrade to keyword scoring, never leave a job unscored ──


def test_score_jobs_keyword_fallback_when_llm_raises():
    """A 429 'out of tokens' raises on every call. Every job must still get a
    keyword score, not come back unscored (which would sort at random)."""
    from job_finder.pipeline import JobFinderPipeline

    class _ExhaustedLLM:
        is_configured = True

        def chat_json(self, *a, **k):
            raise RuntimeError("429 daily token limit reached")

        def chat(self, *a, **k):
            raise RuntimeError("429 daily token limit reached")

    pipe = JobFinderPipeline(llm=_ExhaustedLLM(), profile=None)
    pipe.config = {"search_settings": {}}  # desktop path: use_ai stays on
    jobs = [
        {"title": "Senior Data Engineer", "company": "Stripe", "url": "http://a",
         "description": "python sql dbt"},
        {"title": "Data Platform Manager", "company": "Airbnb", "url": "http://b",
         "description": "snowflake analytics"},
    ]
    scored = pipe.score_jobs(jobs, resume_text="data platform engineering manager", use_ai=True)
    # No job may come back unscored — that is the out-of-tokens degradation.
    assert all(j.get("overall_score") is not None for j in scored), [
        (j["title"], j.get("overall_score")) for j in scored
    ]
