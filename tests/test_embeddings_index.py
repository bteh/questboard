"""The dense embedding index ships dark and degrades cleanly.

Without the optional model installed, the embedder is a no-op and the indexer
writes nothing. With a fake model, the indexer embeds each application once,
gates re-embedding on a content hash, prunes orphans, commits per batch, and
defers the rest if the model drops mid-run. The vectors load back as a matrix
aligned to their application ids for the ranker (PR B). No model download in
CI: the degrade tests force fastembed absent rather than assume it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = str(ROOT / "backend")
SRC_PATH = str(ROOT / "src")
for _p in (BACKEND_PATH, SRC_PATH):
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, BACKEND_PATH)
sys.path.insert(1, SRC_PATH)


@pytest.fixture(autouse=True)
def _reset_embedder():
    """Never let the embedder's process-wide load state leak between tests."""
    from job_finder import embedder

    embedder.reset_for_tests()
    yield
    embedder.reset_for_tests()


@pytest.fixture()
def db(tmp_path):
    import importlib

    for module_name in list(sys.modules):
        if module_name == "job_finder.models" or module_name.startswith("job_finder.models."):
            sys.modules.pop(module_name, None)
    jf_db = importlib.import_module("job_finder.models.database")
    jf_db.init_db(str(tmp_path / "emb.db"))
    yield jf_db
    if jf_db._SessionLocal is not None:
        jf_db._SessionLocal.remove()


def _save(jf_db, title, company, desc, url):
    return jf_db.save_application(
        job_title=title, company=company, description=desc, job_url=url,
    )


def _one_hot(texts):
    """Deterministic unit-norm vectors: one hot dim seeded from each text."""
    from job_finder import embedder

    vecs = []
    for t in texts:
        v = np.zeros(embedder.DIM, dtype="float32")
        v[sum(bytearray(t.encode("utf-8"))) % embedder.DIM] = 1.0
        vecs.append(v)
    return np.vstack(vecs)


def _expected_vec(text):
    return _one_hot([text])[0]


def _install_fake_model(monkeypatch):
    """Make the embedder look installed with the deterministic encoder."""
    from job_finder import embedder

    monkeypatch.setattr(embedder, "is_available", lambda: True)
    monkeypatch.setattr(embedder, "encode", lambda texts, **kw: _one_hot(texts))


# ── degrade path (forced absent, never touches the network) ──


def test_embedder_degrades_without_model(monkeypatch):
    from job_finder import embedder

    # Force `from fastembed import ...` to raise, regardless of what's installed.
    monkeypatch.setitem(sys.modules, "fastembed", None)
    embedder.reset_for_tests()
    assert embedder.is_available() is False
    assert embedder.encode(["anything"]) is None
    assert embedder.encode_one("anything") is None


def test_index_is_noop_without_model(db, monkeypatch):
    from job_finder import embedder
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    monkeypatch.setitem(sys.modules, "fastembed", None)
    embedder.reset_for_tests()
    app = _save(db, "Data Engineer", "Stripe", "python sql", "http://a")
    result = index_embeddings(application_ids=[app.id])
    assert result["available"] is False
    assert result["indexed"] == 0
    ids, matrix = load_embeddings(application_ids=[app.id])
    assert ids == [] and matrix is None


# ── with a fake model ──


