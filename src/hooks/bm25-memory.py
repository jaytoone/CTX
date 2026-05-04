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
import re
import subprocess
import sys
from pathlib import Path

# ── _bm25 package import (script entry-point path hack) ──────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _bm25.tokenizer import tokenize, expand_query_tokens  # noqa: E402
from _bm25.autotune import AUTO_TUNE as _AUTO_TUNE, AUTO_TUNE_ACTIVE as _AUTO_TUNE_ACTIVE  # noqa: E402
from _bm25.rerank import (  # noqa: E402
    vec_embed as _vec_embed, cosine as _cosine,
    semantic_rerank_filter,
    VEC_SOCK as _VEC_SOCK, VEC_DISABLED as _VEC_DISABLED,
    BGE_SOCK as _BGE_SOCK, USE_CROSS_ENCODER as _USE_CROSS_ENCODER,
)
from _bm25.corpus import (  # noqa: E402
    get_git_head, build_decision_corpus, embed_corpus_items,
    get_decision_corpus, _classify_query_type,
)
from _bm25.ranker import (  # noqa: E402
    dense_rank_decisions, rrf_merge, bm25_rank_decisions, hybrid_rank_decisions,
    last_retrieval_scores as _ranker_scores, HAS_BM25,
)
from _bm25.docs_search import (  # noqa: E402
    _extra_doc_files, chunk_document, build_docs_bm25,
    bm25_search_docs, embed_docs_units, dense_rank_docs, hybrid_search_docs,
)
from _bm25.code_search import (  # noqa: E402
    extract_keywords, find_db, log_retrieved_nodes,
    check_and_trigger_reindex, search_graph_for_prompt, search_files_by_grep,
)
from _bm25.hooks_search import (  # noqa: E402
    search_hooks_files, _has_hooks_keywords,
)

RICH = "--rich" in sys.argv

# _last_retrieval_scores: alias to ranker's module-level dict so orchestrator
# can clear/read it without changing call sites.
_last_retrieval_scores = _ranker_scores



# ── Rich Mode: World Model ────────────────────────────────────────

def get_world_model(project_dir):
    """Load dead-ends and facts from .omc/world-model.json (--rich mode)."""
    wm_path = Path(project_dir) / ".omc" / "world-model.json"
    if not wm_path.exists():
        return [], []
    try:
        wm = json.loads(wm_path.read_text())
    except Exception:
        return [], []
    raw_de = wm.get("dead_ends", [])
    if isinstance(raw_de, dict):
        raw_de = []
    dead_ends = [
        f"  x {de.get('goal','')[:60]} -- {de.get('reason','')[:80]}"
        for de in raw_de[-5:]
    ]
    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(
            fact.startswith(p) for p in ("paper:", "README:", "uncertain:")
        ):
            facts.append(f"  * {fact[:80]}")
    return dead_ends, facts[-8:]


# ── Session Decisions ─────────────────────────────────────────────

def get_session_decisions(project_dir):
    """Read .omc/session-decisions.md for uncommitted decisions."""
    p = Path(project_dir) / ".omc" / "session-decisions.md"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().split("\n")
        return [l.strip() for l in lines if l.strip().startswith(">")][-5:]
    except Exception:
        return []


# ── Pending Decisions (from previous session Stop hook) ──────────

def consume_pending_decisions(project_dir: str):
    """
    이전 세션 stop-decision-capture.py가 남긴 .pending-decisions.json 읽고 삭제.
    Returns list of formatted strings for additionalContext injection, or [].
    """
    slug = project_dir.replace("/", "-")
    pending_path = Path.home() / ".claude" / "projects" / slug / "memory" / ".pending-decisions.json"
    if not pending_path.exists():
        return []

    try:
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        captured_at = payload.get("captured_at", "")[:16]  # "2026-04-14T12:34"
    except Exception:
        try:
            pending_path.unlink(missing_ok=True)
        except Exception:
            pass
        return []

    # 읽은 즉시 삭제 (1회성 전달)
    try:
        pending_path.unlink(missing_ok=True)
    except Exception:
        pass

    if not decisions:
        return []

    lines = [f"[PENDING MEMORY] 이전 세션({captured_at}) 결정 후보 — MEMORY.md 업데이트 필요 여부 판단:"]
    for d in decisions:
        tag = d.get("tag", "")
        ctx = d.get("context", "")
        lines.append(f"  [{tag}] {ctx}")
    lines.append("→ 위 항목 중 MEMORY.md에 없는 중요한 결정이 있으면 즉시 Edit tool로 기록하세요.")
    return lines


