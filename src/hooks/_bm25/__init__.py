"""Public API for the _bm25 package.

For new code, prefer the package-level imports below. Existing submodule
imports (e.g. ``from _bm25.tokenizer import tokenize``) remain supported
and are not deprecated.

Examples::

    from _bm25 import tokenize, score_corpus_bm25
    from _bm25 import bm25_rank_decisions, hybrid_search_docs

Module-level state (e.g. AUTO_TUNE, last_retrieval_scores) is intentionally
not re-exported here — access it via submodule path
(``from _bm25.autotune import AUTO_TUNE``) to avoid Python module-binding
surprises.

Also consumed by src/retrieval/adaptive_trigger.py (eval pipeline) so that
eval and production share a single canonical tokenizer/scorer (Task C).
"""

# Tokenization
from .tokenizer import tokenize, expand_query_tokens

# BM25 ranking primitives
from .ranker import (
    score_corpus_bm25,
    bm25_rank_decisions,
    dense_rank_decisions,
    hybrid_rank_decisions,
    rrf_merge,
)

# Decision corpus (G1)
from .corpus import get_decision_corpus, get_git_head, build_decision_corpus

# Semantic rerank
from .rerank import semantic_rerank_filter

# Document / code / hooks search
from .docs_search import bm25_search_docs, hybrid_search_docs
from .code_search import search_files_by_grep, search_graph_for_prompt
from .hooks_search import search_hooks_files

# Output emission
from .output import emit_output

__all__ = [
    "tokenize", "expand_query_tokens",
    "score_corpus_bm25", "bm25_rank_decisions", "dense_rank_decisions",
    "hybrid_rank_decisions", "rrf_merge",
    "get_decision_corpus", "get_git_head", "build_decision_corpus",
    "semantic_rerank_filter",
    "bm25_search_docs", "hybrid_search_docs",
    "search_files_by_grep", "search_graph_for_prompt",
    "search_hooks_files",
    "emit_output",
]
