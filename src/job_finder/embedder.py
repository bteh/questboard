"""Local sentence embeddings for hybrid retrieval (ships dark).

Wraps fastembed + ``BAAI/bge-small-en-v1.5``, an ONNX CPU model with no torch.
This module NEVER hard-fails: if fastembed or the model weights are missing,
``is_available()`` is False and every ``encode`` returns None, so callers fall
back to keyword/BM25 ranking. Nothing loads at import time; the model loads
lazily on first use and is cached process-wide behind a lock.

Vectors come back L2-normalized float32, so cosine similarity is a plain dot
product. They are stored as raw little-endian float32 bytes (see
``embeddings_index``). fastembed is an OPTIONAL dependency (``pip install
'questboard[embeddings]'``); until it is installed nothing here does anything.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Sequence

logger = logging.getLogger(__name__)

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
# bge wants this instruction prefix on the QUERY side (the resume), never on
# the stored documents (the jobs). See the model card.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

_model = None
_load_lock = threading.Lock()
_load_failed = False


def _hosted_artifact_missing() -> bool:
    """Hosted processes may only use a model artifact baked into the image."""
    hosted = os.getenv("HOSTED_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    cache_dir = os.getenv("JOB_FINDER_EMBEDDING_CACHE_DIR", "").strip()
    has_files = bool(
        cache_dir
        and os.path.isdir(cache_dir)
        and any(files for _root, _dirs, files in os.walk(cache_dir))
    )
    return bool(hosted and not has_files)


def _load_model():
    """Load the model once, or record that it is unavailable. Never raises."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    with _load_lock:
        if _model is not None or _load_failed:
            return _model
        if _hosted_artifact_missing():
            _load_failed = True
            logger.warning(
                "Embeddings unavailable: hosted mode requires a preloaded model artifact; "
                "ranking falls back to BM25"
            )
            return None
        try:
            from fastembed import TextEmbedding  # heavy + optional
        except Exception as exc:  # not installed
            _load_failed = True
            logger.info(
                "Embeddings unavailable (fastembed not installed: %s); "
                "ranking falls back to keywords",
                exc,
            )
            return None
        try:
            cache_dir = os.getenv("JOB_FINDER_EMBEDDING_CACHE_DIR", "").strip() or None
            kwargs = {"model_name": MODEL_NAME}
            if cache_dir:
                kwargs["cache_dir"] = cache_dir
            _model = TextEmbedding(**kwargs)
            logger.info("Loaded embedding model %s (%d-dim)", MODEL_NAME, DIM)
        except Exception as exc:  # weights download blocked / transient
            # Do NOT latch here. Unlike a missing package, a load failure is
            # often transient (a network blip on the first weight download), so
            # leaving _load_failed False lets the next batch run retry instead
            # of degrading to keywords for the whole process lifetime. The only
            # caller is the occasional batch indexer, so retry cost is bounded.
            logger.warning(
                "Embedding model %s failed to load (%s); will retry next run, "
                "keywords for now",
                MODEL_NAME,
                exc,
            )
    return _model


def is_available() -> bool:
    """True only when a real model is loaded and encoding will work."""
    return _load_model() is not None


def reset_for_tests() -> None:
    """Clear the cached load state. Test-only seam."""
    global _model, _load_failed
    _model = None
    _load_failed = False


def encode(texts: Sequence[str], *, is_query: bool = False):
    """Return an ``(n, DIM)`` float32 L2-normalized numpy array, or None.

    None means the model is unavailable, so the caller must degrade to
    keyword/BM25 ranking. ``is_query=True`` applies the bge query prefix
    (used for the resume side, not the stored jobs).
    """
    model = _load_model()
    if model is None or not texts:
        return None
    try:
        import numpy as np

        prepared = [QUERY_PREFIX + t if is_query else t for t in texts]
        vecs = np.asarray(list(model.embed(prepared)), dtype="float32")
        if vecs.ndim != 2 or vecs.shape[1] != DIM:
            logger.warning("Unexpected embedding shape %s; ignoring", vecs.shape)
            return None
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
    except Exception as exc:
        logger.warning("Embedding failed (%s); falling back to keywords", exc)
        return None


def encode_one(text: str, *, is_query: bool = False):
    """Encode a single string to a normalized 1-D vector, or None."""
    out = encode([text], is_query=is_query)
    return None if out is None else out[0]
