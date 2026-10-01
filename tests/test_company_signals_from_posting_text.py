"""Funding and crypto signals read from a posting's own text.

Real case, Oct 1 2026: 391 of 464 rows on Brian's Find Work board carried
company_type "Unknown" and empty industry_tags, so the "Startups & founding"
chip showed 5 companies and the "Crypto" chip missed TRM Labs and Alpaca.
Scrapers never fill funding_stage or total_funding, yet 15 of those postings
state their round in the description, and TRM Labs calls itself blockchain
intelligence. Every rule in company_signals is pinned here by the sentence
that motivated it. The must-not-trigger cases are real rows too: AWS and
Bill.com say "startups" about their customers, Acquia sells digital asset
management (a CMS), and a bank lists "blockchain" once among initiatives.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "backend"), str(ROOT / "src")):
    if _path in sys.path:
        sys.path.remove(_path)
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(1, str(ROOT / "src"))

from job_finder.company_classifier import classify_company  # noqa: E402
from job_finder.company_signals import (  # noqa: E402
    fill_funding_from_text,
    funding_signals,
    industry_signals,
)
from job_finder.company_taxonomy import (  # noqa: E402
    classify_job_taxonomy,
    is_known_crypto_company,
)
from job_finder.models.company_signal_repair import (  # noqa: E402
    COMPANY_SIGNAL_REPAIR_NAME,
    COMPANY_SIGNAL_REPAIR_VERSION,
    repair_company_signals,
)

RENDER = (
    "In February 2026, we raised an additional $100M in Series C financing, "
    "bringing our total funding to $260M, to accelerate our vision."
)
HADRIAN = "Following our $1.37B Series D at a $7.87B valuation, we are scaling production."
DUNE = (
    "In February 2022, we announced our Series B funding round led by Coatue "
    "and Union Square Ventures, an important milestone."
)
TURQUOISE = (
    "Turquoise Health is a Series C price transparency platform for finance "
    "leaders across healthcare."
)
YIPIT = (
    "YipitData is the market-leading data and analytics firm for the disruptive "
    "economy and most recently raised $475M from The Carlyle Group at a "
    "valuation of over $1B."
)
ALPACA = (
    "Alpaca is proudly backed by $400 million in funding from top-tier global "
    "investors including Portage Ventures, Spark Capital, Tribe Capital, "
    "Social Leverage, Horizons Ventures, SBI Group, Derayah Financial, Unbound, "
    "Peak XV, Elefund, and Y Combinator."
)
LEGION = (
    "Legion Health is backed by Y Combinator, leading venture capital firms, "
    "and founders from Function Health."
)
MEDSCOUT = "We've raised $31.8M from incredible investors to redefine this category."
CLARIUM = (
    "Founded in 2020, Clarium has raised $43M in total funding. Our Series A "
    "was led by Northzone, with participation from General Catalyst."
)
SHIELD = (
    "Shield AI is a venture-backed defense-tech company with the mission of "
    "protecting service members and civilians."
)
ABACUS = (
    "Abacus Insights is a high-growth, VC-backed company. Backed by $100M from "
    "top investors, we're tackling big challenges."
)
VANNEVAR = (
    "In just three years, we grew from $3M to $80M in ARR, achieved early "
    "profitability, and reached unicorn status."
)
TRM = (
    "TRM Labs is a blockchain intelligence company. Our products help crypto "
    "compliance teams detect fraud and financial crime."
)
AWS = "Amazon Web Services serves millions of customers, from startups to enterprises."
BILL = "At Bill.com we help businesses from startups to established brands."
ACQUIA = (
    "Acquia brings together Content Management, Digital Asset Management, and "
    "Product Information Management in a single AI-powered platform."
)
BANK = (
    "Our technology initiatives include cloud migration, blockchain, machine "
    "learning, and open banking APIs."
)
STAMP = "2026-07-01T00:00:00+00:00"


# ---------------------------------------------------------------- funding text


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        (RENDER, {"funding_stage": "series c", "total_funding": "$100M"}),
        (HADRIAN, {"funding_stage": "series d", "total_funding": "$1.37B"}),
        (DUNE, {"funding_stage": "series b"}),
        (TURQUOISE, {"funding_stage": "series c"}),
        (YIPIT, {"total_funding": "$475M"}),
        (ALPACA, {"funding_stage": "seed", "total_funding": "$400M"}),
        (LEGION, {"funding_stage": "seed"}),
        (MEDSCOUT, {"total_funding": "$31.8M"}),
        (CLARIUM, {"funding_stage": "series a", "total_funding": "$43M"}),
        (SHIELD, {"funding_stage": "venture-backed"}),
        (ABACUS, {"funding_stage": "venture-backed", "total_funding": "$100M"}),
        (VANNEVAR, {"funding_stage": "unicorn"}),
    ],
    ids=[
        "render", "hadrian", "dune", "turquoise", "yipitdata", "alpaca",
        "legion", "medscout", "clarium", "shield-ai", "abacus", "vannevar",
    ],
)
def test_real_sentences_map_to_stage_and_amount(sentence: str, expected: dict) -> None:
    assert funding_signals(sentence) == expected


def test_the_series_letter_beats_y_combinator() -> None:
    """Alpaca row 5967 names Y Combinator and a Series D in the same text."""
    assert funding_signals(ALPACA + " We closed our Series D in 2024.")["funding_stage"] == "series d"


def test_the_latest_series_letter_wins() -> None:
    text_ = "Our Series A was led by Northzone. In 2025 we closed our Series C."
    assert funding_signals(text_)["funding_stage"] == "series c"


def test_pre_seed_is_not_read_as_seed() -> None:
    assert funding_signals("We closed our pre-seed round last spring.") == {
        "funding_stage": "pre-seed"
    }


def test_vannevar_arr_figures_are_not_funding() -> None:
    assert "total_funding" not in funding_signals(VANNEVAR)


def test_hadrian_valuation_is_not_the_raise() -> None:
    assert funding_signals(HADRIAN)["total_funding"] == "$1.37B"


@pytest.mark.parametrize("sentence", [AWS, BILL, ACQUIA, BANK], ids=["aws", "bill", "acquia", "bank"])
def test_customer_talk_and_cms_copy_carry_no_funding_signal(sentence: str) -> None:
    assert funding_signals(sentence) == {}


def test_a_series_range_about_customers_is_not_our_round() -> None:
    assert funding_signals("We partner with Series A-C startups on their data stack.") == {}


def test_a_candidate_called_a_unicorn_is_not_a_unicorn_company() -> None:
    assert funding_signals("We are looking for a unicorn who can design and code.") == {}


def test_empty_text_yields_nothing() -> None:
    assert funding_signals("") == {}


# Second audit over the 292 rows the repair touched on the Oct 1 copy: the
# amount rules bit on figures that sit next to the wrong noun. Each case
# below is the real sentence that was mis-read.


@pytest.mark.parametrize(
    ("sentence", "expected"),
    [
        ("Our latest $70M raise at a $7B valuation reflects the confidence the market has placed in us.",
         {"total_funding": "$70M"}),
        ("Function recently announced a $298M Series B and is entering its next chapter of growth.",
         {"funding_stage": "series b", "total_funding": "$298M"}),
        ("We're a VC-funded startup (recently raised $51M Series C) building an orchestrator.",
         {"funding_stage": "series c", "total_funding": "$51M"}),
        ("With more than $100 million raised in recent funding, including a $53 million round.",
         {"total_funding": "$100M"}),
        ("With $125M raised at Series B from IVP, Sequoia, Benchmark.",
         {"funding_stage": "series b", "total_funding": "$125M"}),
        ("ShopMy recently became a unicorn, raising at a $1.5B valuation with backing from Bessemer.",
         {"funding_stage": "unicorn"}),
        ("Quvia is a fast growing, Series A company backed by Colombia Capital ($5B+ in fund commitments.",
         {"funding_stage": "series a"}),
        ("Founded in 2007, we scaled the business with less than $3 million in outside funding until "
         "2021, when we did a traditional IPO on the Nasdaq stock exchange.",
         {"funding_stage": "public", "total_funding": "$3M"}),
    ],
    ids=["commure", "function-health", "spacelift", "twin-health", "langchain", "shopmy", "quvia", "backblaze"],
)
def test_amounts_land_on_the_raise_not_the_valuation(sentence: str, expected: dict) -> None:
    assert funding_signals(sentence) == expected


@pytest.mark.parametrize(
    "sentence",
    [
        "While hypersonic systems offer high speeds, their exorbitant costs exceeding $50 million per round limit the military.",
        "TailorMed has supported over 75 million patients and secured more than $7.4 billion in financial assistance since 2020.",
        "Our clients have raised over $5B in aggregate and are backed by companies like OpenAI, a16z.",
        "Our client is a fast-growing, Series A-backed AI company delivering agentic AI solutions.",
        "Join an early-stage company led by serial entrepreneur Andrew Filev (founder of a unicorn startup).",
        "A talent network for founding product designer roles at VC-backed startups.",
        "The entrepreneurial spirit of a start-up backed by the scale and resources of a $1 billion company.",
        "Since our founding, we have deployed more than $1 billion in financing to small businesses.",
        "Our primary clients today are cutting-edge, venture-backed AI SaaS startups and VC firms.",
        "We're already on 500+ active projects with 100K+ workers, securing over $100B in construction value.",
        "Experience in accounting and reporting for PE and/or VC funded portfolio companies.",
        "We recently closed a growth investment from Main Street Capital Corporation (NYSE: MAIN).",
    ],
    ids=["dow-army", "tailormed", "pearl-talent", "toptal", "zencoder", "signalfire", "ensemble",
         "accion", "ignition", "odin", "system-six", "cybermedia"],
)
def test_figures_about_customers_valuations_and_other_companies_are_not_ours(sentence: str) -> None:
    assert funding_signals(sentence) == {}


def test_quvia_keeps_its_series_a_and_not_its_investors_fund_size() -> None:
    sentence = (
        "Quvia is backed by Columbia Capital, a respected venture capital firm founded in 1989 "
        "that has raised over $5 Bn of fund commitments. Quvia is a fast growing, Series A company."
    )
    assert funding_signals(sentence) == {"funding_stage": "series a"}


def test_a_listed_company_reads_its_own_ticker() -> None:
    assert funding_signals("Samsara (NYSE: IOT) is the pioneer of the Connected Operations Cloud.") == {
        "funding_stage": "public"
    }


def test_backblaze_tiers_as_a_public_company_not_a_startup() -> None:
    assert classify_company("Backblaze", funding_stage="public", total_funding="$3M") == "Midsize"


# --------------------------------------------------------------- industry text


def test_trm_labs_text_is_crypto() -> None:
    assert industry_signals("TRM Labs", TRM) == ["crypto"]


def test_acquia_digital_asset_management_is_not_crypto() -> None:
    assert industry_signals("Acquia", ACQUIA) == []


def test_one_blockchain_mention_in_a_bank_list_is_not_crypto() -> None:
    assert industry_signals("First Horizon Bank", BANK) == []


def test_aws_and_bill_com_are_not_crypto() -> None:
    assert industry_signals("Amazon Web Services", AWS) == []
    assert industry_signals("Bill.com", BILL) == []


def test_a_crypto_word_in_the_company_name_is_enough() -> None:
    assert industry_signals("Crypto.com", "Build data pipelines.") == ["crypto"]
    assert industry_signals("Blockchain.com", "") == ["crypto"]


def test_defi_does_not_match_inside_definitive() -> None:
    assert industry_signals("Definitive Healthcare", "We define the market.") == []


def test_two_distinct_words_are_needed_not_one_word_twice() -> None:
    assert industry_signals("Acme", "blockchain data, blockchain pipelines, blockchains") == []
    assert industry_signals("Acme", "onchain data for stablecoin issuers") == ["crypto"]


# ---------------------------------------------------------------- classifier


def test_render_and_dune_tier_from_their_text_signals() -> None:
    assert classify_company("Render", funding_stage="series c", total_funding="$100M") == "Elite Startup"
    assert classify_company("Dune", funding_stage="series b") == "Growth Stage"


def test_venture_backed_and_unicorn_tiers() -> None:
    assert classify_company("Shield AI", funding_stage="venture-backed") == "Growth Stage"
    assert classify_company("Abacus Insights", funding_stage="vc-backed") == "Growth Stage"
    assert classify_company("Vannevar Labs", funding_stage="unicorn") == "Elite Startup"


def test_other_real_rows_tier_as_startups() -> None:
    assert classify_company("Hadrian Automation", funding_stage="series d", total_funding="$1.37B") == "Elite Startup"
    assert classify_company("Legion Health", funding_stage="seed") == "Early Startup"
    assert classify_company("YipitData", total_funding="$475M") == "Elite Startup"
    assert classify_company("Medscout", total_funding="$31.8M") == "Growth Stage"


# ----------------------------------------------------------------- catalog


def test_trm_labs_and_alpaca_are_catalog_crypto_companies() -> None:
    assert is_known_crypto_company("TRM Labs")
    assert is_known_crypto_company("Trm Labs")
    assert is_known_crypto_company("Alpaca")
    industries, _ = classify_job_taxonomy(
        company="TRM Labs", source="ashby", title="Data Engineer",
        description="Build ETL pipelines at petabyte scale.",
    )
    assert industries == ["crypto"]


# --------------------------------------------------------------- save path


def test_fill_funding_from_text_fills_only_empty_fields() -> None:
    job = {"company": "Render", "description": RENDER}
    fill_funding_from_text(job)
    assert (job["funding_stage"], job["total_funding"]) == ("series c", "$100M")

    kept = {"company": "Render", "description": RENDER, "funding_stage": "Series D"}
    fill_funding_from_text(kept)
    assert kept["funding_stage"] == "Series D"
    assert kept["total_funding"] == "$100M"

    bare = {"company": "AWS", "description": AWS}
    fill_funding_from_text(bare)
    assert "funding_stage" not in bare and "total_funding" not in bare


def test_scoring_pass_zero_tiers_render_from_its_description() -> None:
    from job_finder.pipeline import JobFinderPipeline

    pipe = JobFinderPipeline(llm=None, profile=None)
    pipe._keyword_score_single = lambda job, resume, cache: None  # type: ignore[method-assign]
    jobs = [
        {"title": "Data Engineer", "company": "Render", "url": "https://x/render",
         "source": "ashby", "description": RENDER},
        {"title": "Data Engineer", "company": "Amazon Web Services", "url": "https://x/aws",
         "source": "linkedin", "description": AWS},
    ]
    pipe.score_jobs(jobs, "resume", use_ai=False)
    by_company = {job["company"]: job for job in jobs}
    assert by_company["Render"]["company_type"] == "Elite Startup"
    assert by_company["Render"]["funding_stage"] == "series c"
    assert by_company["Amazon Web Services"]["company_type"] == "Unknown"


@pytest.fixture()
def db_session(tmp_path, monkeypatch):
    """Real schema on a temp file; never the desktop runtime's DB.

    init_db runs the startup repairs during migration, which records the
    marker before any rows exist, so repair tests here pass force=True.
    """
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOSTED_MODE", "false")
    database = importlib.import_module("job_finder.models.database")
    database.init_db(str(tmp_path / "job_tracker.db"))
    session = database._SessionLocal()
    yield session
    session.close()
    database._SessionLocal.remove()


def test_save_path_stores_the_stage_and_the_name_signal(db_session) -> None:
    database = importlib.import_module("job_finder.models.database")

    job = {"company": "Render", "description": RENDER}
    fill_funding_from_text(job)
    rec = database.save_application(
        job_title="Data Engineer", company="Render", location="Remote",
        job_url="https://x/render", source="ashby", description=RENDER,
        funding_stage=job.get("funding_stage"), total_funding=job.get("total_funding"),
        company_type=classify_company("Render", job.get("funding_stage"), job.get("total_funding")),
    )
    stored = db_session.get(database.ApplicationRecord, rec.id)
    assert (stored.funding_stage, stored.total_funding) == ("series c", "$100M")
    assert stored.company_type == "Elite Startup"

    named = database.save_application(
        job_title="Data Engineer", company="Web3 Payroll Inc", location="Remote",
        job_url="https://x/web3payroll", source="greenhouse",
        description="Build data pipelines for payroll.",
    )
    assert '"crypto"' in db_session.get(database.ApplicationRecord, named.id).industry_tags


def test_a_rescrape_fills_an_empty_stage_without_reshuffling(db_session) -> None:
    database = importlib.import_module("job_finder.models.database")

    first = database.save_application(
        job_title="Data Engineer", company="Render", location="Remote",
        job_url="https://x/render", source="ashby", description="Short teaser.",
    )
    assert first.funding_stage in (None, "")
    stamp = first.updated_at
    second = database.save_application(
        job_title="Data Engineer", company="Render", location="Remote",
        job_url="https://x/render", source="ashby", description=RENDER,
        funding_stage="series c", total_funding="$100M",
    )
    assert second.id == first.id
    assert (second.funding_stage, second.total_funding) == ("series c", "$100M")
    assert second.updated_at == stamp, "the fill alone must not bump the log stamp"
    third = database.save_application(
        job_title="Data Engineer", company="Render", location="Remote",
        job_url="https://x/render", source="ashby", description=RENDER,
        funding_stage="series d", total_funding="$1B",
    )
    assert (third.funding_stage, third.total_funding) == ("series c", "$100M")


# ------------------------------------------------------------------ repair


@pytest.fixture()
def engine(tmp_path):
    """Temp DB only; the desktop runtime's DB is a symlink to the live board."""
    eng = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, company VARCHAR, source VARCHAR,"
            " company_type VARCHAR, funding_stage VARCHAR, total_funding VARCHAR,"
            " industry_tags TEXT, description TEXT, updated_at VARCHAR)"
        ))
    return eng


