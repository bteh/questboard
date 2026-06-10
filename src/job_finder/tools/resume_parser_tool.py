"""Resume parser (PDF, DOCX, TXT) — plain function, no framework dependency."""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)
_SAFE_PROFILE_RE = re.compile(r"^[A-Za-z0-9_-]+$")

SUPPORTED_RESUME_EXTENSIONS = (".pdf", ".docx", ".txt")


def find_resume(profile: str | None = None) -> str | None:
    """Search for a resume (PDF, DOCX, or TXT) in the ``knowledge/`` directory.

    Parameters
    ----------
    profile:
        When provided, looks for ``{profile}_resume.{pdf,docx,txt}`` first
        before falling back to generic resume detection.

    Returns the absolute path of the first resume found, or *None*.
    """
    if profile and not _SAFE_PROFILE_RE.fullmatch(profile):
        logger.warning("Ignoring unsafe profile name '%s' during resume lookup", profile)
        profile = None

    knowledge_dirs = [
        os.path.join(os.getcwd(), "knowledge"),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "knowledge")
        ),
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "knowledge")
        ),
    ]

    # Deduplicate resolved paths to avoid scanning the same directory twice
    seen: set[str] = set()
    unique_dirs: list[str] = []
    for d in knowledge_dirs:
        resolved = os.path.realpath(d)
        if resolved not in seen and os.path.exists(resolved):
            seen.add(resolved)
            unique_dirs.append(resolved)

    # Priority 1: profile-specific resume across ALL directories
    if profile:
        for knowledge_dir in unique_dirs:
            for ext in SUPPORTED_RESUME_EXTENSIONS:
                profile_path = os.path.join(knowledge_dir, f"{profile}_resume{ext}")
                if os.path.exists(profile_path):
                    return profile_path

    # Priority 2: default_resume.{pdf,docx,txt}
    for knowledge_dir in unique_dirs:
        for ext in SUPPORTED_RESUME_EXTENSIONS:
            default_path = os.path.join(knowledge_dir, f"default_resume{ext}")
            if os.path.exists(default_path):
                return default_path

    # Priority 3: any supported file with "resume" in the name
    for knowledge_dir in unique_dirs:
        candidates = [
            f
            for f in os.listdir(knowledge_dir)
            if f.lower().endswith(SUPPORTED_RESUME_EXTENSIONS)
        ]
        if not candidates:
            continue
        resume_named = sorted(f for f in candidates if "resume" in f.lower())
        target = resume_named[0] if resume_named else candidates[0]
        return os.path.join(knowledge_dir, target)
    return None


def parse_resume(file_path: str = "", profile: str | None = None) -> str:
    """Parse a resume (PDF, DOCX, or TXT) and return the full text content.

    Parameters
    ----------
    file_path:
        Path to the resume file.  If empty, checks the ``RESUME_PATH``
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
            "ERROR: No resume found. Please place your resume (PDF, DOCX, or TXT) "
            "in the knowledge/ directory or provide a file path."
        )

    if not os.path.exists(file_path):
        return f"ERROR: Resume file not found at: {file_path}"

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".docx":
        return _parse_docx(file_path)
    if ext == ".txt":
        return _parse_txt(file_path)
    return _parse_pdf(file_path)


def _parse_pdf(file_path: str) -> str:
    """Extract text from a PDF resume via PyPDF2."""
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


def _parse_docx(file_path: str) -> str:
    """Extract text from a DOCX resume via python-docx (lazy import)."""
    try:
        import docx
    except ImportError:
        return "ERROR: python-docx not installed. Run: pip install python-docx"

    try:
        document = docx.Document(file_path)
        text_parts: list[str] = [
            p.text.strip() for p in document.paragraphs if p.text and p.text.strip()
        ]
        for table in document.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text and cell.text.strip():
                        text_parts.append(cell.text.strip())

        full_text = "\n".join(text_parts)

        if not full_text.strip():
            return "WARNING: DOCX was read but no text was extracted."

        return full_text
    except Exception as e:
        return f"ERROR parsing resume: {e!s}"


def _parse_txt(file_path: str) -> str:
    """Read a plain-text resume."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            full_text = f.read()

        if not full_text.strip():
            return "WARNING: Text file was read but it is empty."

        return full_text
    except Exception as e:
        return f"ERROR parsing resume: {e!s}"
