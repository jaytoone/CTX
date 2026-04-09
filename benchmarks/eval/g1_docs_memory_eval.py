#!/usr/bin/env python3
"""
G1 Docs Memory Eval — PageIndex vs no_ctx
==========================================
Tests whether PageIndex can serve as a G1 long-term memory system by indexing
CTX's own research documents and answering factual questions about past experiments.

Run:
  cd /home/jayone/Project/CTX
  source ~/.claude/env/shared.env
  python3 benchmarks/eval/g1_docs_memory_eval.py 2>&1 | tee /tmp/docs_memory_eval_output.txt
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

import anthropic

# Add PageIndex to path
sys.path.insert(0, "/tmp/pageindex_repo")

from pageindex.page_index_md import (
    extract_nodes_from_markdown,
    extract_node_text_content,
    build_tree_from_nodes,
)


# ──────────────────────────────────────────────────────────────────────────────
# QA Pairs
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
# LLM client (same pattern as g1_pageindex_eval.py)
# ──────────────────────────────────────────────────────────────────────────────

def get_llm_client() -> Optional[anthropic.Anthropic]:
    key = os.environ.get("MINIMAX_API_KEY", "")
    url = os.environ.get("MINIMAX_BASE_URL", "")
    if key and url:
        return anthropic.Anthropic(api_key=key, base_url=url)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return anthropic.Anthropic(api_key=key)
    return None


def call_llm(client: anthropic.Anthropic, system: str, user: str, max_tokens: int = 512) -> str:
    if client is None:
        return "[NO-CLIENT]"
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            system=system,
        )
        for block in resp.content:
            block_type = getattr(block, "type", "")
            if block_type == "text" and hasattr(block, "text"):
                return block.text
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return "[EMPTY]"
    except Exception as e:
        return f"[LLM-ERROR: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# Build combined document from all research *.md files
# ──────────────────────────────────────────────────────────────────────────────

def build_combined_document(research_dir: Path) -> str:
    md_files = sorted(research_dir.glob("*.md"))
    parts = ["# CTX Research Archive\n"]
    for md_file in md_files:
        filename = md_file.name
        content = md_file.read_text(encoding="utf-8", errors="replace")
        parts.append(f"\n## {filename}\n")
        parts.append(content)
    return "\n".join(parts)


# ──────────────────────────────────────────────────────────────────────────────
# PageIndex helpers (same pattern as g1_pageindex_eval.py)
# ──────────────────────────────────────────────────────────────────────────────

def build_pageindex_tree(markdown_content: str) -> List[dict]:
    node_list, markdown_lines = extract_nodes_from_markdown(markdown_content)
    nodes_with_content = extract_node_text_content(node_list, markdown_lines)
    tree = build_tree_from_nodes(nodes_with_content)
    return tree


def tree_to_toc(tree: List[dict], indent: int = 0, max_nodes: int = 200) -> str:
    lines = []
    count = 0
    for node in tree:
        if count >= max_nodes:
            break
        node_id = node.get("node_id", "")
        title = node.get("title", "")
        line_num = node.get("line_num", "")
        prefix = "  " * indent
        lines.append(f"{prefix}[{node_id}] {title} (line {line_num})")
        count += 1
        if node.get("nodes") and count < max_nodes:
            child_toc = tree_to_toc(node["nodes"], indent + 1, max_nodes - count)
            if child_toc:
                lines.append(child_toc)
                count += child_toc.count("\n") + 1
    return "\n".join(lines)


def get_node_by_id(tree: List[dict], node_id: str) -> Optional[dict]:
    for node in tree:
        if node.get("node_id") == node_id:
            return node
        if node.get("nodes"):
            found = get_node_by_id(node["nodes"], node_id)
            if found:
                return found
    return None


def get_section_text(node: dict) -> str:
    text = node.get("text", "")
    for child in node.get("nodes", []):
        child_text = get_section_text(child)
        if child_text:
            text += "\n" + child_text
    return text


# ──────────────────────────────────────────────────────────────────────────────
# PageIndex 2-step retrieval
# ──────────────────────────────────────────────────────────────────────────────

def keyword_fallback_context(question: str, combined_doc: str, window: int = 6000) -> str:
    """Simple keyword-based fallback: find paragraphs containing question keywords."""
    # Extract significant words from question (skip stopwords)
    stopwords = {"은", "는", "이", "가", "에서", "의", "로", "을", "를", "와", "과", "한", "에", "도", "으로",
                 "a", "the", "is", "in", "of", "to", "and", "for", "from"}
    words = [w for w in re.split(r'[\s\?\.,]+', question) if len(w) >= 2 and w not in stopwords]

    # Score each paragraph
    paragraphs = combined_doc.split("\n\n")
    scored = []
    for p in paragraphs:
        if len(p.strip()) < 30:
            continue
        p_lower = p.lower()
        score = sum(1 for w in words if w.lower() in p_lower)
        if score > 0:
            scored.append((score, p))

    scored.sort(key=lambda x: -x[0])
    selected = []
    total = 0
    for _, p in scored:
        if total + len(p) > window:
            break
        selected.append(p)
        total += len(p)

    return "\n\n".join(selected) if selected else combined_doc[:window]


def query_pageindex(
    question: str,
    tree: List[dict],
    client: anthropic.Anthropic,
    combined_doc: str = "",
) -> str:
    toc = tree_to_toc(tree, max_nodes=150)

    # Step 1: LLM picks relevant node IDs from TOC
    nav_system = (
        "You are navigating a CTX research archive index. "
        "Given the table of contents, output 1-4 node IDs most likely to contain the answer. "
        "A node ID is a 4-digit number like 0001, 0042, 0123. "
        "Output ONLY node IDs as a comma-separated list, e.g.: 0001,0042,0123. "
        "No explanation needed."
    )
    nav_user = f"""Question: {question}

