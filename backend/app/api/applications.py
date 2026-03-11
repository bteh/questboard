from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.schemas.application import (
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationUpdate,
    StatusUpdate,
)
from app.schemas.apply import PrepareResponse, SubmitRequest, SubmitResponse
from app.services import application_service
from app.services import apply_service

router = APIRouter(prefix="/applications", tags=["applications"])


def _to_response(record) -> ApplicationResponse:
    strengths = []
    gaps = []
    try:
        if record.key_strengths:
            strengths = json.loads(record.key_strengths)
    except (json.JSONDecodeError, TypeError):
        pass
    try:
        if record.key_gaps:
            gaps = json.loads(record.key_gaps)
    except (json.JSONDecodeError, TypeError):
        pass

    return ApplicationResponse(
        id=record.id,
        job_title=record.job_title,
        company=record.company,
        location=record.location or "",
        job_url=record.job_url or "",
        source=record.source or "",
        description=record.description or "",
        is_remote=record.is_remote or False,
        work_type=getattr(record, "work_type", "") or "",
        salary_min=record.salary_min,
        salary_max=record.salary_max,
        overall_score=record.overall_score,
        technical_score=record.technical_score,
        leadership_score=record.leadership_score,
        platform_building_score=record.platform_building_score,
        comp_potential_score=record.comp_potential_score,
        company_trajectory_score=record.company_trajectory_score,
        culture_fit_score=record.culture_fit_score,
        career_progression_score=record.career_progression_score,
        recommendation=record.recommendation or "",
        score_reasoning=record.score_reasoning or "",
        key_strengths=strengths,
        key_gaps=gaps,
        funding_stage=record.funding_stage,
        total_funding=record.total_funding,
        employee_count=record.employee_count,
        company_type=getattr(record, "company_type", "") or "",
        company_intel_json=record.company_intel_json or "",
        resume_tweaks_json=record.resume_tweaks_json or "",
        cover_letter=record.cover_letter or "",
        application_method=getattr(record, "application_method", "") or "",
        profile=getattr(record, "profile", "default") or "default",
        status=record.status or "found",
        date_found=record.date_found,
        date_applied=record.date_applied,
        notes=record.notes or "",
        contact_name=record.contact_name or "",
        contact_email=record.contact_email or "",
        referral_source=record.referral_source or "",
        url_status=getattr(record, "url_status", "unknown") or "unknown",
        last_checked_at=getattr(record, "last_checked_at", None),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=ApplicationListResponse)
