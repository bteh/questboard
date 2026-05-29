"""Crypto/web3 relevance: vocabulary, company tagging, and the shared
role-filter predicate that keeps filter_by_role and the DB purge in lockstep.
"""

from __future__ import annotations

import pytest

from job_finder.tools.scrapers._utils import (
    _has_crypto_terms,
    _match_roles_crypto,
    crypto_company_slugs,
    is_crypto_company,
    job_passes_role_filter,
)


# ── Vocabulary ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "title",
    [
        "NFT Platform Engineer",
        "DAO Operations Lead",
        "Staking Product Manager",
        "Validator Operations Engineer",
        "Wallet Engineer",
        "Ethereum Core Developer",
        "Solana Engineer",
        "Onchain Analyst",
        "Dapp Developer",
        "Smart Contract Engineer",
        "Senior Solidity Engineer",
        "DeFi Associate",
        "Web3 BD Manager",
        "ZK Circuit Researcher",
        "Blockchain Engineer",
    ],
)
def test_new_crypto_vocab_matches(title):
    # role does not word-match; the crypto term is what rescues the title.
    assert _match_roles_crypto(title, ["data engineer"]) is True


@pytest.mark.parametrize(
    "title",
    [
        "Rust Engineer",            # 'rust' dropped — too generic / non-crypto
        "Senior Marketing Manager",
        "Registered Nurse",
        "Node.js Developer",        # 'node' dropped — too generic
    ],
)
def test_non_crypto_titles_not_rescued(title):
    assert _match_roles_crypto(title, ["data engineer"]) is False


def test_match_roles_crypto_title_only_ignores_clean_signal_in_other_fields():
    # Matching is title-only on purpose — a generic title is NOT rescued by a
    # crypto term elsewhere, because board/tag metadata is too noisy.
    assert _match_roles_crypto("Senior Backend Engineer", ["data engineer"]) is False


def test_match_roles_crypto_still_honors_plain_role_match():
    assert _match_roles_crypto("Senior Data Engineer", ["data engineer"]) is True


def test_zk_whole_word_still_matches():
    # Regression: 'zk' reclassified to whole-word must still catch this title.
    assert _has_crypto_terms("ZK Circuit Researcher") is True


# ── Crypto company tagging ───────────────────────────────────────────────────
def test_is_crypto_company_seed_slug():
    assert is_crypto_company("alchemy")       # Ashby crypto seed
    assert is_crypto_company("magiceden")
    assert is_crypto_company("Magic Eden")    # cleaned-name form normalizes too
    assert is_crypto_company("phantom")


def test_is_crypto_company_negative():
    assert not is_crypto_company("stripe")
    assert not is_crypto_company("chainguard")  # container security, not crypto
    assert not is_crypto_company("")
    assert not is_crypto_company(None)


def test_crypto_company_slugs_nonempty():
    assert "alchemy" in crypto_company_slugs()


# ── Shared parity predicate ──────────────────────────────────────────────────
def _job(**kw):
    base = {"title": "", "source": "", "company": "", "is_remote": False, "description": ""}
    base.update(kw)
    return base


def _passes(job, roles="data engineer", strictness="balanced", mode="all_significant", founding=True):
    return job_passes_role_filter(
        job, [roles], match_mode=mode, include_founding=founding, strictness=strictness
    )


def test_parity_crypto_company_ats_job_passes_balanced():
    assert _passes(_job(title="Solidity Engineer", source="ashby", company="Alchemy"))


def test_parity_cryptojobslist_job_passes():
    assert _passes(_job(title="DeFi Associate", source="cryptojobslist", is_remote=True))


def test_parity_non_crypto_remotive_dropped():
    assert not _passes(
        _job(title="Marketing Engineer", source="remotive", company="Acme", is_remote=True)
    )


def test_parity_strict_drops_crypto():
    assert not _passes(
        _job(title="Solidity Engineer", source="ashby", company="Alchemy"),
        strictness="strict",
        mode="exact",
        founding=False,
    )


def test_parity_balanced_nonremote_anyword_rescue():
    # Non-remote + balanced → any_word rescue keeps a variant title via 'engineer'.
    assert _passes(
        _job(title="ML Platform Engineer", source="greenhouse", company="Acme", is_remote=False)
    )


def test_jobspy_namesake_company_not_crypto_rescued():
    # A non-crypto JobSpy job whose company NAME collides with a crypto base
    # slug (e.g. "Polygon" the games site) must NOT get crypto matching — the
    # company-name fallback is for ATS sources (curated slugs) only. Otherwise
    # crypto-titled off-role jobs leak into non-crypto searches.
    j = _job(title="Blockchain Marketing Lead", source="indeed", company="Polygon", is_remote=True)
    assert not _passes(j)


def test_crypto_company_slug_name_roundtrip_parity():
    # Guardrail: the scrape-time crypto flag is set from the SLUG, but the DB
    # purge re-derives crypto-domain from the cleaned display NAME. They must
    # agree for every crypto slug or the purge could delete a kept ATS job.
    from job_finder.tools.scrapers._utils import _clean_company_name

    for slug in crypto_company_slugs():
        assert is_crypto_company(_clean_company_name(slug)) == is_crypto_company(slug), slug


# ── ATS scrapers apply crypto matching at scrape time for crypto companies ────
def test_ashby_crypto_company_keeps_crypto_titles(monkeypatch):
    from job_finder.tools.scrapers import ashby

    payload = {
        "jobs": [
            {"title": "Solidity Engineer", "location": "Remote", "jobUrl": "u1"},
            {"title": "Marketing Manager", "location": "Remote", "jobUrl": "u2"},
        ]
    }
    monkeypatch.setattr(ashby, "_get_json", lambda *a, **k: payload)
    jobs = ashby._fetch_company_jobs(
        "alchemy", ["data engineer"], match_mode="all_significant", include_founding=True
    )
    titles = {j["title"] for j in jobs}
    assert "Solidity Engineer" in titles      # crypto company → crypto rescue
    assert "Marketing Manager" not in titles   # not crypto, no role match


def test_ashby_non_crypto_company_stays_strict(monkeypatch):
    from job_finder.tools.scrapers import ashby

    payload = {"jobs": [{"title": "Solidity Engineer", "location": "Remote", "jobUrl": "u1"}]}
    monkeypatch.setattr(ashby, "_get_json", lambda *a, **k: payload)
    jobs = ashby._fetch_company_jobs(
        "stripe", ["data engineer"], match_mode="all_significant", include_founding=True
    )
    assert jobs == []   # non-crypto company → strict matcher drops the crypto title