Research Archive Table of Contents:
{toc[:4000]}

Output only the relevant 4-digit node IDs (e.g. 0042,0078):"""

    nav_response = call_llm(client, nav_system, nav_user, max_tokens=100)
    # Match 4-digit IDs, allowing for zero-padding
    node_ids = re.findall(r'\b(0\d{3})\b', nav_response)
    # Also match any 4-digit number if zero-padded form not present
    if not node_ids:
        raw_ids = re.findall(r'\b(\d{1,4})\b', nav_response)
        node_ids = [f"{int(x):04d}" for x in raw_ids if 1 <= int(x) <= 9999]

    print(f"    nav_response: {nav_response[:80]!r} -> node_ids={node_ids[:6]}")

    # Step 2: Fetch those sections and answer
    sections = []
    for nid in node_ids[:5]:
        node = get_node_by_id(tree, nid)
        if node:
            section_text = get_section_text(node)
            title = node.get("title", nid)
            sections.append(f"=== [{nid}] {title} ===\n{section_text[:2000]}")

    if not sections:
        # Fallback: keyword-based paragraph retrieval from full doc
        print("    [WARN] No nodes found — using keyword fallback")
        context = keyword_fallback_context(question, combined_doc)
    else:
        context = "\n\n".join(sections)

    answer_system = (
        "You are a CTX research expert. Answer the question factually based on the provided context. "
        "Be specific with numbers and percentages. Keep answer to 2-3 sentences."
    )
    answer_user = f"""Relevant research sections:
{context[:5000]}

Question: {question}