def _add(engine, **kw) -> None:
    row = {
        "company": "Render", "source": "ashby", "company_type": "Unknown",
        "funding_stage": None, "total_funding": None, "industry_tags": "[]",
        "description": RENDER, "updated_at": STAMP,
    }
    row.update(kw)
    cols = ", ".join(row)
    binds = ", ".join(f":{k}" for k in row)
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO applications ({cols}) VALUES ({binds})"), row)


def _rows(engine) -> list[tuple]:
    with engine.begin() as conn:
        return [tuple(r) for r in conn.execute(text(
            "SELECT company, company_type, funding_stage, total_funding, industry_tags "
            "FROM applications ORDER BY id"
        ))]


def test_repair_retiers_render_tags_trm_and_leaves_aws_unknown(engine) -> None:
    _add(engine)
    _add(engine, company="Trm Labs", description=TRM)
    _add(engine, company="Amazon Web Services (AWS)", source="linkedin", description=AWS)
    assert repair_company_signals(engine) == 2
    assert _rows(engine) == [
        ("Render", "Elite Startup", "series c", "$100M", "[]"),
        ("Trm Labs", "Unknown", None, None, '["crypto"]'),
        ("Amazon Web Services (AWS)", "Unknown", None, None, "[]"),
    ]


def test_repair_tags_a_catalog_crypto_company_whose_text_is_vague(engine) -> None:
    """TRM Labs row 19608 only says "blockchain"; the catalog identity carries it."""
    _add(engine, company="TRM Labs", description="Analyze blockchain transaction activity at petabyte scale.")
    _add(engine, company="Alpaca", source="greenhouse",
         description="Brokerage infrastructure for stocks, ETFs, options, crypto and more.")
    assert repair_company_signals(engine) == 2
    assert [r[4] for r in _rows(engine)] == ['["crypto"]', '["crypto"]']