def test_index_embeds_with_exact_values_then_gates_on_hash(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder import embeddings_index as ix
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    rows = [
        ("Data Engineer", "Stripe", "python sql", "http://a"),
        ("Nurse Practitioner", "Kaiser", "clinic", "http://b"),
        ("Product Manager", "Figma", "roadmap", "http://c"),
    ]
    saved = {url: _save(db, t, c, d, url) for (t, c, d, url) in rows}

    candidate_ids = [row.id for row in saved.values()]
    first = index_embeddings(application_ids=candidate_ids)
    assert first == {"available": True, "indexed": 3, "skipped": 0, "pruned": 0}

    ids, matrix = load_embeddings(application_ids=candidate_ids)
    assert matrix.shape == (3, 384) and matrix.dtype == np.float32
    # Exact byte round-trip AND id->row alignment (the contract PR B relies on).
    for (t, c, d, url) in rows:
        app_id = saved[url].id
        expected = _expected_vec(ix.job_embedding_text(t, c, d))
        assert np.array_equal(matrix[ids.index(app_id)], expected)

    # Nothing changed -> re-run embeds nothing.
    again = index_embeddings(application_ids=candidate_ids)
    assert again["indexed"] == 0 and again["skipped"] == 3


def test_changed_description_re_embeds_only_that_row(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder.embeddings_index import index_embeddings

    a = _save(db, "Data Engineer", "Stripe", "python sql", "http://a")
    b = _save(db, "Nurse Practitioner", "Kaiser", "clinic", "http://b")
    candidate_ids = [a.id, b.id]
    index_embeddings(application_ids=candidate_ids)

    session = db.get_session()
    row = session.get(db.ApplicationRecord, a.id)
    row.description = "python sql dbt snowflake airflow"
    session.commit()

    result = index_embeddings(application_ids=candidate_ids)
    assert result["indexed"] == 1
    assert result["skipped"] == 1


def test_multi_batch_commits_then_defers_when_model_drops(db, monkeypatch):
    from job_finder import embedder
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    apps = [
        _save(db, f"Data Engineer {i}", "Co", f"desc {i}", f"http://{i}")
        for i in range(4)
    ]
    candidate_ids = [app.id for app in apps]

    calls = {"n": 0}

    def flaky_encode(texts, **kw):
        calls["n"] += 1
        return _one_hot(texts) if calls["n"] == 1 else None  # drops on 2nd batch

    monkeypatch.setattr(embedder, "is_available", lambda: True)
    monkeypatch.setattr(embedder, "encode", flaky_encode)

    # batch_size=2 over 4 rows: first chunk commits, second returns None -> defer
    first = index_embeddings(application_ids=candidate_ids, batch_size=2)
    assert first["indexed"] == 2
    ids, _ = load_embeddings(application_ids=candidate_ids)
    assert len(ids) == 2  # only the committed chunk landed, no partial garbage

    # Model recovers -> the deferred rows embed on the next pass, no re-embeds.
    monkeypatch.setattr(embedder, "encode", lambda texts, **kw: _one_hot(texts))
    second = index_embeddings(application_ids=candidate_ids, batch_size=2)
    assert second["indexed"] == 2
    assert second["skipped"] == 2
    ids2, matrix2 = load_embeddings(application_ids=candidate_ids)
    assert len(ids2) == 4 and matrix2.shape == (4, 384)


def test_prunes_orphan_vectors(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    a = _save(db, "Data Engineer", "Stripe", "python sql", "http://a")
    b = _save(db, "Nurse Practitioner", "Kaiser", "clinic", "http://b")
    candidate_ids = [a.id, b.id]
    index_embeddings(application_ids=candidate_ids)

    session = db.get_session()
    session.delete(session.get(db.ApplicationRecord, a.id))
    session.commit()

    result = index_embeddings(application_ids=candidate_ids)
    assert result["pruned"] == 1
    ids, matrix = load_embeddings(application_ids=candidate_ids)
    assert a.id not in ids and matrix.shape[0] == 1


# ── pure helpers ──


def test_job_embedding_text_and_hash(monkeypatch):
    from job_finder import embeddings_index as ix, embedder

    text = ix.job_embedding_text("Data Engineer", "Stripe", "  build pipelines  ")
    assert text == "Data Engineer . Stripe . build pipelines"
    # empty fields are dropped, not rendered as blank segments
    assert ix.job_embedding_text("Data Engineer", "", None) == "Data Engineer"
    # hash is stable and text-sensitive
    assert ix.content_hash(text) == ix.content_hash(text)
    assert ix.content_hash(text) != ix.content_hash(text + " x")
    # the model name is folded in, so a model swap forces a full re-embed
    baseline = ix.content_hash(text)
    monkeypatch.setattr(embedder, "MODEL_NAME", "some/other-model")
    assert ix.content_hash(text) != baseline


def test_index_requires_explicit_candidate_scope(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    with pytest.raises(ValueError, match="application_ids is required"):
        index_embeddings()
    with pytest.raises(ValueError, match="application_ids is required"):
        load_embeddings()


def test_scope_excludes_quests_and_other_workspaces(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    mine = db.save_application(
        job_title="Data Engineer", company="Mine", job_url="http://mine",
        workspace_id="ws-a", vertical="career",
    )
    theirs = db.save_application(
        job_title="Data Engineer", company="Theirs", job_url="http://theirs",
        workspace_id="ws-b", vertical="career",
    )
    quest = db.save_application(
        job_title="Paid study", company="Lab", job_url="http://quest",
        workspace_id="ws-a", vertical="study",
    )
    ids = [mine.id, theirs.id, quest.id]

    result = index_embeddings(application_ids=ids, workspace_id="ws-a")
    assert result["indexed"] == 1
    loaded_ids, matrix = load_embeddings(application_ids=ids, workspace_id="ws-a")
    assert loaded_ids == [mine.id]
    assert matrix.shape == (1, 384)


def test_loader_rejects_stale_or_malformed_vectors(db, monkeypatch):
    _install_fake_model(monkeypatch)
    from job_finder.embeddings_index import index_embeddings, load_embeddings

    app = _save(db, "Data Engineer", "Stripe", "python", "http://a")
    index_embeddings(application_ids=[app.id])
    session = db.get_session()
    stored = session.get(db.JobEmbedding, app.id)
    stored.dim = 12
    session.commit()

    ids, matrix = load_embeddings(application_ids=[app.id])
    assert ids == [] and matrix is None
