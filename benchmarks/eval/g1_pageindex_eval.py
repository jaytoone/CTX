#!/usr/bin/env python3
"""
G1 PageIndex Baseline Eval
===========================
Integrates PageIndex (https://github.com/VectifyAI/PageIndex) as a new retrieval
baseline in the CTX G1 long-term memory evaluation.

PageIndex approach:
1. Convert CHANGELOG to markdown with hierarchical headers
2. Build a tree index using PageIndex's md_to_tree (no LLM required for indexing)
3. For each QA pair: ask LLM to navigate the tree TOC → fetch relevant section → answer

Compares against existing baselines from g1_openset_results.json.
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import anthropic

# Add PageIndex to path
sys.path.insert(0, "/tmp/pageindex_repo")

from pageindex.page_index_md import (
    extract_nodes_from_markdown,
    extract_node_text_content,
    build_tree_from_nodes,
)


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

REPOS = [
    {
        "name": "Flask",
        "clone_dir": "/tmp/g1_eval_flask",
        "changelog": "CHANGES.rst",
        "format": "rst",
    },
    {
        "name": "Requests",
        "clone_dir": "/tmp/g1_eval_requests",
        "changelog": "HISTORY.md",
        "format": "md",
    },
    {
        "name": "Django",
        "clone_dir": "/tmp/g1_eval_django",
        "format": "django",
    },
]

QA_PAIRS_PATH = Path("benchmarks/results/g1_openset_qa_pairs.json")
EXISTING_RESULTS_PATH = Path("benchmarks/results/g1_openset_results.json")
RESULTS_DIR = Path("benchmarks/results")


# ──────────────────────────────────────────────────────────────────────────────
# LLM client (MiniMax M2.5 via Anthropic-compatible API)
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
        # Fallback: any block with text
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return "[EMPTY]"
    except Exception as e:
        return f"[LLM-ERROR: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# CHANGELOG → Markdown conversion
# ──────────────────────────────────────────────────────────────────────────────

def rst_to_markdown(text: str) -> str:
    """Convert Flask CHANGES.rst to markdown with ## version headers."""
    lines = []
    sections = re.split(r'\n(Version \d+\.\d+[\.\d]*)\n[-=~]+\n', text)
    # sections[0] = preamble, then alternating: version_header, body
    lines.append("# CHANGELOG\n")
    i = 1
    while i < len(sections) - 1:
        version_header = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""
        lines.append(f"\n## {version_header}\n")
        # Convert RST bullets to markdown
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("-   ") or stripped.startswith("-  "):
                content = stripped[4:].strip()
                content = re.sub(r'\s*:\w+:`[^`]+`', '', content).strip()
                lines.append(f"- {content}")
            elif stripped.startswith("Released ") or stripped.startswith("Unreleased"):
                lines.append(f"\n{stripped}\n")
            else:
                lines.append(stripped)
        i += 2
    return "\n".join(lines)


def requests_history_to_markdown(text: str) -> str:
    """Convert Requests HISTORY.md (RST underline style) to clean markdown."""
    lines = []
    lines.append("# CHANGELOG\n")
    # Match: "X.Y.Z (YYYY-MM-DD)\n---"
    version_pattern = re.compile(
        r'^(\d+\.\d+[\.\d]*)\s+\((\d{4}-\d{2}-\d{2})\)\n[-]+',
        re.MULTILINE
    )
    matches = list(version_pattern.finditer(text))
    for idx, match in enumerate(matches):
        version = match.group(1)
        date = match.group(2)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        lines.append(f"\n## {version} ({date})\n")
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped.startswith("- ") or stripped.startswith("* "):
                lines.append(stripped)
            elif stripped.startswith("**") and stripped.endswith("**"):
                lines.append(f"\n### {stripped.strip('*').strip()}\n")
        lines.append("")
    return "\n".join(lines)


