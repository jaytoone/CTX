#!/usr/bin/env python3
"""
bm25-memory: BM25-based reactive memory for Claude Code.
Replaces git-memory.py (G1 proactive, recall 0.169) + g2-augment.py (G2 graph).

G1: ALL git decision commits → BM25 query-time ranking → top-7 relevant to prompt
    Keyword-identical: Structural Recall@7=1.000 (inflated, token overlap=0.476)
    Paraphrase fair eval: Structural Recall@7=0.627 (bias=0.373, 20260410 g1_fair_eval.py)
    Type2/3/4 (why/what/rationale): Structural Recall@7=0.667
    Combined fair Recall@7=0.634 (71 queries) — vs proactive 0.169 → 3.7x improvement
    Fix: CTX YYYYMMDD-prefix commits now recognized as decisions

G2a: docs/research/*.md + CLAUDE.md + MEMORY.md → BM25 → top-5 relevant chunks
     Keyword-identical eval: 10/10 (1.000) | Paraphrase eval: 7/10 (0.700)
     Note: 1.000 is inflated — paraphrase 0.700 is the honest fairness-adjusted score
G2b: codebase graph (codebase-memory-mcp SQLite) → relevant code files (project-internal only)
     Fallback: git grep -c keyword ranking when no DB available
G2b-hooks: ~/.claude/hooks/*.py BM25 search (triggered by "hook/훅/bm25-memory/auto-index/..." keywords)
     Directly indexes hook file function signatures — solves G2b external file gap

Cache: .omc/decision_corpus.json (auto-invalidated on git HEAD change)
"""
import json
import os
import sys
from pathlib import Path

# ── _bm25 package import (script entry-point path hack) ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bm25.autotune import (  # noqa: E402
    AUTO_TUNE as _AUTO_TUNE, AUTO_TUNE_ACTIVE as _AUTO_TUNE_ACTIVE,
    get_g1_top_k as _get_g1_top_k, get_g2d_top_k as _get_g2d_top_k,
)
from _bm25.rerank import (  # noqa: E402
    VEC_SOCK as _VEC_SOCK, VEC_DISABLED as _VEC_DISABLED,
    BGE_SOCK as _BGE_SOCK, USE_CROSS_ENCODER as _USE_CROSS_ENCODER,
)
from _bm25.corpus import get_decision_corpus, _classify_query_type  # noqa: E402
from _bm25.ranker import (  # noqa: E402
    hybrid_rank_decisions, last_retrieval_scores as _ranker_scores,
)
from _bm25.docs_search import build_docs_bm25, hybrid_search_docs  # noqa: E402
from _bm25.code_search import (  # noqa: E402
    extract_keywords, find_db, log_retrieved_nodes,
    check_and_trigger_reindex, search_graph_for_prompt, search_files_by_grep,
)
from _bm25.hooks_search import search_hooks_files, _has_hooks_keywords  # noqa: E402
from _bm25.session import (  # noqa: E402
    get_world_model, get_session_decisions, consume_pending_decisions,
)
from _bm25.injection import write_injection_record  # noqa: E402
from _bm25.output import build_header_lines, emit_output  # noqa: E402

RICH = "--rich" in sys.argv

# _last_retrieval_scores: alias to ranker's module-level dict so orchestrator
# can clear/read it without changing call sites.
_last_retrieval_scores = _ranker_scores


