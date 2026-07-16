"""Batch embedding indexer for the hybrid ranker (ships dark).

Embeddings are computed OUT of the scrape hot path: ``save_application`` stays
a fast, LLM-free insert, and this batch job embeds new or changed rows
afterwards (call it post-scrape or from the scheduler). That matters because
the embedding model is CPU-bound and would otherwise block the single hosted
worker (see the debate notes).

Everything here is a no-op until the optional embedding model is installed:
``index_embeddings`` returns ``available=False`` and writes nothing. When the
model is present, each application is embedded once and gated by a content
hash, so an unchanged re-scrape re-embeds nothing.
"""
from __future__ import annotations

import hashlib
import logging

logger = logging.getLogger(__name__)

_MAX_DESC_CHARS = 2000


def job_embedding_text(job_title: str | None, company: str | None, description: str | None) -> str:
    """The text embedded for one job: title, company, then a description head.

    The description is capped so one enormous posting can't dominate the
    vector or slow encoding; the title and company carry the strongest signal.
    """
    parts = [
        (job_title or "").strip(),
        (company or "").strip(),
        (description or "").strip()[:_MAX_DESC_CHARS],
    ]
    return " . ".join(p for p in parts if p)


def content_hash(text: str) -> str:
    """Stable hash of (model + text); an unchanged hash skips re-embedding.

    The model name is folded in so swapping the embedding model changes every
    hash and forces a clean re-embed of the whole board.
    """
    from job_finder import embedder

    return hashlib.sha256(f"{embedder.MODEL_NAME}\n{text}".encode("utf-8")).hexdigest()


def index_embeddings(*, batch_size: int = 128, limit: int | None = None) -> dict:
    """Embed applications missing a current vector. No-op without the model.

    Returns a summary dict: ``available`` (was the model loadable),
    ``indexed`` (rows embedded), ``skipped`` (already current),
    ``pruned`` (orphan vectors deleted). On a mid-run DB error it rolls back,
    returns what landed, and never leaves the thread-local session poisoned
    for the next caller.
    """
    from job_finder import embedder

    result = {"available": False, "indexed": 0, "skipped": 0, "pruned": 0}
    if not embedder.is_available():
        return result
    result["available"] = True

    from job_finder.models.database import (
        ApplicationRecord,
        JobEmbedding,
        _close_session,
        get_session,
    )

    session = get_session()
    try:
        existing: dict[int, str] = dict(
            session.query(JobEmbedding.application_id, JobEmbedding.content_hash).all()
        )
        apps = session.query(
            ApplicationRecord.id,
            ApplicationRecord.job_title,
            ApplicationRecord.company,
            ApplicationRecord.description,
        ).all()
        live_ids = {a.id for a in apps}

        # Prune vectors whose application is gone (SQLite doesn't enforce the FK
        # cascade unless PRAGMA foreign_keys is on, so never rely on it).
        orphans = [aid for aid in existing if aid not in live_ids]
        if orphans:
            session.query(JobEmbedding).filter(
                JobEmbedding.application_id.in_(orphans)
            ).delete(synchronize_session=False)
            session.commit()
            result["pruned"] = len(orphans)

        todo: list[tuple[int, str, str]] = []
        for app in apps:
            text = job_embedding_text(app.job_title, app.company, app.description)
            digest = content_hash(text)
            if existing.get(app.id) == digest:
                result["skipped"] += 1
                continue
            todo.append((app.id, text, digest))
            if limit is not None and len(todo) >= limit:
                break

        for start in range(0, len(todo), batch_size):
            chunk = todo[start : start + batch_size]
            vectors = embedder.encode([text for _, text, _ in chunk])
            if vectors is None:
                # Model became unavailable mid-run; stop and leave the rest for
                # the next pass rather than write partial garbage. Chunks that
                # already committed stay; deferred rows keep no vector so the
                # next pass re-picks them by content hash.
                logger.warning(
                    "Embedding stopped mid-run; %d rows deferred", len(todo) - start
                )
                break
            for (app_id, _text, digest), vector in zip(chunk, vectors):
                blob = vector.astype("float32").tobytes()
                row = session.get(JobEmbedding, app_id)
                if row is None:
                    session.add(
                        JobEmbedding(
                            application_id=app_id,
                            model=embedder.MODEL_NAME,
                            dim=embedder.DIM,
                            content_hash=digest,
                            vector=blob,
                        )
                    )
                else:
                    row.model = embedder.MODEL_NAME
                    row.dim = embedder.DIM
                    row.content_hash = digest
                    row.vector = blob
                result["indexed"] += 1
            session.commit()
    except Exception as exc:
        # Best-effort batch job: a failed commit (e.g. WAL write contention)
        # must not leave the thread-local scoped session mid-transaction for
        # the next caller. Roll back and return what already landed.
        session.rollback()
        logger.warning(
            "Embedding index aborted (%s); %d embedded before stop",
            exc,
            result["indexed"],
        )
    finally:
        _close_session()

    logger.info(
        "Embedding index: %d embedded, %d current, %d pruned",
        result["indexed"],
        result["skipped"],
        result["pruned"],
    )
    return result


def load_embeddings():
    """Load every stored vector as ``(app_ids, matrix)`` for ranking.

    ``matrix`` is an ``(n, DIM)`` float32 numpy array whose row i belongs to
    ``app_ids[i]``. Returns ``([], None)`` when there are no vectors or numpy
    is unavailable. The hybrid ranker (PR B) uses this for the semantic half.
    """
    try:
        import numpy as np
    except Exception:
        return [], None

    from job_finder.models.database import JobEmbedding, _close_session, get_session

    session = get_session()
    try:
        rows = session.query(JobEmbedding.application_id, JobEmbedding.vector).all()
    finally:
        _close_session()

    if not rows:
        return [], None

    app_ids = [aid for aid, _ in rows]
    matrix = np.vstack([np.frombuffer(blob, dtype="float32") for _, blob in rows])
    return app_ids, matrix
