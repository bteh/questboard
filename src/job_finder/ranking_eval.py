"""Offline evaluation for an owner-labeled hybrid-ranking pool."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from job_finder.hybrid_ranker import rank_jobs


def precision_at_k(labels: list[int], k: int = 10) -> float:
    if not labels:
        return 0.0
    window = labels[:k]
    return sum(label >= 2 for label in window) / k


def ndcg_at_k(labels: list[int], k: int = 10) -> float:
    def dcg(values: list[int]) -> float:
        return sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(values[:k]))

    ideal = dcg(sorted(labels, reverse=True))
    return dcg(labels) / ideal if ideal else 0.0


def _semantic_scores(jobs: list[dict], query: str) -> dict[int, float] | None:
    """Use the local artifact when present; otherwise evaluate lexical fallback."""
    try:
        from job_finder import embedder
        from job_finder.embeddings_index import job_embedding_text

        query_vector = embedder.encode_one(query, is_query=True)
        matrix = embedder.encode(
            [job_embedding_text(job.get("title"), job.get("company"), job.get("description")) for job in jobs]
        )
        if query_vector is None or matrix is None:
            return None
        return {int(job["db_id"]): float(vector @ query_vector) for job, vector in zip(jobs, matrix)}
    except Exception:
        return None


def evaluate_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    profile_results: list[dict[str, Any]] = []
    for profile in payload.get("profiles") or []:
        config = dict(profile.get("intent") or {})
        jobs = [dict(job) for job in profile.get("jobs") or []]
        for index, job in enumerate(jobs, 1):
            job["db_id"] = int(job.get("id") or index)
            job.setdefault("match_bucket", "primary")
        query = "\n".join(
            [
                *[str(v) for v in config.get("target_roles") or []],
                *[str(v) for v in config.get("keyword_searches") or []],
            ]
        ).strip() or str(profile.get("resume_text") or "")[:4000]
        semantic_query = f"{query}\n{str(profile.get('resume_text') or '')[:12000]}".strip()
        semantic = _semantic_scores(jobs, semantic_query)
        ranked = rank_jobs(jobs, query_text=query, config=config, semantic_scores=semantic)
        labels = [int(job.get("label") or 0) for job in ranked]
        baseline = sorted(jobs, key=lambda job: -float(job.get("baseline_score") or 0))
        baseline_labels = [int(job.get("label") or 0) for job in baseline]
        primary_top = [job for job in ranked if job.get("match_bucket") == "primary"][:10]
        profile_results.append(
            {
                "id": str(profile.get("id") or "profile"),
                "owner": bool(profile.get("owner")),
                "rank_source": ranked[0].get("rank_source") if ranked else None,
                "precision_at_10": precision_at_k(labels),
                "ndcg_at_10": ndcg_at_k(labels),
                "baseline_ndcg_at_10": ndcg_at_k(baseline_labels),
                "off_family_in_primary_top_10": sum(bool(job.get("off_family")) for job in primary_top),
                "constraint_violations_in_primary_top_10": sum(
                    job.get("hard_constraint_pass") is False for job in primary_top
                ),
            }
        )

    macro = sum(item["ndcg_at_10"] for item in profile_results) / max(len(profile_results), 1)
    baseline_macro = sum(item["baseline_ndcg_at_10"] for item in profile_results) / max(len(profile_results), 1)
    uplift = (macro / baseline_macro - 1.0) if baseline_macro else (1.0 if macro else 0.0)
    owner_rows = [item for item in profile_results if item["owner"]]
    checks = {
        "at_least_four_profiles": len(profile_results) >= 4,
        "owner_precision_at_10_gte_0_8": bool(owner_rows) and all(item["precision_at_10"] >= 0.8 for item in owner_rows),
        "macro_ndcg_uplift_gte_15pct": uplift >= 0.15,
        "no_off_family_primary_top_10": all(item["off_family_in_primary_top_10"] == 0 for item in profile_results),
        "hard_constraints_enforced": all(item["constraint_violations_in_primary_top_10"] == 0 for item in profile_results),
    }
    return {
        "profiles": profile_results,
        "macro_ndcg_at_10": macro,
        "baseline_macro_ndcg_at_10": baseline_macro,
        "ndcg_uplift": uplift,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Questboard hybrid ranking")
    parser.add_argument("dataset", type=Path, help="Owner-labeled JSON dataset")
    args = parser.parse_args()
    result = evaluate_dataset(json.loads(args.dataset.read_text(encoding="utf-8")))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