def test_repair_keeps_tiers_that_outrank_a_text_mention(engine) -> None:
    """A row tiered Enterprise by head count keeps it even if the text names a round."""
    _add(engine, company="Fidelity Investments", company_type="Enterprise",
         description="We invest in Series B companies. Our Series B fund is $2B.")
    assert repair_company_signals(engine) == 0
    assert _rows(engine)[0][1] == "Enterprise"


def test_repair_does_not_reshuffle_the_board(engine) -> None:
    _add(engine)
    repair_company_signals(engine)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT updated_at FROM applications")).scalar() == STAMP


def test_repair_records_its_marker_and_a_second_run_touches_nothing(engine) -> None:
    _add(engine)
    assert repair_company_signals(engine) == 1
    with engine.begin() as conn:
        version = conn.execute(
            text("SELECT version FROM data_repairs WHERE name = :n"),
            {"n": COMPANY_SIGNAL_REPAIR_NAME},
        ).scalar()
    assert version == COMPANY_SIGNAL_REPAIR_VERSION
    _add(engine, company="Hadrian Automation", description=HADRIAN)
    assert repair_company_signals(engine) == 0, "version marker should skip"
    assert repair_company_signals(engine, force=True) == 1
    assert repair_company_signals(engine, force=True) == 0, "idempotent: nothing left to change"


