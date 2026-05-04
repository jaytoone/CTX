"""
_bm25 — internal package for bm25-memory.py modules.

Public re-exports so orchestrator can do:
    from _bm25.tokenizer import tokenize, expand_query_tokens
    from _bm25.autotune import AUTO_TUNE, AUTO_TUNE_ACTIVE
    etc.

Also consumed by src/retrieval/adaptive_trigger.py (eval pipeline) so that
eval and production share a single canonical tokenizer/scorer (Task C).
"""
