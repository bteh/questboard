from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from job_finder.ranking_eval import ndcg_at_k, precision_at_k


def test_precision_at_10_uses_relevance_two_as_the_cutoff():
    assert precision_at_k([3, 2, 1, 0, 3, 2, 2, 3, 2, 3]) == 0.8


def test_ndcg_rewards_putting_high_labels_first():
    assert ndcg_at_k([3, 2, 1, 0]) > ndcg_at_k([0, 1, 2, 3])
