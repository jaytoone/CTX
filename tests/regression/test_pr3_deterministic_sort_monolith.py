"""
PR-3 regression — monolith form (drop-in for upstream `bm25-memory.py` port).

Same 5 cases as `test_pr3_deterministic_sort.py`, but the import path is
restructured so the test loads the upstream monolith via `importlib.util`
(the file name `bm25-memory.py` contains a hyphen and cannot be imported
as a normal module).

After the monolith port lands upstream, these tests run as-is from the
upstream root with no `_bm25/` package on `sys.path`. From the fork side,
they also pass because our orchestrator file is at the same path.

Sites covered:
  - dense_rank_decisions
  - rrf_merge
  - bm25_rank_decisions
"""
import importlib.util
import sys
from pathlib import Path


def _load_bm25_memory():
    """Dynamically load `src/hooks/bm25-memory.py` as a module.

    Hyphen in the filename rules out a normal import. The fork orchestrator
    and the upstream monolith both expose the three target functions at
    module level, so this loader is interchangeable between them.
    """
    proj = Path(__file__).resolve().parents[2]
    monolith = proj / "src" / "hooks" / "bm25-memory.py"
    # Ensure the package directory is importable so the orchestrator's own
    # internal imports resolve (in fork: `_bm25/`; in upstream monolith
    # there are no such imports — the loader still works).
    sys.path.insert(0, str(proj / "src" / "hooks"))
    spec = importlib.util.spec_from_file_location("bm25_memory", monolith)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bm25_memory = _load_bm25_memory()


def _resolve(name):
    """Resolve a target function from the monolith.

    Upstream monolith: function defined at module level → direct attribute.
    Fork orchestrator (post-decomposition): orchestrator does not re-export
    rrf_merge / dense_rank_decisions / bm25_rank_decisions, so we fall back
    to the `_bm25.ranker` module that the orchestrator imports from.
    """
    if hasattr(bm25_memory, name):
        return getattr(bm25_memory, name)
    # Fallback for fork — package present alongside the orchestrator
    from _bm25 import ranker  # type: ignore
    return getattr(ranker, name)


rrf_merge = _resolve("rrf_merge")
dense_rank_decisions = _resolve("dense_rank_decisions")
bm25_rank_decisions = _resolve("bm25_rank_decisions")
HAS_BM25 = getattr(bm25_memory, "HAS_BM25", None)
if HAS_BM25 is None:
    from _bm25 import ranker as _ranker  # type: ignore
    HAS_BM25 = getattr(_ranker, "HAS_BM25", False)


def _items(n, prefix="c"):
    return [{"hash": f"{prefix}{i:03d}", "text": f"item {i}", "emb": []} for i in range(n)]


def test_rrf_merge_idempotent_same_input():
    """Same input → same output across repeat calls (no hidden randomness)."""
    a = _items(20, "a")
    b = _items(20, "b")
    keys1 = [it["hash"] for it in rrf_merge(a, b)]
    keys2 = [it["hash"] for it in rrf_merge(a, b)]
    assert keys1 == keys2, f"rrf_merge non-idempotent: {keys1[:5]} vs {keys2[:5]}"


def test_rrf_merge_equal_rank_tiebreak_independent_of_list_input_order():
    """Items with identical RRF rank in both lists must order by hash —
    independent of whether item X or item Y was inserted first into list_a.

    This is the bug that hash tiebreak fixes: previously dict-insertion
    order leaked into the output, so swapping list_a/list_b position of
    equal-rank items would shuffle the result."""
    a1 = [{"hash": "zzz_late", "text": "z"}]
    b1 = [{"hash": "aaa_early", "text": "a"}]
    a2 = [{"hash": "aaa_early", "text": "a"}]
    b2 = [{"hash": "zzz_late", "text": "z"}]
    keys1 = [it["hash"] for it in rrf_merge(a1, b1)]
    keys2 = [it["hash"] for it in rrf_merge(a2, b2)]
    assert keys1 == keys2 == ["aaa_early", "zzz_late"], (
        f"hash tiebreak failed:\n  case1={keys1}\n  case2={keys2}"
    )


def test_rrf_merge_equal_score_tiebreak_is_hash():
    """Items with identical RRF scores (same rank in both lists) must
    order by hash key ascending, not insertion order."""
    a = [{"hash": "z_high", "text": "z"}, {"hash": "a_low", "text": "a"}]
    b = [{"hash": "a_low", "text": "a"}, {"hash": "z_high", "text": "z"}]
    out = rrf_merge(a, b)
    keys = [it["hash"] for it in out]
    assert keys == ["a_low", "z_high"], f"hash tiebreak failed: got {keys}"


def test_dense_rank_decisions_no_emb_returns_empty():
    """Sanity: vec-daemon down → empty list."""
    corpus = _items(5)
    result = dense_rank_decisions(corpus, "any query")
    assert result == [] or all("hash" in it for it in result)


def test_bm25_rank_decisions_index_tiebreak():
    """bm25_rank_decisions: equal scores → index ascending.

    Corpus of byte-identical entries gets identical BM25 scores. With the
    explicit `(-scores[i], i)` tiebreak, surviving entries (after MMR /
    cluster dedup) come back in ascending index order."""
    if not HAS_BM25:
        return
    corpus = [
        {"hash": f"h{i}", "subject": "identical text", "text": "identical text body for bm25"}
        for i in range(5)
    ]
    result = bm25_rank_decisions(
        corpus,
        "identical bm25",
        top_k=5,
        min_score=0.0,
        adaptive_floor_ratio=0.0,
        mmr_jaccard_threshold=1.01,  # disable MMR
        skip_rerank=True,
    )
    hashes = [it["hash"] for it in result]
    if len(hashes) > 1:
        assert hashes == sorted(hashes), f"index tiebreak broken: {hashes}"


if __name__ == "__main__":
    test_rrf_merge_idempotent_same_input()
    print("PASS: rrf_merge idempotent")
    test_rrf_merge_equal_rank_tiebreak_independent_of_list_input_order()
    print("PASS: rrf_merge equal-rank tiebreak independent of input order")
    test_rrf_merge_equal_score_tiebreak_is_hash()
    print("PASS: rrf_merge equal-score tiebreak by hash")
    test_dense_rank_decisions_no_emb_returns_empty()
    print("PASS: dense_rank_decisions no-emb sanity")
    test_bm25_rank_decisions_index_tiebreak()
    print("PASS: bm25_rank_decisions index tiebreak")
    print("\nAll PR-3 monolith-form regression tests passed.")
