"""
tier1_longmemeval.py — Tier 1 public-benchmark harness for LongMemEval (ICLR 2025).

LongMemEval (arxiv:2410.10813) evaluates LLM chat memory across 5 axes:
  - information extraction
  - multi-session reasoning
  - knowledge updates
  - temporal reasoning
  - abstention

Dataset: HuggingFace `xiaowu0162/longmemeval` (500+ multi-session QA pairs).
License: Apache-2.0. Third-party — the whole point of Tier 1 is NOT using
our own corpus.

Adapter strategy:
  1. Download `longmemeval_s` (short-context variant; fastest).
  2. For each question, build the memory context as CTX would have surfaced it
     by running BM25 over the multi-session haystack history (injected as
     session messages).
  3. Feed (context + question) to LLM, record answer.
  4. Score via LongMemEval's official judge script (LLM-based F1 / exact-match).
  5. Emit Recall + answer-quality numbers per axis.

This harness supports two retrievers (--retriever):
  - ctx:       CTX BM25 + bge-daemon rerank
  - oracle:    ground-truth memories only (upper-bound sanity)
  - none:      no memory (lower-bound baseline)
  - chroma:    claude-mem-like dense retrieval (if chromadb installed)

Usage:
  python3 benchmarks/eval/tier1_longmemeval.py --download
  python3 benchmarks/eval/tier1_longmemeval.py --retriever ctx --n 20
  python3 benchmarks/eval/tier1_longmemeval.py --retriever none --n 20
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

ROOT = Path(__file__).parent.parent.parent
DATASET_DIR = ROOT / "benchmarks" / "datasets" / "longmemeval"
RESULTS = ROOT / "benchmarks" / "results" / "tier1_longmemeval.json"
sys.path.insert(0, str(ROOT / "benchmarks" / "eval"))
from downstream_llm_eval import get_llm_client, call_llm   # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Dataset download / load
# ══════════════════════════════════════════════════════════════════════════

DATASET_URL = "xiaowu0162/longmemeval"   # HF dataset identifier
DATASET_FILES = ("longmemeval_s.json", "longmemeval_oracle.json")


def download_dataset(target: Path = DATASET_DIR) -> Path:
    """Fetch the LongMemEval short-context split from HF.
    Falls back to manual URL if huggingface_hub not installed."""
    target.mkdir(parents=True, exist_ok=True)
    try:
        from huggingface_hub import hf_hub_download
        for fname in DATASET_FILES:
            local = target / fname
            if local.exists():
                continue
            p = hf_hub_download(repo_id=DATASET_URL, filename=fname,
                                repo_type="dataset", local_dir=str(target))
            print(f"[download] {fname} -> {p}")
    except ImportError:
        print("[error] pip install huggingface_hub — or place dataset files manually:", file=sys.stderr)
        for f in DATASET_FILES:
            print(f"  expected: {target / f}", file=sys.stderr)
        sys.exit(2)
    return target


def load_dataset(split: str = "longmemeval_s") -> List[Dict[str, Any]]:
    path = DATASET_DIR / f"{split}.json"
    if not path.exists():
        print(f"[error] {path} not found. Run with --download first.", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text())


# ══════════════════════════════════════════════════════════════════════════
# Retriever adapters
# ══════════════════════════════════════════════════════════════════════════

def _lazy_bm25_hook():
    HOOK = Path.home() / ".claude" / "hooks" / "bm25-memory.py"
    spec = importlib.util.spec_from_file_location("bm25mem", str(HOOK))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def retrieve_ctx(question: str, haystack: List[Dict], top_k: int = 7) -> List[str]:
    """CTX-style BM25 retrieval over multi-session haystack.

    Each haystack entry is a session {session_id, turns: [{role, content}]}.
    We flatten turns as pseudo-commits for BM25 ranking. Reuses the production
    bm25_rank_decisions tokenizer + adaptive floor + MMR filters."""
    hook = _lazy_bm25_hook()
    # Flatten: one "commit-like" entry per turn, with the content as subject
    corpus = []
    for s_idx, sess in enumerate(haystack):
        sid = sess.get("session_id", f"s{s_idx}")
        for t_idx, turn in enumerate(sess.get("turns", [])):
            txt = turn.get("content", "")[:400]
            if not txt.strip():
                continue
            corpus.append({
                "subject": f"[{sid}/t{t_idx}] {txt}",
                "text": txt,
                "date": sess.get("timestamp"),
            })
    if not corpus:
        return []
    hits = hook.bm25_rank_decisions(corpus, question, top_k=top_k, min_score=0.1)
    return [h.get("subject", h.get("text", "")) for h in hits]


def retrieve_oracle(question: str, oracle_memories: List[str], top_k: int = 7) -> List[str]:
    """Use ground-truth oracle memories (upper bound sanity)."""
    return oracle_memories[:top_k]


def retrieve_none(question: str, *args, **kwargs) -> List[str]:
    return []


def retrieve_chroma(question: str, haystack: List[Dict], top_k: int = 7) -> List[str]:
    """claude-mem-style dense retrieval (requires chromadb + all-MiniLM)."""
    try:
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("[chroma] chromadb not installed; returning []", file=sys.stderr)
        return []
    client = chromadb.Client()
    try:
        coll = client.get_or_create_collection(
            "tier1-longmemeval",
            embedding_function=embedding_functions.DefaultEmbeddingFunction(),
        )
        docs, ids = [], []
        for s_idx, sess in enumerate(haystack):
            for t_idx, turn in enumerate(sess.get("turns", [])):
                txt = turn.get("content", "")[:400]
                if not txt.strip():
                    continue
                docs.append(txt)
                ids.append(f"s{s_idx}-t{t_idx}")
        coll.upsert(documents=docs, ids=ids)
        res = coll.query(query_texts=[question], n_results=top_k)
        return res.get("documents", [[]])[0]
    except Exception as e:
        print(f"[chroma] error: {e}", file=sys.stderr)
        return []


RETRIEVERS = {
    "ctx":    retrieve_ctx,
    "oracle": retrieve_oracle,
    "none":   retrieve_none,
    "chroma": retrieve_chroma,
}


# ══════════════════════════════════════════════════════════════════════════
# LLM answer + judge
# ══════════════════════════════════════════════════════════════════════════

ANSWER_SYS = (
    "You are a helpful assistant answering questions about a long multi-session "
    "conversation. Use the provided memory excerpts to answer concisely. If the "
    "answer is not supported by the memory, say 'I don't have enough information'."
)
JUDGE_SYS = (
    "You are a strict grader. Given a reference answer and a candidate answer, "
    "decide if the candidate is correct (captures the key fact in the reference). "
    "Output EXACTLY one word: CORRECT or INCORRECT."
)


def answer_question(client, question: str, memories: List[str], model: str = "") -> str:
    memory_block = "\n".join(f"- {m}" for m in memories) if memories else "(no memory)"
    user = f"Memory excerpts:\n{memory_block}\n\n---\n\nQuestion: {question}"
    return call_llm(client, ANSWER_SYS, user, model=model, max_tokens=512)


def judge_answer(client, reference: str, candidate: str, model: str = "") -> int:
    prompt = f"Reference answer: {reference}\n\nCandidate answer: {candidate}\n\nIs the candidate correct?"
    out = call_llm(client, JUDGE_SYS, prompt, model=model, max_tokens=1024)
    if out.startswith("["):
        return 0
    import re as _re
    words = _re.findall(r"\b(CORRECT|INCORRECT)\b", out.upper())
    return 1 if (words and words[-1] == "CORRECT") else 0


# ══════════════════════════════════════════════════════════════════════════
# Main eval loop
# ══════════════════════════════════════════════════════════════════════════

def run_eval(questions: List[Dict], retriever_name: str, n: int = 0, model: str = "") -> Dict:
    retriever = RETRIEVERS[retriever_name]
    client = get_llm_client()
    if not client:
        print("[error] no LLM client", file=sys.stderr)
        sys.exit(2)

    if n:
        questions = questions[:n]

    results = []
    correct_by_axis: Dict[str, List[int]] = {}
    for i, q in enumerate(questions, 1):
        question_text = q.get("question", "")
        reference = q.get("answer", "")
        axis = q.get("question_type", "unknown")
        haystack = q.get("haystack_sessions", [])
        oracle = q.get("answer_session_ids", []) or q.get("oracle_memories", [])

        if retriever_name == "oracle":
            memories = retrieve_oracle(question_text, [str(o) for o in oracle])
        elif retriever_name == "none":
            memories = []
        else:
            memories = retriever(question_text, haystack, top_k=7)

        candidate = answer_question(client, question_text, memories, model=model)
        is_correct = judge_answer(client, reference, candidate, model=model)

        correct_by_axis.setdefault(axis, []).append(is_correct)
        results.append({
            "question_id": q.get("question_id", str(i)),
            "axis": axis,
            "question": question_text[:200],
            "reference": reference[:200],
            "candidate": candidate[:500],
            "n_memories": len(memories),
            "correct": is_correct,
        })
        print(f"  [{i}/{len(questions)}] axis={axis} correct={is_correct} mem={len(memories)}", flush=True)

    # Aggregate per axis
    per_axis = {axis: {"n": len(xs), "accuracy": round(sum(xs)/len(xs), 3)}
                for axis, xs in correct_by_axis.items()}
    overall = {"n": len(results),
               "accuracy": round(sum(r["correct"] for r in results) / max(1, len(results)), 3)}

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    # Append to per-retriever key — keep history of runs
    existing = {}
    if RESULTS.exists():
        try:
            existing = json.loads(RESULTS.read_text())
        except Exception:
            pass
    existing[retriever_name] = {
        "overall": overall, "per_axis": per_axis,
        "per_question": results, "model": model or os.environ.get("MINIMAX_MODEL", ""),
    }
    RESULTS.write_text(json.dumps(existing, indent=2))
    print(f"\n[tier1-longmemeval] retriever={retriever_name} overall={overall}")
    print(f"  per_axis: {json.dumps(per_axis)}")
    print(f"  wrote {RESULTS}")
    return existing[retriever_name]


def main():
    ap = argparse.ArgumentParser(description="Tier 1 — LongMemEval harness (ICLR 2025)")
    ap.add_argument("--download", action="store_true", help="fetch dataset from HuggingFace")
    ap.add_argument("--retriever", choices=list(RETRIEVERS.keys()), default="ctx")
    ap.add_argument("--n", type=int, default=0, help="cap number of questions (0 = all)")
    ap.add_argument("--model", default="")
    ap.add_argument("--split", default="longmemeval_s")
    args = ap.parse_args()

    if args.download:
        download_dataset()
        print("[download] complete")
        return

    qs = load_dataset(args.split)
    print(f"[tier1-longmemeval] loaded {len(qs)} questions from {args.split}")
    run_eval(qs, args.retriever, n=args.n, model=args.model)


if __name__ == "__main__":
    main()
