"""Streamlit UI for the Job Finder pipeline."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
from streamlit_option_menu import option_menu

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
    backfill_company_types,
)
from job_finder.company_classifier import classify_company, COMPANY_TYPES
from job_finder.pipeline import JobFinderPipeline, _load_search_config
from components import (
    STATUS_OPTIONS,
    recommendation_badge,
    status_badge,
    remote_badge,
    salary_badge,
    funding_badge,
    is_remote_job,
    company_info_line,
    score_color_class,
    format_date,
    render_job_card,
    render_activity_item,
    render_empty_state,
    render_pipeline_steps,
    render_connection_badge,
    company_type_badge,
)

# Initialize database
init_db()

# One-time backfill of company types for existing records
if "company_types_backfilled" not in st.session_state:
    backfill_company_types()
    st.session_state["company_types_backfilled"] = True

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


def _list_profiles() -> list[str]:
    profiles_dir = os.path.join(
        os.path.dirname(__file__), "src", "job_finder", "config", "profiles"
    )
    names = ["default"]
    if os.path.isdir(profiles_dir):
        for f in sorted(os.listdir(profiles_dir)):
            if f.endswith(".yaml") and not f.startswith("_"):
                names.append(f.replace(".yaml", ""))
    return names


def _get_llm() -> LLMClient:
    return LLMClient()


def _find_profile_resume(profile_name: str) -> str | None:
    knowledge_dir = os.path.join(_PROJECT_ROOT, "knowledge")
    if not os.path.exists(knowledge_dir):
        return None
    profile_file = f"{profile_name}_resume.pdf"
    if os.path.exists(os.path.join(knowledge_dir, profile_file)):
        return profile_file
    pdfs = [f for f in os.listdir(knowledge_dir) if f.lower().endswith(".pdf")]
    if not pdfs:
        return None
    resume_pdfs = [f for f in pdfs if "resume" in f.lower()]
    return resume_pdfs[0] if resume_pdfs else pdfs[0]


def _profile_resume_filename(profile_name: str) -> str:
    return f"{profile_name}_resume.pdf"


# ==========================================================================
# Page Config
# ==========================================================================

st.set_page_config(
    page_title="Gig AI - Job Search Pipeline",
    page_icon="G",
    layout="wide",
    initial_sidebar_state="expanded",
)

_css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
if os.path.exists(_css_path):
    with open(_css_path) as _css_file:
        st.markdown(f"<style>{_css_file.read()}</style>", unsafe_allow_html=True)

# ==========================================================================
# Sidebar
# ==========================================================================

with st.sidebar:
    st.title("Gig AI")

    # Profile selector
    available_profiles = _list_profiles()
    active_profile = st.selectbox(
        "Profile",
        available_profiles,
        index=0,
        help="Each profile has its own roles, keywords, and scoring weights",
    )
    _active_cfg = _load_search_config(
        active_profile if active_profile != "default" else None
    )
    _profile_display = _active_cfg.get("profile", {}).get("name", active_profile)

    st.divider()

    # Icon-based navigation
    page = option_menu(
        menu_title=None,
        options=["Dashboard", "Run Search", "Applications", "Analytics", "Settings"],
        icons=["speedometer2", "search", "list-task", "graph-up", "gear"],
        default_index=0,
        styles={
            "container": {"padding": "0"},
            "icon": {"font-size": "0.9rem"},
            "nav-link": {
                "font-size": "0.88rem",
                "padding": "8px 12px",
                "margin": "2px 0",
                "border-radius": "6px",
            },
            "nav-link-selected": {
                "background-color": "#EEF2FF",
                "color": "#4F46E5",
                "font-weight": "600",
            },
        },
    )

    st.divider()

    # Compact sidebar stats
    _profile_filter = active_profile if active_profile != "default" else None
    all_apps = get_all_applications(profile=_profile_filter)
    total = len(all_apps)
    strong_apply = len([a for a in all_apps if a.recommendation == "STRONG_APPLY"])
    applied = len([a for a in all_apps if a.status == "applied"])
    interviewing = len([a for a in all_apps if a.status == "interviewing"])

    st.markdown(
        f'<div class="sidebar-stats">'
        f'<strong>{total}</strong> jobs &middot; '
        f'<strong>{strong_apply}</strong> strong &middot; '
        f'<strong>{applied}</strong> applied &middot; '
        f'<strong>{interviewing}</strong> interviewing'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.divider()

    # LLM status (compact)
    llm = _get_llm()
    render_connection_badge(llm)

# ==========================================================================
# Dashboard
# ==========================================================================

if page == "Dashboard":
    st.title("Job Search Command Center")
    if active_profile != "default":
        st.caption(f"Profile: {_profile_display}")

    # Top metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Found", total)
    col2.metric("Strong Matches", strong_apply)
    col3.metric("Applied", applied)
    col4.metric("Interviewing", interviewing)

    st.divider()

    # Top opportunities — card layout
    st.subheader("Top Opportunities")

    # Filters row
    dcol1, dcol2 = st.columns([3, 1])
    with dcol1:
        dash_type_filter = st.selectbox(
            "Company Type",
            ["All"] + COMPANY_TYPES,
            key="dash_type_filter",
        )
    with dcol2:
        dash_remote_only = st.checkbox("Remote only", key="dash_remote_only")

    strong_apps = [
        a for a in all_apps
        if a.recommendation in ("STRONG_APPLY", "APPLY") and a.overall_score
    ]
    if dash_type_filter != "All":
        strong_apps = [a for a in strong_apps if getattr(a, "company_type", "") == dash_type_filter]
    if dash_remote_only:
        strong_apps = [a for a in strong_apps if is_remote_job(a)]
    strong_apps.sort(key=lambda x: x.overall_score or 0, reverse=True)

    _DASH_LIMIT = 10
    if strong_apps:
        for app in strong_apps[:_DASH_LIMIT]:
            render_job_card(app, key_prefix="dash_")
        # Show count so user knows if there are more
        if len(strong_apps) > _DASH_LIMIT:
            st.caption(
                f"Showing top {_DASH_LIMIT} of {len(strong_apps)} matches. "
                f"Go to **Applications** to see all."
            )
        else:
            st.caption(f"{len(strong_apps)} match{'es' if len(strong_apps) != 1 else ''}")
    else:
        render_empty_state(
            "&#128269;",
            "No scored jobs yet",
            "Go to Run Search to start your job search pipeline.",
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
            render_activity_item(app)
    else:
        render_empty_state(
            "&#128338;",
            "No activity yet",
            "Your recent job search activity will appear here.",
        )

# ==========================================================================
# Run Search
# ==========================================================================

elif page == "Run Search":
    st.title("Run Job Search Pipeline")

    # Pipeline visualization
    llm = _get_llm()
    ai_available = llm.is_configured
    render_pipeline_steps(ai_available)

    if not ai_available:
        st.caption("Full pipeline requires a connected LLM provider. Configure in Settings.")

    st.divider()

    # Search form — prevents reruns on every keystroke
    _default_roles = _active_cfg.get("target_roles", [
        "data platform engineer", "analytics engineer", "senior data engineer",
        "staff data engineer", "manager data engineering", "head of data",
        "founding data engineer",
    ])
    _default_kw = _active_cfg.get("keyword_searches", ["dbt", "Trino", "lakehouse"])
    _default_locs = _active_cfg.get("locations", ["Los Angeles, CA", "Remote"])
    _default_days = _active_cfg.get("search_settings", {}).get("max_days_old", 14)

    with st.form("search_form"):
        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**Search Parameters** &mdash; {_profile_display}")
            roles = st.text_area(
                "Target Roles (one per line)",
                value="\n".join(_default_roles),
                height=180,
            )
            keywords = st.text_area(
                "Keywords (one per line)",
                value="\n".join(_default_kw),
                height=80,
            )

        with col2:
            st.markdown("**Locations & Filters**")
            locations_input = st.text_area(
                "Locations (one per line)",
                value="\n".join(_default_locs),
                height=80,
            )
            max_days = st.slider("Posted within (days)", 1, 30, _default_days)
            include_remote = st.checkbox("Include Remote", value=True)

        # Resume status inline
        knowledge_dir = os.path.join(_PROJECT_ROOT, "knowledge")
        profile_resume = _find_profile_resume(active_profile)
        if profile_resume:
            st.success(f"Resume: `{profile_resume}`")
        else:
            st.warning(f"No resume for '{_profile_display}'. Upload in Settings > Resume.")

        # Button row
        st.divider()
        bcol1, bcol2, bcol3 = st.columns(3)
        with bcol1:
            search_only = st.form_submit_button(
                "Search Only", use_container_width=True
            )
        with bcol2:
            search_score = st.form_submit_button(
                "Search + Score", use_container_width=True
            )
        with bcol3:
            full_pipeline = st.form_submit_button(
                "Full AI Pipeline",
                use_container_width=True,
                type="primary",
                disabled=not ai_available,
            )

    # Execute pipeline
    if search_only or search_score or full_pipeline:
        role_list = [r.strip() for r in roles.strip().split("\n") if r.strip()]
        kw_list = [k.strip() for k in keywords.strip().split("\n") if k.strip()]
        location_list = [loc.strip() for loc in locations_input.strip().split("\n") if loc.strip()]

        # "Include Remote" adds a Remote search alongside city searches (OR logic)
        if include_remote and not any(loc.lower() == "remote" for loc in location_list):
            location_list.append("Remote")

        if not role_list or not location_list:
            st.error("Please enter at least one role and one location.")
        else:
            progress_bar = st.progress(0)
            status_text = st.empty()

            use_ai = full_pipeline and ai_available
            _prof = active_profile if active_profile != "default" else None
            pipeline = JobFinderPipeline(llm=llm if use_ai else None, profile=_prof)

            _step = [0]
            total_steps = len(role_list) * len(location_list) + len(kw_list) * len(location_list)
            if search_score or full_pipeline:
                total_steps += 10

            def update_progress(msg: str):
                _step[0] += 1
                pct = min(_step[0] / max(total_steps, 1), 0.99)
                progress_bar.progress(pct, text=msg)
                status_text.text(msg)

            if search_only:
                with st.spinner("Searching job boards..."):
                    jobs = pipeline.search_all_jobs(
                        roles=role_list,
                        locations=location_list,
                        progress=update_progress,
                    )
                    saved = 0
                    for job in jobs:
                        ct = classify_company(job.get("company", ""))
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
                            company_type=ct,
                            profile=active_profile,
                        )
                        if rec:
                            saved += 1
                    progress_bar.progress(1.0, text="Complete!")
                    st.toast(f"Found {len(jobs)} jobs! ({saved} new)")
                    st.success(f"Found {len(jobs)} unique jobs! ({saved} new saved)")
            else:
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
                        st.toast(f"Done! {scored} scored, {strong} strong matches.")
                        st.success(
                            f"Done! {len(jobs)} jobs found, {scored} scored, "
                            f"{strong} strong matches."
                        )
                    except Exception as e:
                        st.error(f"Pipeline error: {e}")
                        st.exception(e)

# ==========================================================================
# All Applications
# ==========================================================================

elif page == "Applications":
    st.title("Application Tracker")

    # Filters row
    fcol1, fcol2, fcol3, fcol4, fcol5, fcol6 = st.columns([2, 2, 2, 2, 1, 1])
    with fcol1:
        status_filter = st.selectbox(
            "Status", ["All"] + STATUS_OPTIONS, key="app_status_filter"
        )
    with fcol2:
        recommendation_filter = st.selectbox(
            "Recommendation",
            ["All", "STRONG_APPLY", "APPLY", "MAYBE", "SKIP"],
            key="app_rec_filter",
        )
    with fcol3:
        app_type_filter = st.selectbox(
            "Company Type",
            ["All"] + COMPANY_TYPES,
            key="app_type_filter",
        )
    with fcol4:
        sort_by = st.selectbox(
            "Sort by",
            ["Score (High-Low)", "Date (Recent)", "Company (A-Z)"],
            key="app_sort",
        )
    with fcol5:
        min_score_filter = st.number_input("Min Score", 0, 100, 0, key="app_min_score")
    with fcol6:
        remote_only = st.checkbox("Remote only", key="app_remote_only")

    # Get filtered data
    apps = get_all_applications(
        status=status_filter if status_filter != "All" else None,
        min_score=min_score_filter if min_score_filter > 0 else None,
        profile=_profile_filter,
        company_type=app_type_filter if app_type_filter != "All" else None,
    )
    if recommendation_filter != "All":
        apps = [a for a in apps if a.recommendation == recommendation_filter]
    if remote_only:
        apps = [a for a in apps if is_remote_job(a)]

    # Sort
    if sort_by == "Score (High-Low)":
        apps.sort(key=lambda a: a.overall_score or 0, reverse=True)
    elif sort_by == "Date (Recent)":
        apps.sort(key=lambda a: a.updated_at or a.created_at or _EPOCH, reverse=True)
    elif sort_by == "Company (A-Z)":
        apps.sort(key=lambda a: (a.company or "").lower())

    # View toggle and count
    vcol1, vcol2, vcol3 = st.columns([4, 1, 1])
    with vcol1:
        st.caption(f"Showing {len(apps)} applications")
    with vcol2:
        view_mode = st.radio(
            "View",
            ["Cards", "Table"],
            horizontal=True,
            key="app_view_mode",
            label_visibility="collapsed",
        )

    if apps:
        if view_mode == "Cards":
            # Card view — same expandable cards as Dashboard
            for app_item in apps[:50]:  # cap at 50 for performance
                render_job_card(app_item, key_prefix="apps_")
            if len(apps) > 50:
                st.info(f"Showing 50 of {len(apps)} results. Use filters to narrow down.")
        else:
            # Table view
            df_data = []
            for app_item in apps:
                remote = is_remote_job(app_item)
                df_data.append({
                    "Company": app_item.company,
                    "Title": app_item.job_title,
                    "Type": getattr(app_item, "company_type", "") or "Unknown",
                    "Score": app_item.overall_score or 0,
                    "Recommendation": app_item.recommendation or "-",
                    "Status": app_item.status or "found",
                    "Remote": "Yes" if remote else "",
                    "Salary": (
                        f"${app_item.salary_min:,.0f}-${app_item.salary_max:,.0f}"
                        if app_item.salary_min and app_item.salary_max else ""
                    ),
                    "Source": app_item.source or "",
                    "Found": format_date(app_item.date_found, "short"),
                    "URL": app_item.job_url or "",
                })

            df = pd.DataFrame(df_data)

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Score": st.column_config.ProgressColumn(
                        "Score", min_value=0, max_value=100, format="%d"
                    ),
                    "URL": st.column_config.LinkColumn("URL", display_text="View"),
                    "Company": st.column_config.TextColumn("Company", width="medium"),
                    "Title": st.column_config.TextColumn("Title", width="large"),
                },
            )

        # Bulk actions row
        st.divider()
        acol1, acol2, acol3 = st.columns([1, 1, 4])
        with acol1:
            if st.button("Add Application"):
                st.session_state["show_add_dialog"] = True
        with acol2:
            # Build CSV for export regardless of view mode
            export_data = []
            for app_item in apps:
                export_data.append({
                    "Company": app_item.company,
                    "Title": app_item.job_title,
                    "Score": app_item.overall_score or 0,
                    "Recommendation": app_item.recommendation or "-",
                    "Status": app_item.status or "found",
                    "URL": app_item.job_url or "",
                })
            export_df = pd.DataFrame(export_data)
            st.download_button(
                "Export CSV",
                export_df.to_csv(index=False),
                "job_applications.csv",
                "text/csv",
            )
    else:
        render_empty_state(
            "&#128203;",
            "No applications match your filters",
            "Try adjusting your filter criteria or run a new search.",
        )

    # Manual add dialog
    if st.session_state.get("show_add_dialog"):
        @st.dialog("Add Application")
        def add_app_dialog():
            new_title = st.text_input("Job Title")
            new_company = st.text_input("Company")
            new_location = st.text_input("Location")
            new_url = st.text_input("Job URL")
            new_source = st.text_input("Source")
            new_notes = st.text_area("Notes", height=80)

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Save", type="primary", use_container_width=True):
                    if new_title and new_company:
                        save_application(
                            job_title=new_title,
                            company=new_company,
                            location=new_location,
                            job_url=new_url,
                            source=new_source,
                            notes=new_notes,
                            profile=active_profile,
                        )
                        st.toast(f"Added: {new_company} - {new_title}")
                        st.session_state["show_add_dialog"] = False
                        st.rerun()
                    else:
                        st.error("Title and Company are required.")
            with col2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state["show_add_dialog"] = False
                    st.rerun()

        add_app_dialog()

# ==========================================================================
# Analytics
# ==========================================================================

elif page == "Analytics":
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

                # Get thresholds from profile config
                _thresholds = _active_cfg.get("scoring", {}).get("thresholds", {})
                _t_strong = _thresholds.get("strong_apply", 70)
                _t_apply = _thresholds.get("apply", 55)
                _t_maybe = _thresholds.get("maybe", 40)

                fig = px.histogram(
                    x=scores,
                    nbins=20,
                    labels={"x": "Overall Score", "y": "Count"},
                    color_discrete_sequence=["#4F46E5"],
                )
                # Threshold lines
                for val, label, color in [
                    (_t_strong, "Strong", "#10B981"),
                    (_t_apply, "Apply", "#3B82F6"),
                    (_t_maybe, "Maybe", "#F59E0B"),
                ]:
                    fig.add_vline(
                        x=val, line_dash="dash", line_color=color, line_width=1.5,
                        annotation_text=label, annotation_position="top",
                        annotation_font_color=color, annotation_font_size=11,
                    )
                fig.update_layout(
                    showlegend=False, height=400,
                    plot_bgcolor="#FFFFFF", paper_bgcolor="#FAFAFA",
                    margin=dict(t=40),
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.subheader("Recommendations")
                rec_order = ["STRONG_APPLY", "APPLY", "MAYBE", "SKIP"]
                rec_colors = {
                    "STRONG_APPLY": "#10B981",
                    "APPLY": "#3B82F6",
                    "MAYBE": "#F59E0B",
                    "SKIP": "#EF4444",
                }
                rec_counts = {}
                for a in scored_apps:
                    rec = a.recommendation or "SKIP"
                    rec_counts[rec] = rec_counts.get(rec, 0) + 1

                # Horizontal bar chart
                labels = [r for r in rec_order if r in rec_counts]
                values = [rec_counts[r] for r in labels]
                colors = [rec_colors.get(r, "#94A3B8") for r in labels]

                fig = go.Figure(go.Bar(
                    x=values,
                    y=labels,
                    orientation="h",
                    marker_color=colors,
                    text=values,
                    textposition="auto",
                ))
                fig.update_layout(
                    height=400,
                    plot_bgcolor="#FFFFFF", paper_bgcolor="#FAFAFA",
                    yaxis={"autorange": "reversed"},
                    showlegend=False,
                    margin=dict(t=40, l=120),
                )
                st.plotly_chart(fig, use_container_width=True)

        # Status pipeline funnel
        st.subheader("Application Pipeline")
        status_counts = {}
        for a in all_apps:
            s = a.status or "unknown"
            status_counts[s] = status_counts.get(s, 0) + 1

        ordered_counts = {
            s: status_counts.get(s, 0) for s in STATUS_OPTIONS if s in status_counts
        }

        if ordered_counts:
            fig = go.Figure(
                data=[go.Funnel(
                    y=list(ordered_counts.keys()),
                    x=list(ordered_counts.values()),
                    textinfo="value+percent initial",
                    marker={
                        "color": [
                            "#4F46E5", "#6366F1", "#818CF8", "#10B981",
                            "#34D399", "#F59E0B", "#EF4444", "#94A3B8",
                        ][:len(ordered_counts)]
                    },
                )]
            )
            fig.update_layout(
                height=400, paper_bgcolor="#FAFAFA",
                margin=dict(t=20),
            )
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
                color_discrete_sequence=["#4F46E5"],
            )
            fig.update_layout(
                showlegend=False, height=350,
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FAFAFA",
            )
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
                    color_discrete_sequence=["#10B981"],
                )
                fig.update_layout(
                    showlegend=False, height=350,
                    yaxis={"autorange": "reversed"},
                    plot_bgcolor="#FFFFFF", paper_bgcolor="#FAFAFA",
                )
                st.plotly_chart(fig, use_container_width=True)

        # Company Type breakdown
        st.subheader("Jobs by Company Type")
        type_counts = {}
        for a in all_apps:
            ct = getattr(a, "company_type", "") or "Unknown"
            type_counts[ct] = type_counts.get(ct, 0) + 1

        _type_colors = {
            "FAANG+": "#F59E0B", "Big Tech": "#3B82F6", "Elite Startup": "#6366F1",
            "Growth Stage": "#10B981", "Early Startup": "#34D399", "Midsize": "#94A3B8",
            "Enterprise": "#64748B", "Unknown": "#CBD5E1",
        }
        type_labels = [t for t in COMPANY_TYPES + ["Unknown"] if t in type_counts]
        type_values = [type_counts[t] for t in type_labels]
        type_bar_colors = [_type_colors.get(t, "#94A3B8") for t in type_labels]

        if type_labels:
            fig = go.Figure(go.Bar(
                x=type_values,
                y=type_labels,
                orientation="h",
                marker_color=type_bar_colors,
                text=type_values,
                textposition="auto",
            ))
            fig.update_layout(
                height=350,
                plot_bgcolor="#FFFFFF", paper_bgcolor="#FAFAFA",
                yaxis={"autorange": "reversed"},
                showlegend=False,
                margin=dict(t=20, l=120),
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        render_empty_state(
            "&#128200;",
            "No data yet",
            "Run a search first to see your analytics.",
        )

# ==========================================================================
# Settings
# ==========================================================================

elif page == "Settings":
    st.title("Settings")
    if active_profile != "default":
        st.caption(f"Profile: {_profile_display}")

    # Organized into tabs
    tab_llm, tab_profile, tab_resume, tab_database = st.tabs(
        ["LLM Provider", "Profile", "Resume", "Database"]
    )

    # -- LLM Provider Tab --
    with tab_llm:
        llm = _get_llm()

        # Connection status
        info = llm.get_provider_info()
        if not llm.is_configured:
            st.markdown(
                '<span class="conn-badge conn-badge-off">'
                '<span class="conn-dot conn-dot-off"></span> No LLM configured &mdash; basic scoring only</span>',
                unsafe_allow_html=True,
            )
        elif llm.is_available():
            st.markdown(
                f'<span class="conn-badge conn-badge-ok">'
                f'<span class="conn-dot conn-dot-ok"></span> '
                f'Connected to {info["model"]} via {info["label"]}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="conn-badge conn-badge-err">'
                f'<span class="conn-dot conn-dot-err"></span> '
                f'{info["label"]} &mdash; not reachable</span>',
                unsafe_allow_html=True,
            )

        st.divider()

        # Provider selection
        provider_options = {
            "": "None (basic scoring only)",
            "claude-proxy": "Claude Proxy (CLIProxyAPI)",
            "claude-proxy-alt": "Claude Proxy (claude-max-api-proxy)",
            "openai-proxy": "OpenAI Proxy (Codex)",
            "anthropic-api": "Anthropic API (pay-per-use)",
            "openai-api": "OpenAI API (pay-per-use)",
            "gemini": "Google Gemini (free tier)",
            "ollama": "Ollama (local)",
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

        preset = PRESETS.get(selected_provider, {})

        # API key for pay providers
        if selected_provider in ("anthropic-api", "openai-api", "gemini"):
            api_key = st.text_input(
                "API Key",
                value=os.getenv("LLM_API_KEY", ""),
                type="password",
            )
        else:
            api_key = preset.get("api_key", "not-needed")

        # Model dropdown with common options per provider
        _model_presets = {
            "claude-proxy": [
                "claude-sonnet-4-20250514", "claude-sonnet-4-6",
                "claude-opus-4-6", "claude-haiku-4-5-20251001",
            ],
            "claude-proxy-alt": [
                "claude-sonnet-4", "claude-opus-4", "claude-haiku-4-5",
            ],
            "anthropic-api": [
                "claude-sonnet-4-20250514", "claude-opus-4-6",
                "claude-haiku-4-5-20251001",
            ],
            "openai-api": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
            "openai-proxy": ["gpt-4o", "gpt-4o-mini"],
            "gemini": ["gemini-2.5-flash", "gemini-2.0-flash"],
            "ollama": ["llama3.1", "mistral", "codellama"],
        }

        available_models = _model_presets.get(selected_provider, [])
        current_model = os.getenv("LLM_MODEL", "") or preset.get("model", "")

        col1, col2 = st.columns(2)
        with col1:
            base_url = st.text_input(
                "Base URL",
                value=os.getenv("LLM_BASE_URL", "") or preset.get("base_url", ""),
            )
        with col2:
            if available_models:
                model_options = available_models + ["Custom..."]
                try:
                    model_idx = model_options.index(current_model)
                except ValueError:
                    model_idx = len(model_options) - 1  # Custom

                selected_model_option = st.selectbox(
                    "Model", model_options, index=model_idx
                )
                if selected_model_option == "Custom...":
                    model = st.text_input("Custom Model", value=current_model)
                else:
                    model = selected_model_option
            else:
                model = st.text_input(
                    "Model",
                    value=current_model,
                )

        if st.button("Save & Test Connection", type="primary"):
            env_path = os.path.join(_PROJECT_ROOT, ".env")
            lines = []
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()

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

            for key, val in env_vars.items():
                os.environ[key] = val

            test_llm = LLMClient(
                provider=selected_provider,
                base_url=base_url,
                api_key=api_key,
                model=model,
            )
            if not selected_provider:
                st.info("No provider selected. Basic scoring mode active.")
            elif test_llm.is_available():
                st.toast(f"Connected to {model}!")
                st.success(f"Connected to {model}!")
            else:
                st.warning(
                    f"Config saved but could not reach {base_url}. "
                    "Make sure the proxy is running."
                )

        # Setup guides (collapsed)
        with st.expander("Setup Guides"):
            guide_tabs = st.tabs(["CLIProxyAPI", "OpenAI Proxy", "Gemini", "Ollama"])

            with guide_tabs[0]:
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
""")
            with guide_tabs[1]:
                st.markdown("""
**Prerequisites:** ChatGPT Plus/Pro subscription, Node.js

```bash
# 1. Install Codex CLI
npm install -g @openai/codex

# 2. See: github.com/Securiteru/codex-openai-proxy

# 3. Start and point to localhost:3457
```
""")
            with guide_tabs[2]:
                st.markdown("""
1. Go to [aistudio.google.com](https://aistudio.google.com)
2. Click **"Get API Key"**
3. Create a key (takes 30 seconds)
4. Paste it above and select **Gemini**

Free tier: 250 requests/day with Gemini 2.5 Flash.
""")
            with guide_tabs[3]:
                st.markdown("""
```bash
# 1. Install
brew install ollama

# 2. Pull a model
ollama pull llama3.1

# 3. Ollama runs automatically on localhost:11434
```
""")

    # -- Profile Tab --
    with tab_profile:
        _prof_meta = _active_cfg.get("profile", {})
        _prof_name = _prof_meta.get("name", active_profile)
        _prof_desc = _prof_meta.get("description", "Default configuration")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Name:** {_prof_name}")
            st.markdown(f"**Description:** {_prof_desc}")
            _roles = _active_cfg.get("target_roles", [])
            st.markdown(f"**Target Roles:** {len(_roles)} configured")
        with col2:
            _comp = _active_cfg.get("compensation", {})
            _scoring = _active_cfg.get("scoring", {})
            _target_tc = _comp.get("target_total_comp", 300_000)
            _min_base = _comp.get("min_base", 190_000)
            st.markdown(f"**Target TC:** ${_target_tc:,.0f}")
            st.markdown(f"**Min Base:** ${_min_base:,.0f}")
            _thresh = _scoring.get("thresholds", {})
            st.markdown(
                f"**Thresholds:** Strong {_thresh.get('strong_apply', 70)} / "
                f"Apply {_thresh.get('apply', 55)} / "
                f"Maybe {_thresh.get('maybe', 40)}"
            )

        st.divider()
        st.caption(
            "Edit profile YAML files in `src/job_finder/config/profiles/` for full customization."
        )

        # Show config
        if active_profile != "default":
            config_path = os.path.join(
                _PROJECT_ROOT, "src", "job_finder", "config", "profiles",
                f"{active_profile}.yaml",
            )
        else:
            config_path = os.path.join(
                _PROJECT_ROOT, "src", "job_finder", "config", "search_config.yaml",
            )
        if os.path.exists(config_path):
            with st.expander(f"Raw Config ({os.path.basename(config_path)})"):
                with open(config_path, "r") as f:
                    st.code(f.read(), language="yaml")

    # -- Resume Tab --
    with tab_resume:
        knowledge_dir = os.path.join(_PROJECT_ROOT, "knowledge")
        profile_resume = _find_profile_resume(active_profile)

        if profile_resume:
            st.success(f"Resume loaded: `{profile_resume}`")
        else:
            st.warning(f"No resume for profile '{_profile_display}'")

        uploaded = st.file_uploader(
            f"Upload/Replace Resume for {_profile_display} (PDF)",
            type=["pdf"],
            key="settings_resume_upload",
        )
        if uploaded:
            os.makedirs(knowledge_dir, exist_ok=True)
            save_name = _profile_resume_filename(active_profile)
            save_path = os.path.join(knowledge_dir, save_name)
            with open(save_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.toast(f"Resume saved: {save_name}")
            st.success(f"Resume saved: `{save_name}`")

    # -- Database Tab --
    with tab_database:
        if os.path.exists(DB_PATH):
            size_mb = os.path.getsize(DB_PATH) / (1024 * 1024)
            dcol1, dcol2, dcol3 = st.columns(3)
            dcol1.metric("Records", len(all_apps))
            dcol2.metric("Size", f"{size_mb:.2f} MB")
            dcol3.metric("Path", os.path.basename(DB_PATH))

            with st.expander("Full Path"):
                st.code(DB_PATH)
        else:
            st.info("Database will be created on first run.")