Answer:"""

    return call_llm(client, answer_system, answer_user, max_tokens=256)


# ──────────────────────────────────────────────────────────────────────────────
# no_ctx baseline: parametric knowledge only
# ──────────────────────────────────────────────────────────────────────────────

def query_no_ctx(question: str, client: anthropic.Anthropic) -> str:
    system = (
        "You are a research AI. Answer the question from your knowledge only. "
        "If you don't know the exact answer, say so. Keep answer to 2-3 sentences."
    )
    return call_llm(client, system, f"Question: {question}\n\nAnswer:", max_tokens=256)


# ──────────────────────────────────────────────────────────────────────────────
# Scoring: keyword match
# ──────────────────────────────────────────────────────────────────────────────

def score_response(response: str, qa: dict) -> bool:
    resp_lower = response.lower()
    for kw in qa["answer_keywords"]:
        if kw.lower() in resp_lower:
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    research_dir = Path("/home/jayone/Project/CTX/docs/research")

    print("=" * 60)
    print("G1 Docs Memory Eval — PageIndex vs no_ctx")
    print("=" * 60)

    # LLM client
    client = get_llm_client()
    if client is None:
        print("ERROR: No LLM client. Set MINIMAX_API_KEY or ANTHROPIC_API_KEY.")
        return
    model_name = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    print(f"LLM: {model_name}")

    # Build combined document
    print(f"\nBuilding combined document from {research_dir} ...")
    combined_doc = build_combined_document(research_dir)
    doc_chars = len(combined_doc)
    print(f"Combined doc: {doc_chars:,} chars")

    # Build PageIndex tree
    print("Building PageIndex tree (no LLM) ...")
    t0 = time.time()
    tree = build_pageindex_tree(combined_doc)
    build_ms = (time.time() - t0) * 1000
    print(f"Tree built: {len(tree)} root nodes in {build_ms:.0f}ms")

    # Run eval
    print(f"\nRunning {len(QA_PAIRS)} questions ...\n")

    pageindex_results = []
    noctx_results = []

    for i, qa in enumerate(QA_PAIRS, 1):
        q = qa["question"]
        short_q = q[:45] + "..." if len(q) > 45 else q
        print(f"[{i:02d}] {q}")

        # PageIndex
        t0 = time.time()
        pi_answer = query_pageindex(q, tree, client, combined_doc=combined_doc)
        pi_ms = (time.time() - t0) * 1000
        pi_correct = score_response(pi_answer, qa)
        pageindex_results.append(pi_correct)
        pi_verdict = "YES" if pi_correct else "NO "
        print(f"     PageIndex ({pi_ms:.0f}ms): [{pi_verdict}] {pi_answer[:100]}")

        # no_ctx
        t0 = time.time()
        nc_answer = query_no_ctx(q, client)
        nc_ms = (time.time() - t0) * 1000
        nc_correct = score_response(nc_answer, qa)
        noctx_results.append(nc_correct)
        nc_verdict = "YES" if nc_correct else "NO "
        print(f"     no_ctx   ({nc_ms:.0f}ms): [{nc_verdict}] {nc_answer[:100]}")
        print()

    # Summary table
    col_q = 44
    print("G1 Docs Memory Eval — PageIndex vs no_ctx")
    print("=" * (col_q + 22))
    header = f"{'Question':<{col_q}}  {'PageIndex':>9}  {'no_ctx':>6}"
    print(header)
    print("-" * (col_q + 22))

    for i, qa in enumerate(QA_PAIRS):
        q = qa["question"]
        short_q = (q[:col_q - 3] + "...") if len(q) > col_q else q.ljust(col_q)
        pi = "YES" if pageindex_results[i] else "NO"
        nc = "YES" if noctx_results[i] else "NO"
        print(f"{short_q}  {pi:>9}  {nc:>6}")

    print("-" * (col_q + 22))
    pi_total = sum(pageindex_results)
    nc_total = sum(noctx_results)
    print(f"{'TOTAL':<{col_q}}  {pi_total}/10        {nc_total}/10")
    print()
    print(f"PageIndex accuracy: {pi_total * 10}%")
    print(f"no_ctx accuracy:    {nc_total * 10}%")
    advantage = (pi_total - nc_total) * 10
    sign = "+" if advantage >= 0 else ""
    print(f"PageIndex advantage: {sign}{advantage}%")


if __name__ == "__main__":
    main()