def django_releases_to_markdown(clone_dir: str) -> str:
    """Convert Django release notes directory to a single markdown."""
    releases_dir = Path(clone_dir) / "docs" / "releases"
    if not releases_dir.exists():
        return "# CHANGELOG\n\nNo releases found."

    release_files = sorted(releases_dir.glob("*.txt"), reverse=True)
    release_files = [f for f in release_files if re.match(r'^\d+\.\d+', f.stem)][:25]

    lines = ["# CHANGELOG\n"]
    for rf in release_files:
        text = rf.read_text(encoding="utf-8", errors="replace")
        version = rf.stem

        if "UNDER DEVELOPMENT" in text[:300]:
            continue

        date_match = re.search(r'\*(\w+ \d+,?\s*\d{4})\*', text[:400])
        date_str = f" ({date_match.group(1)})" if date_match else ""

        lines.append(f"\n## Django {version}{date_str}\n")

        # Extract what's new features
        whats_new_match = re.search(
            r"What's new in Django.*?\n[=]+\n(.*?)(?:\n\w[^\n]+\n[=]+|\Z)",
            text, re.DOTALL
        )
        if whats_new_match:
            section = whats_new_match.group(1)
            features = re.findall(r'^([A-Z][^\n]{10,80})\n[-~]+', section, re.MULTILINE)
            for feature in features[:8]:
                clean = feature.strip()
                if len(clean) > 10:
                    lines.append(f"- {clean}")
        lines.append("")

    return "\n".join(lines)


def get_changelog_as_markdown(repo_cfg: dict) -> str:
    """Get CHANGELOG as markdown string, converting from original format."""
    fmt = repo_cfg.get("format", "md")

    if fmt == "django":
        return django_releases_to_markdown(repo_cfg["clone_dir"])

    changelog_path = Path(repo_cfg["clone_dir"]) / repo_cfg["changelog"]
    if not changelog_path.exists():
        print(f"  [{repo_cfg['name']}] Changelog not found: {changelog_path}")
        return ""

    text = changelog_path.read_text(encoding="utf-8", errors="replace")

    if fmt == "rst":
        return rst_to_markdown(text)
    else:  # md (requests)
        return requests_history_to_markdown(text)


# ──────────────────────────────────────────────────────────────────────────────
# Build PageIndex tree (no LLM required)
# ──────────────────────────────────────────────────────────────────────────────

def build_pageindex_tree(markdown_content: str) -> List[dict]:
    """Build PageIndex hierarchical tree from markdown text (no LLM)."""
    node_list, markdown_lines = extract_nodes_from_markdown(markdown_content)
    nodes_with_content = extract_node_text_content(node_list, markdown_lines)
    tree = build_tree_from_nodes(nodes_with_content)
    return tree


def tree_to_toc(tree: List[dict], indent: int = 0) -> str:
    """Convert PageIndex tree to a table of contents string."""
    lines = []
    for node in tree:
        node_id = node.get("node_id", "")
        title = node.get("title", "")
        line_num = node.get("line_num", "")
        prefix = "  " * indent
        lines.append(f"{prefix}[{node_id}] {title} (line {line_num})")
        if node.get("nodes"):
            lines.append(tree_to_toc(node["nodes"], indent + 1))
    return "\n".join(lines)


def get_node_by_id(tree: List[dict], node_id: str) -> Optional[dict]:
    """Find a node in the tree by its node_id."""
    for node in tree:
        if node.get("node_id") == node_id:
            return node
        if node.get("nodes"):
            found = get_node_by_id(node["nodes"], node_id)
            if found:
                return found
    return None


def get_section_text(node: dict) -> str:
    """Get text from a node and its children."""
    text = node.get("text", "")
    for child in node.get("nodes", []):
        child_text = get_section_text(child)
        if child_text:
            text += "\n" + child_text
    return text


# ──────────────────────────────────────────────────────────────────────────────
# PageIndex retrieval: LLM navigates the tree
# ──────────────────────────────────────────────────────────────────────────────