def _log_event(event_type, payload):
    """Opt-in telemetry wrapper — silent no-op if gate off. Never breaks hook path."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        log_event(event_type, payload)
    except Exception:
        pass


def main():
    import time as _time
    _t_start = _time.perf_counter()
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    prompt = input_data.get("prompt", "")
    _session_id = input_data.get("session_id", "")

    # A/B scaffold: control arm skips injection entirely (CTX_AB_DISABLE=1).
    # Dashboard uses the logged ab_skipped events to count control-arm sessions.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import ab_disabled, log_event
        if ab_disabled():
            log_event("ab_skipped", {"hook": "bm25-memory", "reason": "CTX_AB_DISABLE"})
            sys.exit(0)
    except Exception:
        pass
    lines = []
    _blocks_fired = []  # for final hook_invoked telemetry summary
    _retrieval_meta = {"ts": _time.time(), "blocks": {}}  # retrieval_event telemetry

    # 0a. Pending decisions from previous session (Stop hook → queue file)
    pending = consume_pending_decisions(project_dir)
    if pending:
        lines.extend(pending)

    # 0b. Session decisions (uncommitted notes)
    session_notes = get_session_decisions(project_dir)
    if session_notes:
        lines.append("[SESSION NOTES (미커밋 판단)]")
        lines.extend(session_notes)

    # 1. G1: Hybrid BM25+dense RRF over decision corpus (2026-04-26)
    # Uses hybrid_rank_decisions() when vec-daemon is up (BM25+dense→RRF→rerank).
    # Falls back to bm25_rank_decisions() if dense unavailable — explicit coverage.
    # Eval: BM25=0.966, Hybrid=0.983 (+1.7pp) on 59-query G1 bench (172 commits).
    _t_g1 = _time.perf_counter()
    corpus = get_decision_corpus(project_dir)
    g1_header = ""
    if corpus:
        _g1_top_k = _get_g1_top_k(prompt, _AUTO_TUNE)
        _last_retrieval_scores.clear()
        relevant = hybrid_rank_decisions(corpus, prompt, top_k=_g1_top_k)
        if relevant:
            # Build forced display header (mechanically injected, not advisory)
            first_subj = relevant[0]["subject"][:70]
            rest_count = len(relevant) - 1
            g1_header = f'> **G1** (time memory): "{first_subj}" and {rest_count} more'

            lines.append(
                f"[RECENT DECISIONS] (BM25: top {len(relevant)} of {len(corpus)})"
            )
            for c in relevant:
                date = c.get("date", "")
                subj = c["subject"]
                prefix = f"  > [{date}] " if date else "  > "
                lines.append(f"{prefix}{subj}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g1_decisions",
                "count": len(relevant),
                "duration_ms": int((_time.perf_counter() - _t_g1) * 1000),
            })
            _blocks_fired.append("g1")
            _g1_meta: dict = {
                "candidates": len(corpus),
                "returned": len(relevant),
                "retrieval_method": "HYBRID" if (_VEC_SOCK.exists() and not _VEC_DISABLED) else "BM25",
                "duration_ms": int((_time.perf_counter() - _t_g1) * 1000),
                "query_type": _classify_query_type(prompt),
            }
            if "bm25_top" in _last_retrieval_scores:
                _g1_meta["top_score_bm25"] = round(_last_retrieval_scores["bm25_top"], 4)
            if "dense_top" in _last_retrieval_scores:
                _g1_meta["top_score_dense"] = round(_last_retrieval_scores["dense_top"], 4)
            _retrieval_meta["blocks"]["g1_decisions"] = _g1_meta
            # Citation probe: log G1 retrieved nodes
            log_retrieved_nodes(project_dir, _session_id, prompt, "g1_decisions", [
                {"id": c.get("hash", c["subject"][:20]), "text": c["subject"], "date": c.get("date", "")}
                for c in relevant
            ])

    # 2. G2: BM25 over project docs
    g2_files = []
    g2_keywords = []
    if prompt:
        _t_g2d = _time.perf_counter()
        _g2d_top_k = _get_g2d_top_k(prompt, _AUTO_TUNE)
        _last_retrieval_scores.pop("bm25_top", None)
        _last_retrieval_scores.pop("dense_top", None)
        doc_chunks = hybrid_search_docs(project_dir, prompt, top_k=_g2d_top_k)
        if doc_chunks:
            lines.append("[G2-DOCS] (BM25+dense RRF relevant research docs)")
            for chunk in doc_chunks:
                chunk_lines = chunk.strip().split("\n")
                header = chunk_lines[0]  # "filename § section"
                fname = header.split(" §")[0].strip()
                if fname and fname not in g2_files:
                    g2_files.append(fname)
                snippet = ""
                if len(chunk_lines) > 1:
                    # Find first non-empty content line
                    for cl in chunk_lines[1:]:
                        cl = cl.strip()
                        if cl and not cl.startswith("#"):
                            snippet = cl[:120]
                            break
                lines.append(f"  > {header}")
                if snippet:
                    lines.append(f"    {snippet}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_docs",
                "count": len(doc_chunks),
                "duration_ms": int((_time.perf_counter() - _t_g2d) * 1000),
            })
            _blocks_fired.append("g2_docs")
            _g2d_corpus_size = len(build_docs_bm25(project_dir)[1]) if doc_chunks else None
            _g2d_meta: dict = {
                "candidates": _g2d_corpus_size,
                "returned": len(doc_chunks),
                "retrieval_method": "HYBRID" if (_VEC_SOCK.exists() and not _VEC_DISABLED) else "BM25",
                "duration_ms": int((_time.perf_counter() - _t_g2d) * 1000),
                "query_type": _classify_query_type(prompt),
            }
            if "bm25_top" in _last_retrieval_scores:
                _g2d_meta["top_score_bm25"] = round(_last_retrieval_scores["bm25_top"], 4)
            if "dense_top" in _last_retrieval_scores:
                _g2d_meta["top_score_dense"] = round(_last_retrieval_scores["dense_top"], 4)
            _retrieval_meta["blocks"]["g2_docs"] = _g2d_meta
            # Citation probe: log G2-DOCS retrieved nodes
            log_retrieved_nodes(project_dir, _session_id, prompt, "g2_docs", [
                {"id": chunk.strip().split("\n")[0].split(" §")[0].strip(), "text": chunk.strip().split("\n")[0][:80]}
                for chunk in doc_chunks
            ])

    # 3. G2: Code file discovery (graph → grep fallback)
    if prompt:
        keywords = extract_keywords(prompt)
        g2_keywords = keywords[:3]
        if keywords:
            _t_g2p = _time.perf_counter()
            db_path = find_db(project_dir)
            if db_path:
                # Staleness check: auto-reindex if DB > 24h old
                stale_warn = check_and_trigger_reindex(project_dir, db_path)
                if stale_warn:
                    lines.append(stale_warn)
                graph_results = search_graph_for_prompt(db_path, keywords)
                if graph_results:
                    lines.append(f"[G2-PREFETCH] Related code for '{' '.join(keywords[:3])}':")
                    seen_files = set()
                    for label, name, fpath in graph_results:
                        lines.append(f"  {label}: {name} @ {fpath}")
                        seen_files.add(fpath)
                    if seen_files:
                        lines.append(f"  Start with: {', '.join(sorted(seen_files)[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_prefetch",
                        "count": len(graph_results),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_prefetch")
            else:
                # Fallback: git grep
                files = search_files_by_grep(project_dir, keywords)
                if files:
                    lines.append(f"[G2-GREP] Files matching '{' '.join(keywords[:3])}' (grep):")
                    for f in files:
                        lines.append(f"  {f}")
                    lines.append(f"  Start with: {', '.join(files[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_grep",
                        "count": len(files),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_grep")

    # 3b. G2: Hooks file discovery (when hook-related terms in prompt)
    if prompt and _has_hooks_keywords(prompt):
        _t_g2h = _time.perf_counter()
        hook_results = search_hooks_files(prompt)
        if hook_results:
            lines.append(f"[G2-HOOKS] Hook files matching '{prompt[:40]}':")
            for hp, score in hook_results:
                lines.append(f"  {hp}  (score={score:.1f})")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_hooks",
                "count": len(hook_results),
                "duration_ms": int((_time.perf_counter() - _t_g2h) * 1000),
            })
            _blocks_fired.append("g2_hooks")

    # 4. World model (--rich)
    if RICH:
        dead_ends, facts = get_world_model(project_dir)
        if dead_ends:
            lines.append("[DEAD-ENDS -- do not retry]")
            lines.extend(dead_ends)
        if facts:
            lines.append("[KNOWN FACTS]")
            lines.extend(facts)

    if lines:
        header_lines = build_header_lines(
            g1_header, g2_files, g2_keywords,
            _VEC_SOCK, _VEC_DISABLED, _BGE_SOCK, _USE_CROSS_ENCODER,
            _AUTO_TUNE, _AUTO_TUNE_ACTIVE,
        )
        emit_output(lines, header_lines)

    # Final summary event: one record per hook invocation (outside `if lines:`)
    _log_event("hook_invoked", {
        "hook": "bm25-memory",
        "duration_ms": int((_time.perf_counter() - _t_start) * 1000),
        "prompt_len": len(prompt) if prompt else 0,
    })

    # ── P1: record what we injected for utility-rate measurement ─────
    write_injection_record(
        prompt, lines, _retrieval_meta,
        _VEC_SOCK, _VEC_DISABLED, _BGE_SOCK, _session_id,
    )


if __name__ == "__main__":
    main()
