"""Streamlit UI for the Job Finder pipeline."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# Ensure job_finder package is importable
try:
    import job_finder  # noqa: F401
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv

load_dotenv()

from job_finder.llm_client import LLMClient, PRESETS
from job_finder.models.database import (
    DB_PATH,
    init_db,
    get_all_applications,
    update_application_status,
    save_application,
)
from job_finder.pipeline import JobFinderPipeline

# Initialize database
init_db()

# ── Page Config ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Job Finder — AI Job Search Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom Styling ────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .score-high { color: #00c853; font-weight: bold; }
    .score-medium { color: #ff9800; font-weight: bold; }
    .score-low { color: #f44336; font-weight: bold; }
    div[data-testid="stExpander"] {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        margin-bottom: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Helpers ───────────────────────────────────────────────────────────────

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

_STATUS_OPTIONS = [
    "found", "reviewed", "applying", "applied",
    "interviewing", "offer", "rejected", "withdrawn",
]


def _get_llm() -> LLMClient:
    """Create an LLM client from current env/config."""
    return LLMClient()


def _llm_status_badge(llm: LLMClient) -> None:
    """Show a colored badge for LLM connection status."""
    info = llm.get_provider_info()
    if not llm.is_configured:
        st.warning("⚠️ No LLM configured — basic scoring only")
    elif llm.is_available():
        st.success(f"✅ Connected to **{info['model']}** via {info['label']}")
    else:
        st.error(f"❌ LLM configured ({info['label']}) but not reachable. Is the proxy running?")


# ── Sidebar ───────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("🔍 Job Finder")
    st.caption("AI-Powered Job Search")
    st.divider()

    page = st.radio(
        "Navigation",
        [
            "🏠 Dashboard",
            "🚀 Run Search",
            "📋 All Applications",
            "📊 Analytics",
            "⚙️ Settings",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    # Quick stats
    all_apps = get_all_applications()
    total = len(all_apps)
    strong_apply = len([a for a in all_apps if a.recommendation == "STRONG_APPLY"])
    applied = len([a for a in all_apps if a.status == "applied"])
    interviewing = len([a for a in all_apps if a.status == "interviewing"])

    st.metric("Total Tracked", total)
    col1, col2 = st.columns(2)
    col1.metric("🔥 Strong Fit", strong_apply)
    col2.metric("✅ Applied", applied)
    st.metric("🎯 Interviewing", interviewing)

    st.divider()

    # LLM status
    llm = _get_llm()
    info = llm.get_provider_info()
    if llm.is_configured:
        st.caption(f"LLM: {info['model']}")
    else:
        st.caption("LLM: not configured")

# ── Dashboard Page ────────────────────────────────────────────────────────

if page == "🏠 Dashboard":
    st.title("Job Search Command Center")

    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Found", total)
    col2.metric("Strong Matches", strong_apply, help="Score >= 80")
    col3.metric("Applied", applied)
    col4.metric("Interviewing", interviewing)

    st.divider()

    # Top opportunities
    st.subheader("🔥 Top Opportunities")

    strong_apps = [
        a
        for a in all_apps
        if a.recommendation in ("STRONG_APPLY", "APPLY") and a.overall_score
    ]
    strong_apps.sort(key=lambda x: x.overall_score or 0, reverse=True)

    if strong_apps:
        for app in strong_apps[:10]:
            score = app.overall_score or 0
            score_color = (
                "🟢" if score >= 80 else "🟡" if score >= 65 else "🔴"
            )

            with st.expander(
                f"{score_color} **{app.company}** — {app.job_title} | "
                f"Score: {score:.0f} | {app.recommendation} | Status: {app.status}"
            ):
                col1, col2, col3 = st.columns([2, 2, 1])

                with col1:
                    st.markdown(f"**Location:** {app.location}")
                    st.markdown(f"**Source:** {app.source}")
                    if app.job_url:
                        st.markdown(f"[View Job Posting]({app.job_url})")
                    if app.salary_min or app.salary_max:
                        sal_min = f"${app.salary_min:,.0f}" if app.salary_min else "?"
                        sal_max = f"${app.salary_max:,.0f}" if app.salary_max else "?"
                        st.markdown(f"**Salary Range:** {sal_min} - {sal_max}")

                with col2:
                    st.markdown("**Score Breakdown:**")
                    if app.technical_score:
                        st.progress(app.technical_score / 100, text=f"Technical: {app.technical_score:.0f}")
                    if app.leadership_score:
                        st.progress(app.leadership_score / 100, text=f"Leadership: {app.leadership_score:.0f}")
                    if app.platform_building_score:
                        st.progress(
                            app.platform_building_score / 100,
                            text=f"Platform Building: {app.platform_building_score:.0f}",
                        )
                    if app.comp_potential_score:
                        st.progress(
                            app.comp_potential_score / 100,
                            text=f"Comp Potential: {app.comp_potential_score:.0f}",
                        )

                with col3:
                    current_status = app.status or "found"
                    try:
                        status_index = _STATUS_OPTIONS.index(current_status)
                    except ValueError:
                        status_index = 0

                    new_status = st.selectbox(
                        "Update Status",
                        _STATUS_OPTIONS,
                        index=status_index,
                        key=f"status_{app.id}",
                    )
                    if st.button("Update", key=f"btn_{app.id}"):
                        update_application_status(app.id, new_status)
                        st.rerun()

                # Strengths and gaps
                if app.key_strengths:
                    strengths = app.strengths_list
                    if strengths:
                        st.markdown("**Key Strengths:**")
                        for s in strengths:
                            st.markdown(f"- {s}")

                if app.key_gaps:
                    gaps = app.gaps_list
                    if gaps:
                        st.markdown("**Key Gaps:**")
                        for g in gaps:
                            st.markdown(f"- {g}")

                # Score reasoning
                if app.score_reasoning:
                    st.markdown(f"**Analysis:** {app.score_reasoning}")

                # Cover letter
                if app.cover_letter:
                    st.markdown("---")
                    st.markdown("**Cover Letter:**")
                    st.text_area(
                        "Cover Letter",
                        app.cover_letter,
                        height=300,
                        key=f"cl_{app.id}",
                        label_visibility="collapsed",
                    )

                # Resume tweaks
                if app.resume_tweaks_json:
                    st.markdown("---")
                    st.markdown("**Resume Tweaks:**")
                    try:
                        tweaks = json.loads(app.resume_tweaks_json)
                        st.json(tweaks)
                    except json.JSONDecodeError:
                        st.text(app.resume_tweaks_json)
    else:
        st.info(
            "No scored jobs yet. Go to **🚀 Run Search** to start your job search!"
        )

    # Recent activity
    st.divider()
    st.subheader("Recent Activity")

    recent = sorted(
        all_apps,
        key=lambda x: x.updated_at or x.created_at or _EPOCH,
        reverse=True,
    )[:5]
    if recent:
        for app in recent:
            ts = app.updated_at or app.created_at
            st.markdown(
                f"- **{app.company}** — {app.job_title} | "
                f"Status: `{app.status}` | "
                f"Updated: {ts.strftime('%b %d, %Y') if ts else 'N/A'}"
            )
    else:
        st.caption("No activity yet.")

# ── Run Search Page ───────────────────────────────────────────────────────

elif page == "🚀 Run Search":
    st.title("Run Job Search Pipeline")

    # LLM status
    llm = _get_llm()
    _llm_status_badge(llm)

    st.markdown(
        """
        **Pipeline stages:**
        1. 🔍 **Search** — Scrape 5+ job boards (always works)
        2. 📊 **Score** — Rate each job against your resume (basic or AI)
        3. ✨ **Enhance** *(AI only)* — Resume tweaks, cover letters, company intel
        """
    )

    st.divider()

    # Configuration
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Search Parameters")
        roles = st.text_area(
            "Target Roles (one per line)",
            value=(
                "data platform engineer\n"
                "analytics engineer\n"
                "senior data engineer\n"
                "staff data engineer\n"
                "manager data engineering\n"
                "head of data\n"
                "founding data engineer"
            ),
            height=200,
        )
        keywords = st.text_input("Keyword Searches", value="dbt, Trino, lakehouse")
        locations_input = st.text_input("Locations", value="Los Angeles, CA; Remote")

    with col2:
        st.subheader("Filters")
        max_days = st.slider("Posted within (days)", 1, 30, 14)
        include_remote = st.checkbox("Include Remote", value=True)

    st.divider()

    # Resume check
    knowledge_dir = os.path.join(_PROJECT_ROOT, "knowledge")
    resume_files = []
    if os.path.exists(knowledge_dir):
        resume_files = [f for f in os.listdir(knowledge_dir) if f.lower().endswith(".pdf")]

    if resume_files:
        st.success(f"📄 Resume found: `{resume_files[0]}`")
    else:
        st.warning("No resume PDF found in `knowledge/` directory.")
        uploaded = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
        if uploaded:
            os.makedirs(knowledge_dir, exist_ok=True)
            save_path = os.path.join(knowledge_dir, uploaded.name)
            with open(save_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.success(f"Resume saved: `{uploaded.name}`")
            st.rerun()

    st.divider()

    # Parse inputs
    role_list = [r.strip() for r in roles.strip().split("\n") if r.strip()]
    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    location_list = [loc.strip() for loc in locations_input.split(";") if loc.strip()]

    # Run buttons
    col1, col2, col3 = st.columns(3)

    with col1:
        search_only = st.button("🔍 Search Only", use_container_width=True, type="secondary")

    with col2:
        search_score = st.button("📊 Search + Score", use_container_width=True, type="secondary")

    with col3:
        ai_available = llm.is_configured
        full_pipeline = st.button(
            "✨ Full AI Pipeline",
            use_container_width=True,
            type="primary",
            disabled=not ai_available,
            help="Requires an LLM provider. Configure in Settings." if not ai_available else None,
        )

    if search_only or search_score or full_pipeline:
        if not role_list or not location_list:
            st.error("Please enter at least one role and one location.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            use_ai = full_pipeline and ai_available
            pipeline = JobFinderPipeline(llm=llm if use_ai else None)

            _step = [0]  # mutable container for closure
            total_steps = len(role_list) * len(location_list) + len(kw_list) * len(location_list)
            if search_score or full_pipeline:
                total_steps += 10  # scoring + enhancement steps

            def update_progress(msg: str):
                _step[0] += 1
                pct = min(_step[0] / max(total_steps, 1), 0.99)
                progress_bar.progress(pct, text=msg)
                status_text.text(msg)

            if search_only:
                # Search only — no scoring
                with st.spinner("Searching job boards..."):
                    jobs = pipeline.search_all_jobs(
                        roles=role_list,
                        locations=location_list,
                        progress=update_progress,
                    )

                    # Save to DB
                    saved = 0
                    for job in jobs:
                        rec = save_application(
                            job_title=job.get("title", ""),
                            company=job.get("company", ""),
                            location=job.get("location", ""),
                            job_url=job.get("url", ""),
                            source=job.get("source", ""),
                            description=job.get("description", ""),
                            is_remote=job.get("is_remote", False),
                            salary_min=job.get("salary_min"),
                            salary_max=job.get("salary_max"),
                        )
                        if rec:
                            saved += 1

                    progress_bar.progress(1.0, text="Complete!")
                    st.success(f"Found {len(jobs)} unique jobs! ({saved} new saved)")
                    st.balloons()

            else:
                # Search + Score (basic or AI) + optional enhancement
                with st.spinner("Running pipeline..." if not use_ai else "Running full AI pipeline..."):
                    try:
                        jobs = pipeline.run_full_pipeline(
                            progress=update_progress,
                            roles=role_list,
                            locations=location_list,
                            use_ai=use_ai,
                        )

                        progress_bar.progress(1.0, text="Complete!")
                        scored = len([j for j in jobs if j.get("overall_score")])
                        strong = len([j for j in jobs if j.get("recommendation") in ("STRONG_APPLY", "APPLY")])
                        st.success(
                            f"Done! {len(jobs)} jobs found, {scored} scored, "
                            f"{strong} strong matches."
                        )
                        st.balloons()
                    except Exception as e:
                        st.error(f"Pipeline error: {e}")
                        st.exception(e)


# ── All Applications Page ─────────────────────────────────────────────────

elif page == "📋 All Applications":
    st.title("Application Tracker")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All"] + _STATUS_OPTIONS,
        )
    with col2:
        min_score_filter = st.slider("Min Score", 0, 100, 0)
    with col3:
        recommendation_filter = st.selectbox(
            "Recommendation",
            ["All", "STRONG_APPLY", "APPLY", "MAYBE", "SKIP"],
        )

    # Get filtered data
    apps = get_all_applications(
        status=status_filter if status_filter != "All" else None,
        min_score=min_score_filter if min_score_filter > 0 else None,
    )

    if recommendation_filter != "All":
        apps = [a for a in apps if a.recommendation == recommendation_filter]

    st.caption(f"Showing {len(apps)} applications")

    if apps:
        # Convert to DataFrame for display
        df_data = []
        for app in apps:
            df_data.append(
                {
                    "ID": app.id,
                    "Company": app.company,
                    "Title": app.job_title,
                    "Location": app.location,
                    "Score": f"{app.overall_score:.0f}" if app.overall_score else "-",
                    "Recommendation": app.recommendation or "-",
                    "Status": app.status,
                    "Source": app.source,
                    "Salary": (
                        f"${app.salary_min:,.0f}-${app.salary_max:,.0f}"
                        if app.salary_min and app.salary_max
                        else "-"
                    ),
                    "Found": app.date_found.strftime("%m/%d") if app.date_found else "-",
                }
            )

        df = pd.DataFrame(df_data)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score": st.column_config.TextColumn("Score", width="small"),
                "Company": st.column_config.TextColumn("Company", width="medium"),
            },
        )

        # CSV export
        st.divider()
        st.subheader("Bulk Actions")
        st.download_button(
            "Export to CSV",
            df.to_csv(index=False),
            "job_applications.csv",
            "text/csv",
        )
    else:
        st.info("No applications match your filters.")

    # Manual add
    st.divider()
    st.subheader("Manually Add Application")
    with st.form("add_app_form"):
        col1, col2 = st.columns(2)
        with col1:
            new_title = st.text_input("Job Title")
            new_company = st.text_input("Company")
            new_location = st.text_input("Location")
        with col2:
            new_url = st.text_input("Job URL")
            new_source = st.text_input("Source")
            new_notes = st.text_area("Notes")

        if st.form_submit_button("Add Application"):
            if new_title and new_company:
                save_application(
                    job_title=new_title,
                    company=new_company,
                    location=new_location,
                    job_url=new_url,
                    source=new_source,
                    notes=new_notes,
                )
                st.success(f"Added: {new_company} - {new_title}")
                st.rerun()
            else:
                st.error("Title and Company are required.")

# ── Analytics Page ────────────────────────────────────────────────────────

elif page == "📊 Analytics":
    import plotly.express as px
    import plotly.graph_objects as go

    st.title("Search Analytics")

    if all_apps:
        scored_apps = [a for a in all_apps if a.overall_score]
        if scored_apps:
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Score Distribution")
                scores = [a.overall_score for a in scored_apps]
                fig = px.histogram(
                    x=scores,
                    nbins=20,
                    labels={"x": "Overall Score", "y": "Count"},
                    color_discrete_sequence=["#FF6B35"],
                )
                fig.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Recommendations Breakdown")
                rec_counts = {}
                for a in scored_apps:
                    rec = a.recommendation or "UNSCORED"
                    rec_counts[rec] = rec_counts.get(rec, 0) + 1

                fig = px.pie(
                    values=list(rec_counts.values()),
                    names=list(rec_counts.keys()),
                    color_discrete_sequence=["#00c853", "#4caf50", "#ff9800", "#f44336"],
                    hole=0.4,
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)

        # Status pipeline
        st.subheader("Application Pipeline")
        status_counts = {}
        for a in all_apps:
            s = a.status or "unknown"
            status_counts[s] = status_counts.get(s, 0) + 1

        ordered_counts = {
            s: status_counts.get(s, 0) for s in _STATUS_OPTIONS if s in status_counts
        }

        if ordered_counts:
            fig = go.Figure(
                data=[
                    go.Funnel(
                        y=list(ordered_counts.keys()),
                        x=list(ordered_counts.values()),
                        textinfo="value+percent initial",
                        marker={
                            "color": [
                                "#2196f3", "#03a9f4", "#00bcd4", "#009688",
                                "#4caf50", "#8bc34a", "#f44336", "#9e9e9e",
                            ][:len(ordered_counts)]
                        },
                    )
                ]
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)

        # Source and company charts
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Jobs by Source")
            source_counts = {}
            for a in all_apps:
                s = a.source or "Unknown"
                source_counts[s] = source_counts.get(s, 0) + 1

            fig = px.bar(
                x=list(source_counts.keys()),
                y=list(source_counts.values()),
                labels={"x": "Source", "y": "Count"},
                color_discrete_sequence=["#FF6B35"],
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.subheader("Top Companies by Score")
            if scored_apps:
                company_scores = {}
                for a in scored_apps:
                    if a.company not in company_scores or a.overall_score > company_scores[a.company]:
                        company_scores[a.company] = a.overall_score

                sorted_companies = sorted(
                    company_scores.items(), key=lambda x: x[1], reverse=True
                )[:15]

                fig = px.bar(
                    x=[c[1] for c in sorted_companies],
                    y=[c[0] for c in sorted_companies],
                    orientation="h",
                    labels={"x": "Score", "y": "Company"},
                    color_discrete_sequence=["#4caf50"],
                )
                fig.update_layout(showlegend=False, height=350, yaxis={"autorange": "reversed"})
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data yet. Run a search first!")

# ── Settings Page ─────────────────────────────────────────────────────────

elif page == "⚙️ Settings":
    st.title("Settings")

    # ── LLM Provider Configuration ──
    st.subheader("🤖 LLM Provider")
    st.markdown(
        "Configure which AI provider powers smart scoring, cover letters, "
        "and resume optimization. **Search and basic scoring work without any LLM.**"
    )

    # Current status
    llm = _get_llm()
    _llm_status_badge(llm)

    st.divider()

    # Provider selection
    provider_options = {
        "": "None (basic scoring only)",
        "claude-proxy": "🟣 Claude Proxy (CLIProxyAPI) — use your Claude Max subscription",
        "claude-proxy-alt": "🟣 Claude Proxy (claude-max-api-proxy) — alternative proxy",
        "openai-proxy": "🟢 OpenAI Proxy (Codex) — use your ChatGPT subscription",
        "anthropic-api": "🟣 Anthropic API — pay-per-use ($0.50-2/run)",
        "openai-api": "🟢 OpenAI API — pay-per-use",
        "gemini": "🔵 Google Gemini — free tier (250 req/day)",
        "ollama": "⚪ Ollama — local models, free",
    }

    current_provider = os.getenv("LLM_PROVIDER", "")
    provider_keys = list(provider_options.keys())
    try:
        current_idx = provider_keys.index(current_provider)
    except ValueError:
        current_idx = 0

    selected_provider = st.selectbox(
        "Provider",
        provider_keys,
        index=current_idx,
        format_func=lambda k: provider_options.get(k, k),
    )

    # Dynamic fields based on provider
    preset = PRESETS.get(selected_provider, {})

    if selected_provider in ("anthropic-api", "openai-api", "gemini"):
        api_key = st.text_input(
            "API Key",
            value=os.getenv("LLM_API_KEY", ""),
            type="password",
            help="Required for pay-per-use providers",
        )
    else:
        api_key = preset.get("api_key", "not-needed")

    col1, col2 = st.columns(2)
    with col1:
        base_url = st.text_input(
            "Base URL",
            value=os.getenv("LLM_BASE_URL", "") or preset.get("base_url", ""),
            help="The API endpoint URL",
        )
    with col2:
        model = st.text_input(
            "Model",
            value=os.getenv("LLM_MODEL", "") or preset.get("model", ""),
            help="Model name to use",
        )

    # Save config
    if st.button("💾 Save & Test Connection", type="primary"):
        env_path = os.path.join(_PROJECT_ROOT, ".env")
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        # Update or add env vars
        env_vars = {
            "LLM_PROVIDER": selected_provider,
            "LLM_BASE_URL": base_url,
            "LLM_API_KEY": api_key,
            "LLM_MODEL": model,
        }

        for key, val in env_vars.items():
            found = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f"{key}=") or line.strip().startswith(f"# {key}="):
                    lines[i] = f"{key}={val}\n"
                    found = True
                    break
            if not found:
                lines.append(f"{key}={val}\n")

        with open(env_path, "w") as f:
            f.writelines(lines)

        # Set env vars for current session
        for key, val in env_vars.items():
            os.environ[key] = val

        # Test connection
        test_llm = LLMClient(
            provider=selected_provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        if not selected_provider:
            st.info("No provider selected. Basic scoring mode active.")
        elif test_llm.is_available():
            st.success(f"✅ Connected to {model}!")
        else:
            st.warning(
                f"⚠️ Config saved but could not reach {base_url}. "
                "Make sure the proxy is running."
            )

    # Setup instructions
    st.divider()
    st.subheader("📖 Provider Setup Guides")

    with st.expander("🟣 Claude Proxy (CLIProxyAPI) — use your $200/mo Max plan"):
        st.markdown("""