# ── Main ──────────────────────────────────────────────────────────

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
        # Auto-tune: adjust top_k based on flywheel recommendations
        _g1_top_k = 7
        if _AUTO_TUNE:
            _qtype_now = _classify_query_type(prompt)
            _temporal_gap = _AUTO_TUNE.get("temporal_utility_gap", 0)
            # If TEMPORAL utility is 10pp below KEYWORD, reduce top_k to inject only best matches
            if _qtype_now == "TEMPORAL" and _temporal_gap > 0.10:
                _g1_top_k = 5  # more selective for low-utility temporal queries
            # Project-type profile adjustments (Stage 3 local loop)
            _proj_type = _AUTO_TUNE.get("project_type_hint", "")
            _proj_conf = _AUTO_TUNE.get("project_type_confidence", "LOW")
            if _proj_conf in ("HIGH", "MEDIUM"):
                if _proj_type == "python_ml":
                    # ML projects: training/model decisions span longer history
                    _g1_top_k = min(_g1_top_k + 1, 10)
                elif _proj_type == "nextjs_react":
                    # React: component decisions are keyword-specific, fewer suffice
                    _g1_top_k = max(_g1_top_k - 1, 4)
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
        # Auto-tune: adjust G2-DOCS top_k based on flywheel recommendations
        _g2d_top_k = 5
        if _AUTO_TUNE:
            _qtype_now2 = _classify_query_type(prompt)
            _g2_temporal_gap = _AUTO_TUNE.get("temporal_utility_gap", 0)
            if _qtype_now2 == "TEMPORAL" and _g2_temporal_gap > 0.10:
                _g2d_top_k = 3  # more selective for low-utility temporal doc queries
            # Project-type profile adjustments (Stage 3 local loop)
            _proj_type2 = _AUTO_TUNE.get("project_type_hint", "")
            _proj_conf2 = _AUTO_TUNE.get("project_type_confidence", "LOW")
            if _proj_conf2 in ("HIGH", "MEDIUM"):
                if _proj_type2 == "nextjs_react":
                    # Next.js: more framework docs per query (more component/API docs)
                    _g2d_top_k = min(_g2d_top_k + 1, 8)
                elif _proj_type2 == "rust_systems":
                    # Rust: docs are precise, fewer higher-quality docs preferred
                    _g2d_top_k = max(_g2d_top_k - 1, 3)
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
        # Prepend forced display header (mechanically enforced, replaces CLAUDE.md advisory)
        header_lines = []
        if g1_header:
            header_lines.append(g1_header)
        if g2_files or g2_keywords:
            files_str = ", ".join(f"`{f}`" for f in g2_files[:3]) if g2_files else "(docs BM25)"
            kw_str = " ".join(g2_keywords[:3]) if g2_keywords else ""
            via_str = f' — found via "{kw_str}"' if kw_str else ""
            header_lines.append(f"> **G2** (space search): {files_str}{via_str}")
        # Daemon degradation warnings — shown only when socket is absent
        _daemon_warns = []
        if not _VEC_DISABLED and not _VEC_SOCK.exists():
            _daemon_warns.append("vec-daemon down — BM25-only mode (semantic rerank disabled)")
        if _USE_CROSS_ENCODER and not _BGE_SOCK.exists():
            _daemon_warns.append("bge-daemon down — cross-encoder rerank disabled")
        if _daemon_warns:
            header_lines.append("> **⚠ Semantic layer**: " + " | ".join(_daemon_warns))
        # Auto-tune active badge — shows flywheel is running
        if _AUTO_TUNE_ACTIVE:
            n_rec = _AUTO_TUNE.get("based_on_n", "?")
            prefer_hybrid = _AUTO_TUNE.get("prefer_hybrid_G1", False)
            temporal_gap = _AUTO_TUNE.get("temporal_utility_gap")
            proj_hint = _AUTO_TUNE.get("project_type_hint")
            proj_conf = _AUTO_TUNE.get("project_type_confidence", "LOW")
            parts = [f"n={n_rec}"]
            if prefer_hybrid:
                parts.append("hybrid✓")
            if temporal_gap and temporal_gap > 0.05:
                parts.append(f"temporal-gap={temporal_gap*100:.0f}pp")
            if proj_hint and proj_hint != "multi_lang" and proj_conf in ("HIGH", "MEDIUM"):
                parts.append(proj_hint)
            header_lines.append(f"> **CTX auto-tune** [{', '.join(parts)}] — run `ctx-telemetry tune` to refresh")
        if header_lines:
            lines = header_lines + [""] + lines

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(lines),
            }
        }
        json.dump(output, sys.stdout)
        sys.stdout.flush()
        if header_lines:
            print("\n".join(header_lines), file=sys.stderr)
            sys.stderr.flush()

    # Final summary event: one record per hook invocation (outside `if lines:`)
    _log_event("hook_invoked", {
        "hook": "bm25-memory",
        "duration_ms": int((_time.perf_counter() - _t_start) * 1000),
        "prompt_len": len(prompt) if prompt else 0,
    })

    # ── P1: record what we injected for utility-rate measurement ─────
    # Stop hook reads this + the latest assistant turn + substring-matches
    # each item's distinctive tokens. Not stored when dashboard-internal.
    if os.environ.get("CTX_DASHBOARD_INTERNAL") != "1":
        try:
            # Preview = first 120 chars, newlines stripped (same privacy surface
            # as vault.db which already stores full prompts; this just makes the
            # dashboard see new prompts *before* vault.db incremental fires on Stop).
            preview = (prompt or "")[:120].replace("\n", " ").replace("\r", " ")
            # Full prompt stored too so the dashboard's node-details pane can
            # show the whole message before vault.db catches up.
            prompt_full_str = (prompt or "").replace("\r", "")
            # Derive the project basename from CLAUDE_PROJECT_DIR (fallback to cwd)
            try:
                _proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
                _project_name = os.path.basename(_proj.rstrip("/")) if _proj else None
            except Exception:
                _project_name = None
            injection = {
                "ts": _time.time(),
                "prompt_len": len(prompt) if prompt else 0,
                "prompt_preview": preview,
                "prompt_full": prompt_full_str,
                "project": _project_name,
                "items": [],
            }
            # Collect distinctive substrings from emitted blocks.
            # Each item is (block, signature) — signature is a 4-20 char
            # distinctive substring the assistant's response can echo.
            # Meta/filler words from commit subjects that never represent a topic.
            # Drops CTX's internal taxonomy (live-infinite, iter, goal_vN) + conventional
            # commit prefixes + common English verbs — anything that would generate
            # false-positive matches against unrelated responses.
            _META_WORDS = frozenset([
                "live-infinite", "live-inf", "omc-live", "iter", "live",
                "goal_v1", "goal_v2", "goal_v3", "goal",
                "feat", "fix", "refactor", "perf", "docs", "test", "chore",
                "success", "section", "update", "add", "remove", "change",
                "fixed", "added", "removed", "completed",
            ])
            # Header-row detector for "> **G1/G2**" and similar markdown headers
            _is_header_line = lambda st: st.startswith("> **") and "** (" in st

            def _extract_content_tokens(subject: str, n: int = 5) -> list:
                """Pick up to N distinctive content tokens from a commit subject.
                Filters meta words, pure digits, punctuation-only fragments.
                Prefers longer words (more specific = better substring hit rate)."""
                candidates = []
                for w in subject.split():
                    w_clean = w.strip(".,()[]{}:;!?\"'").lower()
                    if len(w_clean) < 4:
                        continue
                    if w_clean in _META_WORDS:
                        continue
                    if w_clean.replace("/", "").replace(".", "").replace("-", "").isdigit():
                        continue   # 20260402, 58/∞, etc.
                    # Keep case of original for better citation-style match
                    candidates.append(w.strip(".,()[]{}:;!?\"'"))
                # Dedup preserving order, sort by length desc for specificity
                seen = set()
                uniq = [t for t in candidates if not (t.lower() in seen or seen.add(t.lower()))]
                uniq.sort(key=lambda t: -len(t))
                return uniq[:n]

            for line in lines:
                s = line.strip()
                # Skip markdown headers like "> **G1** (time memory): ..." — they are
                # not items, they're section labels that would leak into signatures.
                if _is_header_line(s):
                    continue
                # G1 decisions: "> [YYYY-MM-DD] subject" — capture date for age-based wow trigger
                if s.startswith("> [") and "]" in s:
                    close_idx = s.index("]")
                    date_str = s[3:close_idx]
                    subj = s[close_idx + 1:].strip()
                    tokens = _extract_content_tokens(subj, n=5)
                    if tokens:
                        item = {
                            "block": "g1_decisions",
                            "tokens": tokens,
                            "subject": subj[:200],  # preserved for semantic scoring
                        }
                        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                            item["date"] = date_str
                        injection["items"].append(item)
                # G2-DOCS entries: "  > filename.md" → filename AS signature AND
                # also extract date-token + topic words from filename for more hit
                # surface (e.g. "20260411-g1-generalization-validation.md" also
                # matches on "generalization" / "validation").
                elif s.startswith("> ") and (".md" in s or s.endswith(".py")):
                    fname = s.lstrip("> ").strip().split(" §")[0].split()[0]
                    if fname:
                        # filename + its stem words as tokens
                        stem = fname.rsplit(".", 1)[0]
                        parts = [p for p in stem.replace("-", " ").replace("_", " ").split()
                                 if len(p) >= 4 and not p.isdigit()]
                        tokens = [fname] + parts[:4]
                        # Subject for semantic: the filename's natural-language form
                        subject = " ".join(parts) if parts else fname
                        injection["items"].append({
                            "block": "g2_docs", "tokens": tokens, "subject": subject[:200]
                        })
                # G2-PREFETCH: symbol names (function/class) + their path
                elif ": " in s and "@" in s and any(k in s for k in ("Function:", "Class:", "Method:", "Module:", "File:")):
                    try:
                        name = s.split(":", 1)[1].split("@")[0].strip()
                        path = s.split("@", 1)[1].strip() if "@" in s else ""
                        path_base = path.rsplit("/", 1)[-1] if path else ""
                        tokens = [t for t in [name, path_base] if t and len(t) >= 4]
                        if tokens:
                            injection["items"].append({
                                "block": "g2_prefetch",
                                "tokens": tokens,
                                "subject": f"{name} in {path}"[:200],
                            })
                    except Exception:
                        pass
            Path(os.path.expanduser("~/.claude/last-injection.json")).write_text(
                json.dumps(injection)
            )
            # Write retrieval metadata for utility-rate.py → retrieval_event schema
            _retrieval_meta["vec_daemon_up"] = _VEC_SOCK.exists() and not _VEC_DISABLED
            _retrieval_meta["bge_daemon_up"] = _BGE_SOCK.exists() and bool(
                os.environ.get("CTX_CROSS_ENCODER", "1") != "0"
            )
            _retrieval_meta["query_char_count"] = len(prompt) if prompt else 0
            _retrieval_meta["session_id"] = _session_id or ""
            Path(os.path.expanduser("~/.claude/last-retrieval-meta.json")).write_text(
                json.dumps(_retrieval_meta)
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
