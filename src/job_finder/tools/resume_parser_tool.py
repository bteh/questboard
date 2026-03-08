"""Resume PDF parser — plain function, no framework dependency."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def find_resume(profile: str | None = None) -> str | None:
    """Search for a resume PDF in the ``knowledge/`` directory.

    Parameters
    ----------
    profile:
        When provided, looks for ``{profile}_resume.pdf`` first before
        falling back to generic resume detection.

    Returns the absolute path of the first PDF found, or *None*.
    """
    knowledge_dirs = [
        os.path.join(os.getcwd(), "knowledge"),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "knowledge")
        ),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
        ),
    ]

    for knowledge_dir in knowledge_dirs:
        if not os.path.exists(knowledge_dir):
            continue

        # Priority 1: profile-specific resume
        if profile:
            profile_file = f"{profile}_resume.pdf"
            profile_path = os.path.join(knowledge_dir, profile_file)
            if os.path.exists(profile_path):
                return profile_path

        # Priority 2-3: generic fallback
        pdfs = [
            f for f in os.listdir(knowledge_dir) if f.lower().endswith(".pdf")
        ]
        if not pdfs:
            continue
        # Prefer files with "resume" in the name
        resume_pdfs = [f for f in pdfs if "resume" in f.lower()]
        target = resume_pdfs[0] if resume_pdfs else pdfs[0]
        return os.path.join(knowledge_dir, target)
    return None


def parse_resume(file_path: str = "", profile: str | None = None) -> str:
    """Parse a PDF resume and return the full text content.

    Parameters
    ----------
    file_path:
        Path to the resume PDF.  If empty, checks the ``RESUME_PATH``
        environment variable, then searches ``knowledge/``.
    profile:
        Profile name for profile-specific resume detection.

    Returns
    -------
    str
        The extracted text, or an ``ERROR:`` / ``WARNING:`` prefixed string
        on failure.
    """
    # Resolve path
    if not file_path:
        file_path = os.getenv("RESUME_PATH", "")
    if not file_path:
        file_path = find_resume(profile=profile) or ""

    if not file_path:
        return (
            "ERROR: No resume PDF found. Please place your resume PDF in the "
            "knowledge/ directory or provide a file path."
        )

    if not os.path.exists(file_path):
        return f"ERROR: Resume file not found at: {file_path}"

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(file_path)
        text_parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)

        if not full_text.strip():
            return (
                "WARNING: PDF was read but no text was extracted. "
                "The PDF might be image-based. Consider using an OCR tool."
            )

        return full_text

    except ImportError:
        return "ERROR: PyPDF2 not installed. Run: pip install PyPDF2"
    except Exception as e:
        return f"ERROR parsing resume: {e!s}"
