# Hybrid ranking evaluation

Use an anonymized, owner-labeled pool before enabling `HYBRID_RANKING_ENABLED`
beyond the allowlist. Include at least four different profiles. Give every job
a relevance label from 0 to 3 and retain the current keyword score as the
baseline.

```json
{
  "profiles": [
    {
      "id": "owner",
      "owner": true,
      "resume_text": "anonymized resume text",
      "intent": {
        "target_roles": ["Data Engineering Manager"],
        "keyword_searches": ["data platform", "dbt"],
        "watchlist": [],
        "location_preferences": {"workplace_preference": "remote_friendly"},
        "compensation": {"min_base": 150000}
      },
      "jobs": [
        {
          "id": 1,
          "title": "Data Engineering Manager",
          "company": "Example",
          "description": "...",
          "label": 3,
          "baseline_score": 52.1,
          "match_bucket": "primary",
          "off_family": false,
          "hard_constraint_pass": true
        }
      ]
    }
  ]
}
```

Run:

```bash
PYTHONPATH=src python -m job_finder.ranking_eval data/hybrid-ranking-labels.json
```

The command exits nonzero unless owner precision@10 is at least 0.8, macro
nDCG@10 improves by at least 15% over the stored keyword baseline, no
off-family job enters a primary top ten, and all hard constraints hold. The
label file is intentionally not committed; keep resumes and identifying job
history out of the repository.
