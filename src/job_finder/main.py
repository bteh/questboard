#!/usr/bin/env python
"""CLI entry points for the Job Finder pipeline."""

from __future__ import annotations

import os
import sys
import warnings

from dotenv import load_dotenv

load_dotenv()
warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    """Run the full job search pipeline with optional AI enhancement."""
    from job_finder.llm_client import LLMClient
    from job_finder.pipeline import JobFinderPipeline

    llm = LLMClient()
    has_llm = llm.is_configured and llm.is_available()

    print("\n" + "=" * 70)
    print("  JOB FINDER — Job Search Pipeline")
    print("=" * 70)
    if has_llm:
        info = llm.get_provider_info()
        print(f"  LLM: {info['model']} via {info['label']}")
    else:
        print("  LLM: not configured (basic keyword scoring)")
    print("  Searching 5+ job boards | Scoring against resume")
    print("=" * 70 + "\n")

    pipeline = JobFinderPipeline(llm=llm if has_llm else None)
    results = pipeline.run_full_pipeline(
        progress=lambda msg: print(f"  {msg}"),
        use_ai=has_llm,
    )

    print("\n" + "=" * 70)
    print(f"  Pipeline complete! {len(results)} jobs processed.")
    print("  DB: data/job_tracker.db")
    print("=" * 70 + "\n")

    return results


def search():
    """Run only the job search step (no scoring/optimization)."""
    import json

    from job_finder.pipeline import JobFinderPipeline

    pipeline = JobFinderPipeline()
    jobs = pipeline.search_all_jobs(
        progress=lambda msg: print(f"  {msg}"),
    )

    print(f"\nTotal unique jobs found: {len(jobs)}")

    # Save to file
    output_path = os.path.join(os.path.dirname(__file__), "output", "raw_search_results.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(jobs, f, indent=2)
    print(f"Saved to {output_path}")

    return jobs


def score():
    """Run search + scoring (basic keyword scoring, no LLM needed)."""
    from job_finder.llm_client import LLMClient
    from job_finder.pipeline import JobFinderPipeline

    llm = LLMClient()
    has_llm = llm.is_configured and llm.is_available()

    pipeline = JobFinderPipeline(llm=llm if has_llm else None)
    results = pipeline.run_full_pipeline(
        progress=lambda msg: print(f"  {msg}"),
        use_ai=has_llm,
    )

    print(f"\n{len(results)} jobs scored.")
    return results


if __name__ == "__main__":
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "search":
            search()
        elif command == "score":
            score()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m job_finder.main [search|score]")
    else:
        run()