def pageindex_retrieve_and_answer(
    query: str,
    tree: List[dict],
    client: anthropic.Anthropic,
    repo_name: str,
) -> str:
    """
    PageIndex approach:
    1. Show LLM the table of contents
    2. LLM picks which section(s) to look in
    3. Fetch those sections' text
    4. LLM answers from the fetched text
    """
    toc = tree_to_toc(tree)

    # Step 1: navigation — LLM picks relevant node IDs
    nav_system = f"""You are navigating a {repo_name} CHANGELOG to find when a feature was added.
Given the table of contents (TOC), output 1-3 node IDs most likely to contain the answer.
Output ONLY node IDs as a comma-separated list, e.g.: 0001,0002,0015
No explanation needed."""

    nav_user = f"""Question: {query}

CHANGELOG Table of Contents:
{toc[:3000]}

Which node IDs are most relevant? Output only node IDs:"""

    nav_response = call_llm(client, nav_system, nav_user, max_tokens=100)

    # Parse node IDs from navigation response
    node_ids = re.findall(r'\b(\d{4})\b', nav_response)

    # Fetch text from selected nodes
    sections = []
    for nid in node_ids[:4]:
        node = get_node_by_id(tree, nid)
        if node:
            section_text = get_section_text(node)
            sections.append(f"=== Section: {node.get('title', nid)} ===\n{section_text[:1500]}")

    if not sections:
        # Fallback: use first 5 root nodes
        for node in tree[:5]:
            sections.append(f"=== {node.get('title', '')} ===\n{node.get('text', '')[:500]}")

    context = "\n\n".join(sections)

    # Step 2: answer from fetched sections
    answer_system = f"""You are a {repo_name} expert. Answer the question about when a feature was added.
Be specific about version number and release date. Keep answer to 2-3 sentences."""

    answer_user = f"""Relevant CHANGELOG sections:
{context[:4000]}

Question: {query}"""

    return call_llm(client, answer_system, answer_user, max_tokens=256)


# ──────────────────────────────────────────────────────────────────────────────
# Scoring (same as g1_changelog_eval.py)
# ──────────────────────────────────────────────────────────────────────────────

def score_response(response: str, qa: dict) -> float:
    """Score 0/1: does response mention correct date or version?"""
    resp_lower = response.lower()
    gt_date = qa.get("ground_truth_date", "")
    gt_version = qa.get("ground_truth_version", "")

    if gt_date and gt_date in response:
        return 1.0
    if gt_version and gt_version in response:
        return 1.0

    if gt_date:
        parts = gt_date.split("-")
        if len(parts) == 3:
            year, month, day = parts
            month_names = {
                "01": "january", "02": "february", "03": "march", "04": "april",
                "05": "may", "06": "june", "07": "july", "08": "august",
                "09": "september", "10": "october", "11": "november", "12": "december"
            }
            month_name = month_names.get(month, "")
            day_int = str(int(day))

            if year in response and month_name in resp_lower:
                return 1.0
            if year in response and day_int in response:
                return 1.0

    return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Main eval
# ──────────────────────────────────────────────────────────────────────────────

def load_existing_results() -> Dict[str, Dict[str, float]]:
    """Load existing baseline results and compute per-repo means."""
    if not EXISTING_RESULTS_PATH.exists():
        return {}

    with open(EXISTING_RESULTS_PATH) as f:
        data = json.load(f)

    results = {}
    for repo, repo_results in data.items():
        baselines = {}
        for r in repo_results:
            bl = r["baseline"]
            baselines.setdefault(bl, []).append(r["score"])
        results[repo] = {bl: sum(scores) / len(scores) for bl, scores in baselines.items()}

    return results


