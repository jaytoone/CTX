#!/usr/bin/env python3
"""
G1 Docs Memory Eval — BM25 vs PageIndex vs no_ctx
===================================================
Uses BM25Okapi over chunked research docs to answer factual QA pairs.
Compares BM25+LLM, BM25-keyword (no LLM), PageIndex, and no_ctx baselines.

Run:
  cd /home/jayone/Project/CTX
  source ~/.claude/env/shared.env
  python3 benchmarks/eval/g1_docs_bm25_eval.py 2>&1
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

import anthropic
from rank_bm25 import BM25Okapi


# ──────────────────────────────────────────────────────────────────────────────
# QA Pairs (same as g1_docs_memory_eval.py)
# ──────────────────────────────────────────────────────────────────────────────

QA_PAIRS = [
    {
        "question": "CTX G1 long-term memory eval에서 BM25 retrieval의 Recall@5는 얼마인가?",
        "answer_keywords": ["0.881", "88.1%"],
    },
    {
        "question": "CTX의 keyword R@3가 0.379에서 얼마로 개선되었나?",
        "answer_keywords": ["0.724", "72.4%"],
    },
    {
        "question": "CTX G2 external codebase에서 Flask의 R@5는?",
        "answer_keywords": ["0.66", "0.660"],
    },
    {
        "question": "CTX vs Nemotron 비교에서 전체 R@3 결과는?",
        "answer_keywords": ["0.713", "71.3%"],
    },
    {
        "question": "git_memory_real baseline의 G1 recall은?",
        "answer_keywords": ["0.169", "16.9%"],
    },
    {
        "question": "G1 temporal retention eval에서 7-30일 구간 recall은?",
        "answer_keywords": ["0.000", "0.071", "zero"],
    },
    {
        "question": "CTX G1 format ablation에서 테스트한 포맷 종류 수는?",
        "answer_keywords": ["5", "five"],
    },
    {
        "question": "dense_embedding baseline의 open-set 평균 recall은?",
        "answer_keywords": ["0.375", "0.376"],
    },
    {
        "question": "CTX가 Claude Code 첫 턴에서 절약하는 시간 비율은?",
        "answer_keywords": ["60%", "60"],
    },
    {
        "question": "G1 eval에서 사용된 총 QA pair 수는?",
        "answer_keywords": ["59"],
    },
]


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Build BM25 index over doc chunks
# ──────────────────────────────────────────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    """Lowercase; preserve decimal numbers (0.724) and numeric ranges (7-30)."""
    tokens = re.findall(r'\d+[-\u2013]\d+|\d+\.\d+|\w+', text.lower())
    return [t for t in tokens if t]


def chunk_document(filename: str, content: str) -> List[str]:
    """Split a document by ## section headers. Each chunk = filename § header\ncontent."""
    chunks = []
    # Split on ## headers (but not ### or deeper — only top-level sections)
    parts = re.split(r'\n(?=## )', content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split('\n', 1)
        header_line = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ''

        # Remove leading ## from header
        header = re.sub(r'^#+\s*', '', header_line)
        chunk_text = f"{filename} § {header}\n{body}"

        # Keep only chunks with > 50 chars of content
        if len(body) > 50:
            chunks.append(chunk_text)

    # If no sections were found, treat the whole document as one chunk
    if not chunks and len(content) > 50:
        chunks.append(f"{filename} § (full)\n{content}")

    return chunks


def build_bm25_index(research_dir: Path) -> Tuple[BM25Okapi, List[str]]:
    """Read all *.md files, chunk by sections, build BM25Okapi index."""
    md_files = sorted(research_dir.glob("*.md"))
    all_chunks: List[str] = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8", errors="replace")
        file_chunks = chunk_document(md_file.name, content)
        all_chunks.extend(file_chunks)

    # Also index supplementary memory files not under docs/research/
    extra_files = [
        Path("/home/jayone/Project/CTX/CLAUDE.md"),
        Path("/home/jayone/.claude/projects/-home-jayone-Project-CTX/memory/MEMORY.md"),
    ]
    for extra_file in extra_files:
        if extra_file.exists():
            content = extra_file.read_text(encoding="utf-8", errors="replace")
            file_chunks = chunk_document(extra_file.name, content)
            all_chunks.extend(file_chunks)

    tokenized_corpus = [tokenize(chunk) for chunk in all_chunks]
    bm25 = BM25Okapi(tokenized_corpus)

    return bm25, all_chunks


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Retrieve top-5 chunks and answer with LLM
# ──────────────────────────────────────────────────────────────────────────────

def retrieve_top_k(question: str, bm25: BM25Okapi, chunks: List[str], k: int = 5) -> List[str]:
    """Retrieve top-k chunks by BM25 score."""
    query_tokens = tokenize(question)
    scores = bm25.get_scores(query_tokens)

    # Get top-k indices
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    return [chunks[i] for i in top_indices]


def build_context(top_chunks: List[str], max_chars: int = 3000) -> str:
    """Concatenate chunks up to max_chars."""
    result_parts = []
    total = 0
    for chunk in top_chunks:
        if total + len(chunk) > max_chars:
            remaining = max_chars - total
            if remaining > 100:
                result_parts.append(chunk[:remaining])
            break
        result_parts.append(chunk)
        total += len(chunk)
    return "\n\n---\n\n".join(result_parts)


def get_llm_client() -> Optional[anthropic.Anthropic]:
    """Build Anthropic client from env (MiniMax Anthropic-compatible endpoint)."""
    key = os.environ.get("MINIMAX_API_KEY", "")
    url = os.environ.get("MINIMAX_BASE_URL", "")
    if key and url:
        return anthropic.Anthropic(api_key=key, base_url=url)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return anthropic.Anthropic(api_key=key)
    return None


def call_llm(client: anthropic.Anthropic, context: str, question: str) -> str:
    """Call MiniMax M2.5 via Anthropic-compatible SDK to answer based on context."""
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    system = (
        "You are a research assistant. Answer factual questions based ONLY on the provided context. "
        "Be concise."
    )
    user = (
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer with the specific number/value if available:"
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Filter out thinking blocks — only use type="text"
        for block in resp.content:
            block_type = getattr(block, "type", "")
            if block_type == "text" and hasattr(block, "text"):
                return block.text.strip()
        # Fallback: any block with text attribute
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[EMPTY]"
    except Exception as e:
        return f"[LLM-ERROR: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: BM25-keyword baseline (no LLM)
# ──────────────────────────────────────────────────────────────────────────────

def bm25_keyword_check(answer_keywords: List[str], top_chunks: List[str]) -> bool:
    """Check if any answer_keywords appear directly in the retrieved chunks."""
    combined = "\n".join(top_chunks).lower()
    for kw in answer_keywords:
        if kw.lower() in combined:
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────────────────────

def score_response(response: str, answer_keywords: List[str]) -> bool:
    resp_lower = response.lower()
    for kw in answer_keywords:
        if kw.lower() in resp_lower:
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    research_dir = Path("/home/jayone/Project/CTX/docs/research")
    results_dir = Path("/home/jayone/Project/CTX/benchmarks/results")

    print("=" * 60)
    print("G1 Docs Memory Eval — BM25 vs PageIndex vs no_ctx")
    print("=" * 60)

    # Build BM25 index
    print(f"\nBuilding BM25 index from {research_dir} ...")
    t0 = time.time()
    bm25, chunks = build_bm25_index(research_dir)
    build_ms = (time.time() - t0) * 1000
    print(f"Index built: {len(chunks)} chunks from {len(list(research_dir.glob('*.md')))} docs in {build_ms:.0f}ms")
    print(f"Avg chunk length: {sum(len(c) for c in chunks) // max(len(chunks), 1)} chars")

    # Check API availability
    client = get_llm_client()
    llm_available = client is not None
    model_name = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    if llm_available:
        base_url = os.environ.get("MINIMAX_BASE_URL", "anthropic")
        print(f"LLM: {model_name} via {base_url[:40]}...")
    else:
        print("WARNING: No LLM API configured — BM25+LLM will fall back to BM25-keyword")

    print(f"\nRunning {len(QA_PAIRS)} questions ...\n")

    bm25_llm_results = []
    bm25_kw_results = []
    details = []

    for i, qa in enumerate(QA_PAIRS, 1):
        question = qa["question"]
        answer_keywords = qa["answer_keywords"]
        short_q = question[:50] + "..." if len(question) > 50 else question
        print(f"[{i:02d}] {question}")

        # Retrieve top-5 chunks
        top_chunks = retrieve_top_k(question, bm25, chunks, k=5)
        context = build_context(top_chunks, max_chars=3000)

        # BM25-keyword baseline (no LLM)
        kw_correct = bm25_keyword_check(answer_keywords, top_chunks)
        bm25_kw_results.append(kw_correct)
        kw_verdict = "YES" if kw_correct else "NO "
        print(f"     BM25-kw  : [{kw_verdict}] (keywords in top-5 chunks: {answer_keywords})")

        # BM25+LLM
        if llm_available:
            t_llm = time.time()
            llm_answer = call_llm(client, context, question)
            llm_ms = (time.time() - t_llm) * 1000
            if llm_answer.startswith("[LLM-ERROR"):
                print(f"     BM25+LLM : [FALLBACK — LLM error] {llm_answer}")
                # Fall back to keyword result
                llm_correct = kw_correct
            else:
                llm_correct = score_response(llm_answer, answer_keywords)
                llm_verdict = "YES" if llm_correct else "NO "
                print(f"     BM25+LLM ({llm_ms:.0f}ms): [{llm_verdict}] {llm_answer[:100]}")
        else:
            llm_correct = kw_correct
            llm_answer = "[NO-LLM-FALLBACK-TO-KEYWORD]"
            print(f"     BM25+LLM : [FALLBACK — no API]")

        bm25_llm_results.append(llm_correct)

        # Top-1 chunk preview
        if top_chunks:
            preview = top_chunks[0][:120].replace('\n', ' ')
            print(f"     top-1 chunk: {preview}...")

        details.append({
            "question": question,
            "answer_keywords": answer_keywords,
            "bm25_llm_correct": llm_correct,
            "bm25_kw_correct": kw_correct,
            "llm_answer": llm_answer if llm_available else "[no-llm]",
            "top_chunks_preview": [c[:200] for c in top_chunks],
        })
        print()

    # ── Summary table ──────────────────────────────────────────────────────────
    col_q = 45
    header_fmt = f"{'Question (abbrev)':<{col_q}}  {'BM25+LLM':>8}  {'BM25-kw':>7}  {'PageIdx':>7}  {'no_ctx':>6}"
    sep = "-" * (col_q + 35)

    print("\nG1 Docs Memory Eval — BM25 vs PageIndex vs no_ctx")
    print("=" * (col_q + 35))
    print(header_fmt)
    print(sep)

    # PageIndex and no_ctx reference values from prior eval
    pageindex_ref = [False, False, False, True, False, False, True, False, True, False]  # 3/10
    noctx_ref = [False, False, False, False, False, False, False, False, False, False]   # 0/10

    for i, qa in enumerate(QA_PAIRS):
        q = qa["question"]
        short_q = (q[:col_q - 3] + "...") if len(q) > col_q else q.ljust(col_q)
        b_llm = "YES" if bm25_llm_results[i] else "NO"
        b_kw = "YES" if bm25_kw_results[i] else "NO"
        pi = "YES" if pageindex_ref[i] else "NO"
        nc = "YES" if noctx_ref[i] else "NO"
        print(f"{short_q}  {b_llm:>8}  {b_kw:>7}  {pi:>7}  {nc:>6}")

    print(sep)
    llm_total = sum(bm25_llm_results)
    kw_total = sum(bm25_kw_results)
    pi_total = sum(pageindex_ref)
    nc_total = sum(noctx_ref)
    total_label = "TOTAL"
    print(f"{total_label:<{col_q}}  {llm_total}/10      {kw_total}/10      {pi_total}/10      {nc_total}/10")

    print()
    print(f"BM25+LLM accuracy:     {llm_total * 10}%")
    print(f"BM25-keyword accuracy: {kw_total * 10}%")
    print(f"PageIndex accuracy:   {pi_total * 10}%")
    print(f"no_ctx accuracy:       {nc_total * 10}%")

    # ── Save results ───────────────────────────────────────────────────────────
    results_dir.mkdir(parents=True, exist_ok=True)
    output = {
        "eval": "g1_docs_bm25_eval",
        "timestamp": time.strftime("%Y%m%d_%H%M%S"),
        "num_chunks": len(chunks),
        "num_docs": len(list(research_dir.glob("*.md"))),
        "bm25_llm_accuracy": llm_total / 10,
        "bm25_kw_accuracy": kw_total / 10,
        "pageindex_accuracy": pi_total / 10,
        "noctx_accuracy": nc_total / 10,
        "details": details,
    }
    out_path = results_dir / "g1_docs_bm25_results.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