**Prerequisites:** Claude Max subscription, macOS or Linux

```bash
# 1. Install
brew install cliproxyapi

# 2. Authenticate (opens browser)
cli-proxy-api --claude-login

# 3. Start the proxy
brew services start cliproxyapi
# Runs on http://localhost:8317
```

Then select **Claude Proxy** above and click Save & Test.
""")

    with st.expander("🟢 OpenAI Proxy (Codex) — use your ChatGPT Plus plan"):
        st.markdown("""
**Prerequisites:** ChatGPT Plus/Pro subscription, Node.js

```bash
# 1. Install Codex CLI
npm install -g @openai/codex

# 2. Install the proxy
# See: github.com/Securiteru/codex-openai-proxy

# 3. Start and point to localhost:3457
```
""")

    with st.expander("🔵 Google Gemini — free, no credit card"):
        st.markdown("""
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **"Get API Key"**
3. Create a key (takes 30 seconds)
4. Paste it above and select **Gemini**

Free tier: 250 requests/day with Gemini 2.5 Flash.
""")

    with st.expander("⚪ Ollama — local models, completely free"):
        st.markdown("""
```bash
# 1. Install
brew install ollama

# 2. Pull a model
ollama pull llama3.1

# 3. Ollama runs automatically on localhost:11434
```