def list_applications(
    status: str | None = None,
    min_score: float | None = None,
    recommendation: str | None = None,
    source: str | None = None,
    search: str | None = None,
    company_type: str | None = None,
    is_remote: bool | None = None,
    work_type: str | None = None,
    profile: str | None = None,
    sort_by: str = "overall_score",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    items, total = application_service.get_applications(
        db,
        status=status,
        min_score=min_score,
        recommendation=recommendation,
        source=source,
        search=search,
        company_type=company_type,
        is_remote=is_remote,
        work_type=work_type,
        profile=profile,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    return ApplicationListResponse(
        items=[_to_response(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=ApplicationResponse, status_code=201)
def create_application(
    body: ApplicationCreate,
    db: Session = Depends(get_db),
):
    """Manually add a job application."""
    record = application_service.create_application(db, body)
    return _to_response(record)


@router.get("/export/csv")
def export_csv(
    status: str | None = None,
    min_score: float | None = None,
    recommendation: str | None = None,
    source: str | None = None,
    search: str | None = None,
    company_type: str | None = None,
    is_remote: bool | None = None,
    work_type: str | None = None,
    profile: str | None = None,
    sort_by: str = "overall_score",
    sort_dir: str = "desc",
    db: Session = Depends(get_db),
):
    """Export filtered applications as CSV."""
    items, _ = application_service.get_applications(
        db,
        status=status,
        min_score=min_score,
        recommendation=recommendation,
        source=source,
        search=search,
        company_type=company_type,
        is_remote=is_remote,
        work_type=work_type,
        profile=profile,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=1,
        page_size=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Company", "Title", "Score", "Recommendation", "Status", "URL"])
    for r in items:
        writer.writerow([
            r.company,
            r.job_title,
            r.overall_score or "",
            r.recommendation or "",
            r.status or "found",
            r.job_url or "",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=job_applications.csv"},
    )


@router.get("/{app_id}", response_model=ApplicationResponse)
def get_application(app_id: int, db: Session = Depends(get_db)):
    record = application_service.get_application(db, app_id)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_response(record)


@router.patch("/{app_id}", response_model=ApplicationResponse)
def update_application(
    app_id: int,
    update: ApplicationUpdate,
    db: Session = Depends(get_db),
):
    record = application_service.update_application(
        db, app_id, **update.model_dump(exclude_unset=True)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_response(record)


@router.patch("/{app_id}/status", response_model=ApplicationResponse)
def update_status(
    app_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    kwargs = {"status": body.status}
    if body.notes:
        kwargs["notes"] = body.notes
    record = application_service.update_application(db, app_id, **kwargs)
    if not record:
        raise HTTPException(status_code=404, detail="Application not found")
    return _to_response(record)


@router.delete("/{app_id}")
def delete_application(app_id: int, db: Session = Depends(get_db)):
    deleted = application_service.delete_application(db, app_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
    return {"deleted": True}


@router.post("/check-urls")
def check_urls(
    ids: list[int] | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Check if job posting URLs are still live. Updates url_status in DB."""
    return application_service.check_urls(db, ids=ids, limit=limit)


@router.post("/deduplicate")
def deduplicate_applications(
    profile: str | None = None,
    db: Session = Depends(get_db),
):
    """Merge cross-source duplicate applications in the database.

    Groups records by normalized (company + title) and merges duplicates,
    keeping the record with the richest data and deleting the rest.
    Returns the number of duplicate records removed.
    """
    from job_finder.pipeline import _normalize_company, _normalize_title

    from app.models.application import ApplicationRecord

    query = db.query(ApplicationRecord)
    if profile:
        query = query.filter(ApplicationRecord.profile == profile)
    all_records = query.all()

    # Group by normalized (company, title)
    groups: dict[str, list] = {}
    for rec in all_records:
        co = _normalize_company(rec.company or "")
        ti = _normalize_title(rec.job_title or "")
        if not co or not ti:
            continue
        key = f"{co}||{ti}"
        groups.setdefault(key, []).append(rec)

    removed = 0
    for key, group in groups.items():
        if len(group) <= 1:
            continue

        # Pick the best record to keep
        def _richness(rec):
            desc_len = len(rec.description or "")
            has_salary = 1 if (rec.salary_min or rec.salary_max) else 0
            has_score = 1 if rec.overall_score else 0
            score = rec.overall_score or 0
            has_cover = 1 if rec.cover_letter else 0
            has_intel = 1 if rec.company_intel_json else 0
            # Prefer manually-updated records (status != "found")
            has_status = 1 if rec.status and rec.status != "found" else 0
            return (has_status, has_cover, has_intel, has_salary, has_score, score, desc_len)

        group.sort(key=_richness, reverse=True)
        keeper = group[0]

        # Merge useful data from duplicates into keeper
        for dup in group[1:]:
            if not keeper.salary_min and dup.salary_min:
                keeper.salary_min = dup.salary_min
            if not keeper.salary_max and dup.salary_max:
                keeper.salary_max = dup.salary_max
            if not keeper.cover_letter and dup.cover_letter:
                keeper.cover_letter = dup.cover_letter
            if not keeper.company_intel_json and dup.company_intel_json:
                keeper.company_intel_json = dup.company_intel_json
            if not keeper.resume_tweaks_json and dup.resume_tweaks_json:
                keeper.resume_tweaks_json = dup.resume_tweaks_json
            if dup.overall_score and (not keeper.overall_score or dup.overall_score > keeper.overall_score):
                keeper.overall_score = dup.overall_score
                keeper.technical_score = dup.technical_score
                keeper.leadership_score = dup.leadership_score
                keeper.platform_building_score = dup.platform_building_score
                keeper.comp_potential_score = dup.comp_potential_score
                keeper.company_trajectory_score = dup.company_trajectory_score
                keeper.culture_fit_score = dup.culture_fit_score
                keeper.career_progression_score = dup.career_progression_score
                keeper.recommendation = dup.recommendation
                keeper.score_reasoning = dup.score_reasoning
                keeper.key_strengths = dup.key_strengths
                keeper.key_gaps = dup.key_gaps
            if len(dup.description or "") > len(keeper.description or ""):
                keeper.description = dup.description
            db.delete(dup)
            removed += 1

    if removed > 0:
        db.commit()

    return {"removed": removed, "message": f"Merged {removed} duplicate records"}


@router.post("/purge-locations")
def purge_non_matching_locations(
    profile: str | None = None,
):
    """Delete saved jobs that don't match the profile's location preferences.

    Remote jobs are always kept. Only onsite/hybrid jobs outside preferred
    states/cities are removed. Auto-derives from search locations if no
    explicit location_preferences section is configured.
    """
    from job_finder.pipeline import _load_search_config
    from job_finder.models.database import (
        init_db,
        purge_non_matching_locations as _purge,
    )

    config = _load_search_config(profile)
    loc_prefs = config.get("location_preferences", {})

    if loc_prefs.get("filter_enabled", False):
        pref_states = loc_prefs.get("preferred_states", [])
        pref_cities = loc_prefs.get("preferred_cities", [])
    else:
        # Auto-derive from search locations
        from job_finder.company_classifier import parse_location
        pref_states = []
        pref_cities = []
        for loc in config.get("locations", []):
            if loc.lower() in ("remote", "united states", "usa", "us", "anywhere"):
                continue
            parsed = parse_location(loc)
            if parsed["state"] and parsed["state"] not in pref_states:
                pref_states.append(parsed["state"])
            if parsed["city"] and parsed["city"] not in pref_cities:
                pref_cities.append(parsed["city"])

    if not pref_states and not pref_cities:
        return {"purged": 0, "message": "No location preferences configured"}

    init_db()
    purged = _purge(
        preferred_states=pref_states,
        preferred_cities=pref_cities,
        profile=profile,
    )
    return {"purged": purged, "message": f"Removed {purged} jobs outside preferred locations"}


@router.post("/{app_id}/prepare", response_model=PrepareResponse)
def prepare_application(
    app_id: int,
    profile: str = "default",
    db: Session = Depends(get_db),
):
    """Prepare application materials (cover letter, resume tweaks) and detect ATS.

    Generates missing materials via LLM when available and saves them to the DB.
    """
    result = apply_service.prepare_application(db, app_id, profile=profile)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return PrepareResponse(**result)


@router.post("/{app_id}/apply", response_model=SubmitResponse)
def submit_application(
    app_id: int,
    body: SubmitRequest,
    profile: str = "default",
    db: Session = Depends(get_db),
):
    """Submit an application via detected ATS (Greenhouse/Lever).

    Defaults to dry_run=True for safety. Set dry_run=False for live submission.
    """
    result = apply_service.submit_application(
        db,
        app_id,
        cover_letter=body.cover_letter,
        dry_run=body.dry_run,
        profile=profile,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return SubmitResponse(**result)
