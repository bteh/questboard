"""Reusable UI components for Launchboard dashboard."""

from __future__ import annotations

import html as _html_mod
import json
import re
from datetime import datetime, timezone

import streamlit as st

from job_finder.models.database import update_application_status

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATUS_OPTIONS = [
    "found", "reviewed", "applying", "applied",
    "interviewing", "offer", "rejected", "withdrawn",
]

_STATUS_DOTS = {
    "found": "gray",
    "reviewed": "blue",
    "applying": "amber",
    "applied": "blue",
    "interviewing": "green",
    "offer": "green",
    "rejected": "gray",
    "withdrawn": "gray",
}

# ---------------------------------------------------------------------------
# Badge helpers
# ---------------------------------------------------------------------------

def recommendation_badge(rec: str) -> str:
    badge_map = {
        "STRONG_APPLY": "badge-strong-apply",
        "APPLY": "badge-apply",
        "MAYBE": "badge-maybe",
        "SKIP": "badge-skip",
    }
    css_class = badge_map.get(rec, "badge-skip")
    return f'<span class="{css_class}">{rec}</span>'


def status_badge(status: str) -> str:
    css = f"status-{status}" if status else "status-found"
    return f'<span class="status-badge {css}">{status}</span>'


def remote_badge() -> str:
    return '<span class="badge-remote">REMOTE</span>'


def salary_badge(sal_min: float | None, sal_max: float | None) -> str:
    if not sal_min and not sal_max:
        return ""
    lo = f"${sal_min:,.0f}" if sal_min else "?"
    hi = f"${sal_max:,.0f}" if sal_max else "?"
    return f'<span class="badge-salary">{lo}-{hi}</span>'


def funding_badge(app) -> str:
    info = company_info_line(app)
    if not info:
        return ""
    return f'<span class="badge-funding">{info}</span>'


_COMPANY_TYPE_CSS = {
    "FAANG+": "badge-faang",
    "Big Tech": "badge-bigtech",
    "Elite Startup": "badge-elite",
    "Growth Stage": "badge-growth",
    "Early Startup": "badge-early",
    "Midsize": "badge-midsize",
    "Enterprise": "badge-enterprise",
}

# Company avatar color palette — modern, muted, accessible on white text
_AVATAR_COLORS = [
    "#4F46E5", "#7C3AED", "#2563EB", "#0891B2", "#059669",
    "#D97706", "#DC2626", "#DB2777", "#9333EA", "#0D9488",
    "#6366F1", "#8B5CF6", "#0284C7", "#0F766E", "#B45309",
]


def _avatar_color(name: str) -> str:
    """Deterministic background color for company initial avatar."""
    if not name:
        return _AVATAR_COLORS[0]
    return _AVATAR_COLORS[hash(name) % len(_AVATAR_COLORS)]


def company_type_badge(company_type: str) -> str:
    if not company_type or company_type == "Unknown":
        return ""
    css = _COMPANY_TYPE_CSS.get(company_type, "badge-funding")
    return f'<span class="{css}">{company_type}</span>'


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def is_remote_job(app) -> bool:
    if app.is_remote:
        return True
    loc = (app.location or "").lower()
    return "remote" in loc


def company_info_line(app) -> str:
    parts = []
    if app.funding_stage:
        parts.append(app.funding_stage)
    if app.total_funding:
        parts.append(app.total_funding)
    if app.employee_count:
        parts.append(f"{app.employee_count} employees")
    return " \u00b7 ".join(parts)


def score_color_class(score: float) -> str:
    if score >= 70:
        return "score-high"
    elif score >= 50:
        return "score-mid"
    return "score-low"


def _score_bar_fill_class(score: float) -> str:
    if score >= 70:
        return "score-bar-fill-high"
    elif score >= 50:
        return "score-bar-fill-mid"
    return "score-bar-fill-low"