Then select **Ollama** above and click Save & Test.
""")

    st.divider()

    # ── Resume ──
    st.subheader("📄 Resume")
    knowledge_dir = os.path.join(_PROJECT_ROOT, "knowledge")
    if os.path.exists(knowledge_dir):
        pdfs = [f for f in os.listdir(knowledge_dir) if f.lower().endswith(".pdf")]
        if pdfs:
            st.success(f"Resume loaded: `{pdfs[0]}`")
        else:
            st.warning("No resume PDF in knowledge/ directory")
    else:
        st.warning("knowledge/ directory not found")

    uploaded = st.file_uploader("Upload/Replace Resume (PDF)", type=["pdf"])
    if uploaded:
        os.makedirs(knowledge_dir, exist_ok=True)
        save_path = os.path.join(knowledge_dir, uploaded.name)
        with open(save_path, "wb") as f:
            f.write(uploaded.getbuffer())
        st.success(f"Resume saved: `{uploaded.name}`")

    st.divider()

    # ── Database ──
    st.subheader("💾 Database")
    if os.path.exists(DB_PATH):
        size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
        st.markdown(f"- **Path**: `{DB_PATH}`")
        st.markdown(f"- **Size**: `{size_mb:.2f} MB`")
        st.markdown(f"- **Records**: `{len(all_apps)}`")
    else:
        st.info("Database will be created on first run.")

    st.divider()

    # ── Search Config ──
    st.subheader("🔧 Search Configuration")
    config_path = os.path.join(
        _PROJECT_ROOT, "src", "job_finder", "config", "search_config.yaml",
    )
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            st.code(f.read(), language="yaml")
    else:
        st.warning("search_config.yaml not found")