def test_repair_walks_every_batch(engine) -> None:
    for i in range(1_100):
        _add(engine, company=f"Co {i}", description=RENDER if i % 100 == 0 else AWS)
    assert repair_company_signals(engine) == 11


def test_repair_leaves_side_quest_rows_alone(tmp_path) -> None:
    """A casting call ("Dating Series A major streaming platform") is not a Series A."""
    eng = create_engine(f"sqlite:///{tmp_path / 'quests.db'}")
    with eng.begin() as conn:
        conn.execute(text(
            "CREATE TABLE applications ("
            " id INTEGER PRIMARY KEY, company VARCHAR, vertical VARCHAR,"
            " company_type VARCHAR, funding_stage VARCHAR, total_funding VARCHAR,"
            " industry_tags TEXT, description TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO applications (company, vertical, company_type, industry_tags, description) VALUES "
            "('', 'camera', 'Unknown', '[]', "
            "'Casting Singles for New Plastic Surgery and Dating Series A major streaming platform is now casting'), "
            "('Render', 'career', 'Unknown', '[]', :render)"
        ), {"render": RENDER})
    assert repair_company_signals(eng) == 1
    with eng.begin() as conn:
        assert conn.execute(text(
            "SELECT company_type, funding_stage FROM applications ORDER BY id"
        )).fetchall() == [("Unknown", None), ("Elite Startup", "series c")]