def format_date(dt: datetime | None, style: str = "short") -> str:
    if dt is None:
        return "N/A"
    if style == "relative":
        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = now - dt
        if delta.days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                return "just now"
            return f"{hours}h ago"
        elif delta.days == 1:
            return "yesterday"
        elif delta.days < 7:
            return f"{delta.days}d ago"
        return dt.strftime("%b %d")
    elif style == "full":
        return dt.strftime("%B %d, %Y at %I:%M %p")
    return dt.strftime("%b %d, %Y")


def _clean_description(desc: str | None) -> str:
    """Strip raw markdown artifacts from scraped job descriptions."""
    if not desc:
        return ""
    text = desc
    # Fix escaped markdown: \- \. \* \+ \[ \] \( \)
    text = re.sub(r"\\([*\-_.+\[\](){}#>~|])", r"\1", text)
    # Remove bold/italic markers: **text** -> text, *text* -> text
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    # Remove markdown headers: ## Header -> Header
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Remove horizontal rules: ---, ___, ***, or long sequences of dashes
    text = re.sub(r"^[\s]*[-_*]{3,}[\s]*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"-{4,}", " ", text)
    # Convert markdown bullet points to plain text
    text = re.sub(r"^\s*[-*+]\s+", "- ", text, flags=re.MULTILINE)
    # Remove markdown links: [text](url) -> text
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_description(desc: str | None, max_chars: int = 150) -> str:
    """Return a short preview of the job description (cleaned)."""
    if not desc:
        return ""
    clean = _clean_description(desc)
    clean = " ".join(clean.split())  # collapse whitespace to single line
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rsplit(" ", 1)[0] + "..."


def _team_signal(app) -> str:
    """Detect team size/youth signals from employee count and description."""
    signals = []

    # Employee count signal
    emp = app.employee_count or ""
    if emp:
        # Try to parse ranges like "51-200", "1-10", "501-1000"
        nums = re.findall(r"\d+", emp.replace(",", ""))
        if nums:
            low = int(nums[0])
            if low <= 50:
                signals.append(f"Small team ({emp})")
            elif low <= 200:
                signals.append(f"Mid-size ({emp})")
            else:
                signals.append(f"Large ({emp})")
        else:
            signals.append(emp)

    # Description-based signals for founding/early team
    desc = (app.description or "").lower()
    title = (app.job_title or "").lower()
    founding_signals = [
        "founding", "first hire", "first data", "first engineer",
        "0 to 1", "zero to one", "ground floor", "build from scratch",
        "greenfield", "early-stage", "early stage",
    ]
    for sig in founding_signals:
        if sig in desc or sig in title:
            signals.append("Founding/Early team")
            break

    # Small team signals from description
    small_team_signals = [
        "small team", "lean team", "tight-knit", "close-knit",
        "startup environment", "fast-paced startup", "scrappy",
    ]
    if not any("Small" in s for s in signals):  # don't double-count
        for sig in small_team_signals:
            if sig in desc:
                signals.append("Small team culture")
                break

    return " · ".join(signals) if signals else ""


# ---------------------------------------------------------------------------
# Score breakdown HTML (used in detail view)
# ---------------------------------------------------------------------------

def _render_score_bars_html(app) -> str:
    """Build HTML for all 7 scoring dimensions as gradient bars."""
    dimensions = [
        ("Technical", app.technical_score),
        ("Leadership", app.leadership_score),
        ("Career Prog.", app.career_progression_score),
        ("Platform", app.platform_building_score),
        ("Comp Potential", app.comp_potential_score),
        ("Trajectory", app.company_trajectory_score),
        ("Culture Fit", app.culture_fit_score),
    ]
    # Only render if we have at least one score
    has_scores = any(v for _, v in dimensions)
    if not has_scores:
        return ""

    rows = []
    for label, val in dimensions:
        v = val or 0
        fill_class = _score_bar_fill_class(v)
        rows.append(f"""
        <div class="score-bar-row">
            <span class="score-bar-label">{label}</span>
            <div class="score-bar-track">
                <div class="score-bar-fill {fill_class}" style="width: {v}%"></div>
            </div>
            <span class="score-bar-value">{v:.0f}</span>
        </div>""")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Compound components
# ---------------------------------------------------------------------------

def render_job_card(app, key_prefix: str = "") -> None:
    """Render a single job as a styled card with expandable detail view."""
    score = app.overall_score or 0
    remote = is_remote_job(app)
    sc_class = score_color_class(score) if score else "score-mid"

    # Badge row HTML
    badges = recommendation_badge(app.recommendation or "SKIP")
    if remote:
        badges += " " + remote_badge()
    sal = salary_badge(app.salary_min, app.salary_max)
    if sal:
        badges += " " + sal
    fund = funding_badge(app)
    if fund:
        badges += " " + fund

    location_text = _html_mod.escape(app.location or "Location not specified")
    desc_preview = _truncate_description(app.description)
    safe_title = _html_mod.escape(app.job_title or "")
    safe_company = _html_mod.escape(app.company or "")

    # Company type — always show, inline with company name
    _ct_raw = getattr(app, "company_type", "") or "Unknown"
    ct_badge = company_type_badge(_ct_raw) if _ct_raw != "Unknown" else ""
    company_line = safe_company
    if ct_badge:
        company_line += f" {ct_badge}"
    company_line += f" &middot; {location_text}"

    # Team signal — employee count + founding/small team detection
    team_sig = _team_signal(app)
    team_html = (
        f'<div class="job-card-team-signal">{_html_mod.escape(team_sig)}</div>'
        if team_sig else ""
    )

    # Description preview (already cleaned by _truncate_description)
    desc_html = (
        f'<div class="job-card-desc-preview">{_html_mod.escape(desc_preview)}</div>'
        if desc_preview else ""
    )

    # Source and timestamp for the meta row
    source = app.source or ""
    ts = app.updated_at or app.created_at
    time_str = format_date(ts, "relative")

    # Build meta row
    meta_parts = []
    if app.job_url:
        meta_parts.append(
            f'<a href="{app.job_url}" target="_blank" rel="noopener noreferrer">'
            f'View Posting &rarr;</a>'
        )
    if source:
        meta_parts.append(f'<span class="job-card-source">{source}</span>')
    meta_parts.append(f'<span>{time_str}</span>')
    meta_html = " &nbsp;&middot;&nbsp; ".join(meta_parts)

    # Company avatar — colored circle with first letter
    avatar_initial = safe_company[0].upper() if safe_company else "?"
    avatar_bg = _avatar_color(app.company or "")

    card_html = f"""<div class="job-card"><div class="job-card-header"><div class="job-card-info"><div class="job-card-top"><div class="job-card-avatar" style="background:{avatar_bg}">{avatar_initial}</div><div><div class="job-card-title">{safe_title}</div><div class="job-card-company">{company_line}</div></div></div>{team_html}{desc_html}<div class="job-card-badges">{badges}</div><div class="job-card-meta">{meta_html}</div></div><div class="job-card-score"><div class="score-number {sc_class}">{score:.0f}</div><div class="score-label">score</div></div></div></div>"""
    st.markdown(card_html, unsafe_allow_html=True)

    # Expandable detail view
    _render_detail_expander(app, key_prefix)


def _render_detail_expander(app, key_prefix: str) -> None:
    """Expandable section with score breakdown, description, AI materials."""
    # Build a smart label showing what's inside
    detail_parts = []
    has_scores = any([
        app.technical_score, app.leadership_score,
        app.platform_building_score, app.comp_potential_score,
        app.company_trajectory_score, app.culture_fit_score,
        app.career_progression_score,
    ])
    if has_scores:
        detail_parts.append("Score Breakdown")
    if app.description:
        detail_parts.append("Description")
    if app.cover_letter:
        detail_parts.append("Cover Letter")
    if app.resume_tweaks_json:
        detail_parts.append("Resume Tweaks")
    if app.score_reasoning:
        detail_parts.append("Analysis")

    if not detail_parts:
        detail_parts.append("Details")

    label = " \u00b7 ".join(detail_parts)

    with st.expander(label, expanded=False):
        # Action row at top: status dropdown + quick actions
        acol1, acol2 = st.columns([1, 2])
        with acol1:
            current_status = app.status or "found"
            try:
                idx = STATUS_OPTIONS.index(current_status)
            except ValueError:
                idx = 0
            key = f"{key_prefix}status_{app.id}"
            st.selectbox(
                "Update Status",
                STATUS_OPTIONS,
                index=idx,
                key=key,
                on_change=_handle_status_change,
                args=(app.id, key),
            )

        # Two-column detail layout
        if has_scores:
            score_html = _render_score_bars_html(app)
            if score_html:
                st.markdown("**Score Breakdown**")
                st.markdown(score_html, unsafe_allow_html=True)

        # Strengths & Gaps as pills
        strengths = app.strengths_list
        gaps = app.gaps_list
        if strengths or gaps:
            pills_html = ""
            if strengths:
                pills_html += "<strong>Strengths:</strong> "
                pills_html += " ".join(
                    f'<span class="insight-pill insight-strength">{s}</span>'
                    for s in strengths
                )
                pills_html += "<br>"
            if gaps:
                pills_html += "<strong>Gaps:</strong> "
                pills_html += " ".join(
                    f'<span class="insight-pill insight-gap">{g}</span>'
                    for g in gaps
                )
            st.markdown(pills_html, unsafe_allow_html=True)

        # Reasoning
        if app.score_reasoning:
            st.markdown(f"**Analysis:** {app.score_reasoning}")

        # Job Description (cleaned of markdown artifacts)
        if app.description:
            st.divider()
            st.markdown("**Job Description**")
            desc = _clean_description(app.description)
            if len(desc) > 1500:
                st.text_area(
                    "Full Description",
                    desc,
                    height=250,
                    key=f"{key_prefix}desc_{app.id}",
                    label_visibility="collapsed",
                    disabled=True,
                )
            else:
                # Escape HTML entities in the description to avoid injection,
                # then convert newlines to <br> for readable formatting
                desc_safe = _html_mod.escape(desc[:3000]).replace("\n", "<br>")
                st.markdown(
                    f'<div class="job-description-body">{desc_safe}</div>',
                    unsafe_allow_html=True,
                )

        # Cover Letter & Resume Tweaks in tabs
        if app.cover_letter or app.resume_tweaks_json:
            st.divider()
            tab_names = []
            if app.cover_letter:
                tab_names.append("Cover Letter")
            if app.resume_tweaks_json:
                tab_names.append("Resume Tweaks")

            tabs = st.tabs(tab_names)
            tab_idx = 0
            if app.cover_letter:
                with tabs[tab_idx]:
                    st.text_area(
                        "Cover Letter",
                        app.cover_letter,
                        height=250,
                        key=f"{key_prefix}cl_{app.id}",
                        label_visibility="collapsed",
                    )
                tab_idx += 1
            if app.resume_tweaks_json:
                with tabs[tab_idx]:
                    try:
                        tweaks = json.loads(app.resume_tweaks_json)
                        st.json(tweaks)
                    except json.JSONDecodeError:
                        st.text(app.resume_tweaks_json)

        # Company Intel
        if app.company_intel_json:
            st.divider()
            st.markdown("**Company Intel**")
            try:
                intel = json.loads(app.company_intel_json)
                if isinstance(intel, dict):
                    for k, v in intel.items():
                        if v:
                            st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                else:
                    st.json(intel)
            except json.JSONDecodeError:
                st.text(app.company_intel_json)


def _handle_status_change(app_id: int, key: str) -> None:
    """Callback for inline status update."""
    new_status = st.session_state.get(key)
    if new_status:
        update_application_status(app_id, new_status)
        st.toast(f"Status updated to {new_status}")


def render_activity_item(app) -> None:
    """Render a single activity feed item."""
    status = app.status or "found"
    dot_color = _STATUS_DOTS.get(status, "gray")
    ts = app.updated_at or app.created_at
    time_str = format_date(ts, "relative")

    html = f"""
    <div class="activity-item">
      <span class="activity-dot activity-dot-{dot_color}"></span>
      <span class="activity-text">
        <strong>{app.company}</strong> &mdash; {app.job_title}
        {status_badge(status)}
      </span>
      <span class="activity-time">{time_str}</span>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def render_empty_state(icon: str, title: str, description: str) -> None:
    """Render a centered empty state."""
    st.markdown(
        f"""
        <div class="empty-state">
          <div class="empty-state-icon">{icon}</div>
          <div class="empty-state-title">{title}</div>
          <div class="empty-state-desc">{description}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _get_job_sources() -> list[tuple[str, str]]:
    """Get job sources from the scraper registry."""
    try:
        from job_finder.tools.scrapers import get_all_metadata
        return [(m.display_name, m.url) for m in get_all_metadata()]
    except Exception:
        # Fallback if registry fails to load
        return [
            ("Indeed", "https://indeed.com"),
            ("LinkedIn", "https://linkedin.com"),
            ("Glassdoor", "https://glassdoor.com"),
            ("ZipRecruiter", "https://ziprecruiter.com"),
            ("Google Jobs", "https://google.com/jobs"),
            ("YC Startups", "https://workatastartup.com"),
            ("Remotive", "https://remotive.com"),
            ("Himalayas", "https://himalayas.app"),
            ("We Work Remotely", "https://weworkremotely.com"),
            ("Hacker News", "https://news.ycombinator.com"),
            ("Greenhouse", "https://greenhouse.io"),
            ("Lever", "https://lever.co"),
            ("RemoteOK", "https://remoteok.com"),
            ("CryptoJobsList", "https://cryptojobslist.com"),
        ]


def render_pipeline_steps(llm_available: bool) -> None:
    """Show the 3-step pipeline as visual cards."""
    cols = st.columns(3)

    job_sources = _get_job_sources()
    source_names = " &middot; ".join(name for name, _ in job_sources)
    steps = [
        ("1", "Search", f'<span class="pipeline-sources">{source_names}</span>', "done"),
        ("2", "Score", "7-dimension scoring against resume", "done"),
        (
            "3",
            "Enhance",
            "Cover letters & company intel",
            "done" if llm_available else "pending",
        ),
    ]

    for col, (num, label, desc, state) in zip(cols, steps):
        with col:
            css = f"pipeline-step pipeline-step-{state}"
            icon_map = {"done": "&#10003;", "active": "&#9679;", "pending": "&#128274;"}
            icon = icon_map.get(state, "&#9679;")
            st.markdown(
                f"""
                <div class="{css}">
                  <div class="pipeline-step-icon">{icon}</div>
                  <div class="pipeline-step-label">{num}. {label}</div>
                  <div class="pipeline-step-desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def render_connection_badge(llm) -> None:
    """Show a compact connection status badge."""
    info = llm.get_provider_info()
    if not llm.is_configured:
        st.markdown(
            '<span class="conn-badge conn-badge-off">'
            '<span class="conn-dot conn-dot-off"></span> No LLM configured</span>',
            unsafe_allow_html=True,
        )
    elif llm.is_available():
        st.markdown(
            f'<span class="conn-badge conn-badge-ok">'
            f'<span class="conn-dot conn-dot-ok"></span> {info["model"]}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<span class="conn-badge conn-badge-err">'
            f'<span class="conn-dot conn-dot-err"></span> {info["label"]} unreachable</span>',
            unsafe_allow_html=True,
        )
