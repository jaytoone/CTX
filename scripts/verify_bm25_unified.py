#!/usr/bin/env python3
"""
verify_bm25_unified.py — sanity-check that eval and production use the same
canonical BM25 tokenizer/scorer after Task C unification.

Checks:
  1. adaptive_trigger._HAS_UNIFIED_TOKENIZER is True.
  2. tokenize() output is identical for the same input from both import paths.
  3. score_corpus_bm25() returns a numpy array with correct shape.
  4. BM25 ranking order is consistent: higher-relevance doc ranks above noise.

Exit 0 = all checks pass. Exit 1 = any check failed.
"""

import os
import sys

# Self-contained: ensure the project root is on sys.path so `src` is importable
# when running directly without PYTHONPATH (e.g. `python3 scripts/verify_bm25_unified.py`).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f": {detail}" if detail else ""))
    return condition


def main():
    ok = True
    print("=== BM25 Unification Verification ===\n")

    # ── Check 1: unified tokenizer flag ──────────────────────────────────────
    print("1. adaptive_trigger._HAS_UNIFIED_TOKENIZER")
    try:
        from src.retrieval.adaptive_trigger import _HAS_UNIFIED_TOKENIZER
        ok &= check("flag is True", _HAS_UNIFIED_TOKENIZER,
                    str(_HAS_UNIFIED_TOKENIZER))
    except Exception as e:
        ok &= check("import adaptive_trigger", False, str(e))

    # ── Check 2: tokenize() output identical from both paths ─────────────────
    print("\n2. tokenize() identical output from both import paths")
    try:
        from src.hooks._bm25.tokenizer import tokenize as tok_hooks
        from src.retrieval.adaptive_trigger import _bm25_tokenize as tok_eval

        samples = [
            ("BM25 retrieval search", False),
            ("한국어 검색 query test", True),
            ("AdaptiveTrigger retrieve", False),
        ]
        for text, drop_sw in samples:
            out_hooks = tok_hooks(text, drop_stopwords=drop_sw)
            out_eval = tok_eval(text, drop_stopwords=drop_sw)
            ok &= check(
                f"tokenize({text!r:.30}, drop_sw={drop_sw})",
                out_hooks == out_eval,
                f"hooks={out_hooks} eval={out_eval}" if out_hooks != out_eval else f"{out_hooks}",
            )
    except Exception as e:
        ok &= check("tokenize import/call", False, str(e))

    # ── Check 3: score_corpus_bm25() shape and type ──────────────────────────
    print("\n3. score_corpus_bm25() returns correct numpy array")
    try:
        import numpy as np
        from src.hooks._bm25.ranker import score_corpus_bm25
        from src.hooks._bm25.tokenizer import tokenize

        corpus_texts = [
            "BM25 tokenizer retrieval search",
            "unrelated noise document here",
            "CTX hook plugin memory recall",
        ]
        tokenized = [tokenize(t) for t in corpus_texts]
        q_tokens = tokenize("BM25 retrieval", drop_stopwords=True)
        scores = score_corpus_bm25(tokenized, q_tokens)

        ok &= check("returns ndarray", isinstance(scores, np.ndarray),
                    type(scores).__name__)
        ok &= check("shape matches corpus", len(scores) == len(corpus_texts),
                    f"len={len(scores)}")
        ok &= check("doc[0] > doc[1] (relevance order)",
                    scores[0] > scores[1],
                    f"scores={scores.round(3)}")
    except Exception as e:
        ok &= check("score_corpus_bm25", False, str(e))

    # ── Check 4: adaptive_trigger uses unified tokenizer in corpus build ──────
    print("\n4. AdaptiveTriggerRetriever builds corpus with unified tokenizer")
    try:
        import tempfile, os
        from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a minimal Python file to index
            src_file = os.path.join(tmpdir, "example.py")
            with open(src_file, "w") as f:
                f.write("def bm25_retrieval():\n    \"\"\"Canonical tokenizer test.\"\"\"\n    pass\n")
            retriever = AdaptiveTriggerRetriever(tmpdir)
            ok &= check("corpus non-empty", len(retriever._bm25_corpus) > 0,
                        f"len={len(retriever._bm25_corpus)}")
            ok &= check("BM25 index built", retriever.bm25 is not None)
            # Corpus tokens should include stemmed form (e.g., "retriev") from Porter stemmer
            flat_tokens = [t for tokens in retriever._bm25_corpus for t in tokens]
            # Porter stemmer is opt-in (CTX_STEM=1, requires nltk).
            # Check presence only when _STEMMER is active.
            from src.hooks._bm25.tokenizer import _STEMMER
            if _STEMMER is not None:
                ok &= check("porter stem present in corpus",
                            any(len(t) < 10 and t.startswith("retriev") for t in flat_tokens),
                            f"sample={flat_tokens[:10]}")
            else:
                check("porter stem (nltk absent — skipped)", True, "nltk not installed")
    except Exception as e:
        ok &= check("AdaptiveTriggerRetriever init", False, str(e))

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'ALL CHECKS PASSED' if ok else 'SOME CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