def test_an_empty_database_does_not_crash(tmp_path) -> None:
    eng = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    assert repair_company_signals(eng) == 0


def test_shelves_pick_up_render_and_trm_after_the_repair(db_session) -> None:
    database = importlib.import_module("job_finder.models.database")
    from app.services import application_service

    ApplicationRecord = database.ApplicationRecord
    db_session.add_all([
        ApplicationRecord(
            job_title="Data Engineer", company="Render", location="Remote",
            source="ashby", job_url="https://x/render", company_type="Unknown",
            industry_tags="[]", description=RENDER,
        ),
        ApplicationRecord(
            job_title="Data Engineer", company="Trm Labs", location="Remote",
            source="ashby", job_url="https://x/trm", company_type="Unknown",
            industry_tags="[]", description=TRM,
        ),
        ApplicationRecord(
            job_title="Data Engineer", company="Amazon Web Services", location="Remote",
            source="linkedin", job_url="https://x/aws", company_type="Unknown",
            industry_tags="[]", description=AWS,
        ),
    ])
    db_session.commit()

    startup = application_service.source_category_condition(ApplicationRecord, "startup")
    crypto = application_service.source_category_condition(ApplicationRecord, "crypto")
    assert {r.company for r in db_session.query(ApplicationRecord).filter(startup)} == set()
    assert {r.company for r in db_session.query(ApplicationRecord).filter(crypto)} == set()

    assert repair_company_signals(database._engine, force=True) == 2
    db_session.expire_all()

    assert {r.company for r in db_session.query(ApplicationRecord).filter(startup)} == {"Render"}
    assert {r.company for r in db_session.query(ApplicationRecord).filter(crypto)} == {"Trm Labs"}
    aws = db_session.query(ApplicationRecord).filter_by(company="Amazon Web Services").one()
    assert aws.company_type == "Unknown"