def main():
    print("=" * 60)
    print("G1 PageIndex Baseline Evaluation")
    print("=" * 60)

    # Load existing QA pairs
    if not QA_PAIRS_PATH.exists():
        print(f"ERROR: QA pairs not found at {QA_PAIRS_PATH}")
        print("Run g1_changelog_eval.py first to generate QA pairs.")
        return

    with open(QA_PAIRS_PATH) as f:
        all_qa_pairs = json.load(f)

    print(f"Loaded QA pairs: {', '.join(f'{r}={len(p)}' for r, p in all_qa_pairs.items())}")

    # LLM client
    client = get_llm_client()
    if client is None:
        print("ERROR: No LLM client. Set MINIMAX_API_KEY or ANTHROPIC_API_KEY.")
        return
    print(f"LLM: {os.environ.get('MINIMAX_MODEL', 'MiniMax-M2.5')}")

    # Evaluate each repo
    pageindex_scores: Dict[str, float] = {}
    all_pageindex_results = {}

    for repo_cfg in REPOS:
        repo_name = repo_cfg["name"]
        qa_pairs = all_qa_pairs.get(repo_name, [])

        if not qa_pairs:
            print(f"\n[{repo_name}] No QA pairs — skipping")
            continue

        print(f"\n[{repo_name}] {len(qa_pairs)} QA pairs")

        # Build CHANGELOG markdown and PageIndex tree
        print(f"  Building PageIndex tree...")
        md_content = get_changelog_as_markdown(repo_cfg)
        if not md_content:
            print(f"  No CHANGELOG content — skipping")
            continue

        tree = build_pageindex_tree(md_content)
        print(f"  Tree built: {len(tree)} root nodes")

        # Evaluate each QA pair
        repo_results = []
        scores = []

        for i, qa in enumerate(qa_pairs, 1):
            query = qa["query"]
            print(f"  [{i}/{len(qa_pairs)}] {query[:70]}...")

            t0 = time.time()
            response = pageindex_retrieve_and_answer(query, tree, client, repo_name)
            latency_ms = (time.time() - t0) * 1000

            score = score_response(response, qa) if "[NO-CLIENT]" not in response else 0.0
            scores.append(score)

            result = {
                "query": query,
                "ground_truth_version": qa.get("ground_truth_version", ""),
                "ground_truth_date": qa.get("ground_truth_date", ""),
                "score": score,
                "response": response[:300],
                "latency_ms": round(latency_ms, 1),
            }
            repo_results.append(result)

            verdict = "CORRECT" if score == 1.0 else "wrong"
            print(f"    {verdict} ({latency_ms:.0f}ms) | {response[:80]}...")

        mean_score = sum(scores) / len(scores) if scores else 0.0
        pageindex_scores[repo_name] = mean_score
        all_pageindex_results[repo_name] = repo_results
        print(f"  [{repo_name}] PageIndex score: {mean_score:.3f}")

    # Save PageIndex results
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "g1_pageindex_results.json"
    with open(output_path, "w") as f:
        json.dump(all_pageindex_results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved: {output_path}")

    # Load existing results for comparison
    existing = load_existing_results()

    # Print comparison table
    repos = [r["name"] for r in REPOS if r["name"] in pageindex_scores]
    all_baselines_seen = set()
    for repo_scores in existing.values():
        all_baselines_seen.update(repo_scores.keys())
    baselines_ordered = ["no_ctx", "git_memory_real", "dense_embedding", "bm25_retrieval", "full_dump"]
    baselines_ordered = [b for b in baselines_ordered if b in all_baselines_seen]

    print("\n" + "=" * 60)
    print("RESULTS COMPARISON")
    print("=" * 60)
    print(f"\n{'Baseline':<22}", end="")
    for repo in repos:
        print(f"{repo:>10}", end="")
    print(f"{'Mean':>10}")
    print("-" * (22 + 10 * len(repos) + 10))

    # Existing baselines
    for bl in baselines_ordered:
        print(f"{bl:<22}", end="")
        bl_scores = []
        for repo in repos:
            score = existing.get(repo, {}).get(bl, None)
            if score is not None:
                print(f"{score:>10.3f}", end="")
                bl_scores.append(score)
            else:
                print(f"{'N/A':>10}", end="")
        if bl_scores:
            mean = sum(bl_scores) / len(bl_scores)
            print(f"{mean:>10.3f}")
        else:
            print()

    # PageIndex row
    print("-" * (22 + 10 * len(repos) + 10))
    print(f"{'pageindex (new)':<22}", end="")
    pi_scores = []
    for repo in repos:
        score = pageindex_scores.get(repo, None)
        if score is not None:
            print(f"{score:>10.3f}", end="")
            pi_scores.append(score)
        else:
            print(f"{'N/A':>10}", end="")
    if pi_scores:
        mean = sum(pi_scores) / len(pi_scores)
        print(f"{mean:>10.3f}")
    else:
        print()

    print("\nPageIndex approach: hierarchical CHANGELOG tree navigation via LLM reasoning")
    print("(no vector search — LLM reads TOC, selects sections, extracts answer)")


if __name__ == "__main__":
    main()
