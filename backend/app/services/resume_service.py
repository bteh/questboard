"""Resume management service — file operations and parsing."""

from __future__ import annotations

import os

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_KNOWLEDGE_DIR = os.path.join(_PROJECT_ROOT, "knowledge")


def _original_name_path(profile: str) -> str:
    """Path to the sidecar file that stores the user's original filename."""
    return os.path.join(_KNOWLEDGE_DIR, f".{profile}_resume_name")


def get_resume_status(profile: str) -> dict:
    """Check if a resume exists for the given profile."""
    from job_finder.tools.resume_parser_tool import find_resume

    path = find_resume(profile=profile)
    if path and os.path.exists(path):
        # Show the user's original filename if we stored it
        display_name = os.path.basename(path)
        name_file = _original_name_path(profile)
        if os.path.exists(name_file):
            try:
                stored = open(name_file, encoding="utf-8").read().strip()
                if stored:
                    display_name = stored
            except OSError:
                pass
        try:
            file_size = os.path.getsize(path)
        except OSError:
            file_size = 0
        return {
            "profile": profile,
            "exists": True,
            "filename": display_name,
            "file_size": file_size,
            "path": path,
        }
    return {
        "profile": profile,
        "exists": False,
        "filename": "",
        "file_size": 0,
        "path": "",
    }


def upload_resume(profile: str, filename: str, content: bytes) -> dict:
    """Save an uploaded resume PDF for the given profile.

    Writes to both the project-root ``knowledge/`` dir and the CWD-based
    ``knowledge/`` dir (if different) so that ``find_resume()`` always
    finds the latest upload regardless of working directory.
    """
    target_name = f"{profile}_resume.pdf"

    # Primary location (project root)
    os.makedirs(_KNOWLEDGE_DIR, exist_ok=True)
    primary_path = os.path.join(_KNOWLEDGE_DIR, target_name)
    with open(primary_path, "wb") as f:
        f.write(content)

    # Store the user's original filename for display
    with open(_original_name_path(profile), "w", encoding="utf-8") as f:
        f.write(filename)

    # Also write to CWD-based knowledge/ if it differs (backend often runs
    # from a different CWD than the project root)
    cwd_knowledge = os.path.join(os.getcwd(), "knowledge")
    if os.path.realpath(cwd_knowledge) != os.path.realpath(_KNOWLEDGE_DIR):
        os.makedirs(cwd_knowledge, exist_ok=True)
        cwd_path = os.path.join(cwd_knowledge, target_name)
        with open(cwd_path, "wb") as f:
            f.write(content)

    return {
        "profile": profile,
        "filename": filename,
        "message": "Resume uploaded successfully",
    }


def get_resume_path(profile: str) -> str | None:
    """Return the path to the resume PDF if it exists."""
    from job_finder.tools.resume_parser_tool import find_resume

    return find_resume(profile=profile)


def get_resume_text(profile: str) -> str:
    """Parse and return the resume text for a profile."""
    from job_finder.tools.resume_parser_tool import parse_resume

    return parse_resume(profile=profile)
