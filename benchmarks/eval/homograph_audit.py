"""
homograph_audit.py — Surface-token-match failure audit.

Validates whether CTX's recent noise-reduction work (MMR dedup + cluster
signature, 2026-04-24) was the correct engineering priority.

Method:
  1. For each ambiguous term in AMBIGUOUS, generate a natural-language
     prompt that uses the term in ONE sense (the intended sense).
  2. Run CTX G1 retrieval (bm25-memory.bm25_rank_decisions) on that prompt.
  3. For each hit, classify as:
       RELEVANT            - actually matches the intended sense
       SURFACE_MATCH_ONLY  - mentions the term but in a different sense
  4. Report per-term + aggregate surface-match-only rate.

Threshold (pre-registered by 20260424-memory-experiential-eval-protocol.md):
  surface_match_only_rate >= 0.30  -> noise-reduction work was load-bearing
  surface_match_only_rate  < 0.30  -> noise was not the real issue; re-prioritize

Usage:
  python3 benchmarks/eval/homograph_audit.py dump      # emit BM25 hits, no label
  python3 benchmarks/eval/homograph_audit.py classify  # interactive label
  python3 benchmarks/eval/homograph_audit.py score     # score using existing gold
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path(__file__).parent.parent.parent
HOOK_PATH = Path.home() / ".claude" / "hooks" / "bm25-memory.py"
GOLD_PATH = ROOT / "benchmarks" / "datasets" / "homograph_gold.json"
OUT_PATH = ROOT / "benchmarks" / "results" / "homograph_audit.json"


# 20 ambiguous terms with an intended-sense prompt each.
AMBIGUOUS: List[Dict] = [
    {"term": "token", "sense": "software tokens (OAuth, session, API)",
     "prompt": "how is session token storage configured for the dev server"},
    {"term": "token", "sense": "NLP tokenizer tokens",
     "prompt": "bm25 tokenizer token length filter for short words"},
    {"term": "memory", "sense": "RAM/GPU memory",
     "prompt": "vec-daemon VRAM memory usage on RTX 3070 Ti"},
    {"term": "memory", "sense": "conversational memory / CTX recall",
     "prompt": "cross-session memory recall for prior decisions"},
    {"term": "context", "sense": "LLM context window",
     "prompt": "context window limit 200k for Claude Sonnet"},
    {"term": "context", "sense": "injected retrieval context / CTX",
     "prompt": "CTX context injection block format for UserPromptSubmit"},
    {"term": "graph", "sense": "dependency/import graph",
     "prompt": "python import graph traversal for g2-augment"},
    {"term": "graph", "sense": "dashboard knowledge graph UI",
     "prompt": "dashboard force-directed graph node rendering"},
    {"term": "index", "sense": "database/search index",
     "prompt": "codebase-memory-mcp index staleness detection"},
    {"term": "index", "sense": "list/array position",
     "prompt": "list index out of range python error"},
    {"term": "session", "sense": "Claude Code session / chat",
     "prompt": "session memory across Claude Code conversations"},
    {"term": "session", "sense": "TCP/network session",
     "prompt": "ssh session forwarding port 6789"},
    {"term": "cache", "sense": "prompt cache (Anthropic)",
     "prompt": "anthropic prompt cache 5 minute TTL cost"},
    {"term": "cache", "sense": "filesystem/CPU cache",
     "prompt": "disk cache flush after big file write"},
    {"term": "hook", "sense": "Claude Code hooks (UserPromptSubmit etc.)",
     "prompt": "UserPromptSubmit hook injection chat-memory"},
    {"term": "hook", "sense": "git hook",
     "prompt": "git pre-commit hook husky configuration"},
    {"term": "score", "sense": "retrieval score (BM25/cosine)",
     "prompt": "BM25 score threshold 3.0 for G2-DOCS"},
    {"term": "score", "sense": "test score",
     "prompt": "downstream score MiniMax G1 baseline"},
    {"term": "rerank", "sense": "semantic rerank (bi/cross-encoder)",
     "prompt": "bge-daemon cross-encoder rerank top-5 candidates"},
    {"term": "threshold", "sense": "numeric cutoff",
     "prompt": "min_score threshold 0.5 in bm25_rank_decisions"},
]


def _import_bm25_hook():
    spec = importlib.util.spec_from_file_location("bm25mem", str(HOOK_PATH))
    m = importlib.util.module_from_spec(spec)
    os.environ.setdefault("CTX_DISABLE_SEMANTIC_RERANK", "0")
    spec.loader.exec_module(m)
    return m


@dataclass
class Hit:
    rank: int
    subject: str
    date: Optional[str] = None
    label: Optional[str] = None


@dataclass
class PromptAudit:
    term: str
    sense: str
    prompt: str
    hits: List[Hit]
    n_hits: int
    n_relevant: int
    n_surface: int
    surface_rate: float


def run_retrieval(hook_module, prompt: str, top_k: int = 7) -> List[Hit]:
    project_dir = str(ROOT)
    corpus = hook_module.get_decision_corpus(project_dir)
    hits = hook_module.bm25_rank_decisions(corpus, prompt, top_k=top_k)
    out: List[Hit] = []
    for i, h in enumerate(hits, 1):
        out.append(Hit(
            rank=i,
            subject=h.get("subject") or h.get("text", "")[:120],
            date=h.get("date"),
        ))
    return out


def apply_gold(hits: List[Hit], prompt_id: str, gold: Dict) -> None:
    entries = gold.get(prompt_id, {}).get("hits", [])
    by_subj = {e["subject"][:80]: e["label"] for e in entries}
    for h in hits:
        key = h.subject[:80]
        if key in by_subj:
            h.label = by_subj[key]


def score_audit(hits: List[Hit]):
    n_hits = len(hits)
    labeled = [h for h in hits if h.label]
    n_rel = sum(1 for h in labeled if h.label == "RELEVANT")
    n_surf = sum(1 for h in labeled if h.label == "SURFACE_MATCH_ONLY")
    surface_rate = (n_surf / len(labeled)) if labeled else 0.0
    return n_hits, n_rel, n_surf, round(surface_rate, 3)


def cmd_dump(args):
    hook = _import_bm25_hook()
    results = []
    for i, p in enumerate(AMBIGUOUS, 1):
        hits = run_retrieval(hook, p["prompt"])
        print(f"\n[{i}/{len(AMBIGUOUS)}] term='{p['term']}' sense={p['sense']}")
        print(f"    prompt: {p['prompt']}")
        for h in hits:
            print(f"      #{h.rank}  {h.subject[:100]}")
        results.append({"prompt_id": f"{i:02d}-{p['term']}",
                        "prompt": p["prompt"], "sense": p["sense"],
                        "hits": [asdict(h) for h in hits]})
    out = ROOT / "benchmarks" / "results" / "homograph_dump.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print(f"\n[dump] wrote {out}")


def cmd_classify(args):
    hook = _import_bm25_hook()
    GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if GOLD_PATH.exists() and not args.force:
        gold = json.loads(GOLD_PATH.read_text())
        print(f"[classify] resuming {GOLD_PATH} ({len(gold)} prompts already labeled)")
    else:
        gold = {}
    for i, p in enumerate(AMBIGUOUS, 1):
        pid = f"{i:02d}-{p['term']}"
        if pid in gold and not args.force:
            continue
        hits = run_retrieval(hook, p["prompt"])
        print(f"\n=== [{i}/{len(AMBIGUOUS)}] term='{p['term']}'")
        print(f"    intended sense: {p['sense']}")
        print(f"    prompt: {p['prompt']}")
        entries = []
        for h in hits:
            print(f"\n  #{h.rank}  {h.subject}")
            while True:
                lbl = input("    label [r=RELEVANT / s=SURFACE / u=UNCERTAIN / q=quit]: ").strip().lower()
                if lbl in {"r", "s", "u"}:
                    break
                if lbl == "q":
                    GOLD_PATH.write_text(json.dumps(gold, indent=2))
                    print(f"[classify] saved progress to {GOLD_PATH}")
                    return
            label = {"r": "RELEVANT", "s": "SURFACE_MATCH_ONLY", "u": "UNCERTAIN"}[lbl]
            entries.append({"subject": h.subject, "label": label})
        gold[pid] = {"term": p["term"], "sense": p["sense"],
                     "prompt": p["prompt"], "hits": entries}
        GOLD_PATH.write_text(json.dumps(gold, indent=2))
    print(f"\n[classify] complete. {GOLD_PATH}")


def cmd_score(args):
    if not GOLD_PATH.exists():
        print(f"[error] No gold labels at {GOLD_PATH}. Run classify first.", file=sys.stderr)
        sys.exit(2)
    gold = json.loads(GOLD_PATH.read_text())
    hook = _import_bm25_hook()

    audits: List[PromptAudit] = []
    for i, p in enumerate(AMBIGUOUS, 1):
        pid = f"{i:02d}-{p['term']}"
        hits = run_retrieval(hook, p["prompt"])
        apply_gold(hits, pid, gold)
        n_hits, n_rel, n_surf, surface = score_audit(hits)
        audits.append(PromptAudit(
            term=p["term"], sense=p["sense"], prompt=p["prompt"],
            hits=hits, n_hits=n_hits, n_relevant=n_rel,
            n_surface=n_surf, surface_rate=surface,
        ))

    total_labeled = sum(a.n_relevant + a.n_surface for a in audits)
    total_surf = sum(a.n_surface for a in audits)
    aggregate_surface_rate = round((total_surf / total_labeled) if total_labeled else 0.0, 3)
    threshold = 0.30
    verdict = ("ABOVE threshold - noise-reduction work was load-bearing"
               if aggregate_surface_rate >= threshold
               else "BELOW threshold - noise was not the main issue; re-prioritize")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "n_prompts": len(audits),
        "aggregate_surface_match_only_rate": aggregate_surface_rate,
        "threshold": threshold,
        "verdict": verdict,
        "per_prompt": [{
            "term": a.term, "sense": a.sense, "prompt": a.prompt,
            "n_hits": a.n_hits, "n_relevant": a.n_relevant,
            "n_surface": a.n_surface, "surface_rate": a.surface_rate,
            "hits": [asdict(h) for h in a.hits],
        } for a in audits],
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))

    print(f"\n=== Homograph Audit Report ===")
    print(f"prompts: {len(audits)}  |  threshold: {threshold}")
    print(f"aggregate surface_match_only_rate: {aggregate_surface_rate}")
    print(f"verdict: {verdict}\n")
    print(f"{'term':<12} {'sense':<40} {'hits':>4} {'surf':>5} {'rate':>6}")
    for a in audits:
        print(f"{a.term:<12} {a.sense[:38]:<40} {a.n_hits:>4} {a.n_surface:>5} {a.surface_rate:>6}")
    print(f"\n[score] wrote {OUT_PATH}")


def main():
    ap = argparse.ArgumentParser(description="Homograph audit - surface-token-match rate")
    sub = ap.add_subparsers(dest="cmd", required=False)
    sub.add_parser("dump", help="emit hits per prompt, no labeling")
    p_cls = sub.add_parser("classify", help="interactive labeling")
    p_cls.add_argument("--force", action="store_true")
    sub.add_parser("score", help="score against existing gold")
    args = ap.parse_args()
    if args.cmd == "dump":
        cmd_dump(args)
    elif args.cmd == "classify":
        cmd_classify(args)
    else:
        cmd_score(args)


if __name__ == "__main__":
    main()
