#!/usr/bin/env python3
"""
project_understanding_g1_eval.py — G1 Project Understanding Evaluation

Measures: Can an LLM correctly understand a project's work history and direction
using ONLY code/docs (no persistent_memory, no session_log, no git log)?

This is the TRUE G1: "프로젝트 작업 히스토리/방향에 대한 이해도"

Protocol:
  1. CTX indexes a real project (code + docs)
  2. User asks project-state questions (history, architecture, direction, decisions)
  3. WITH CTX: LLM gets CTX-retrieved file context → answers question
  4. WITHOUT CTX: LLM gets NO context → answers from general knowledge only
  5. Score: answer accuracy against ground truth (extracted from git/docs)

Question categories:
  H (History):     "What was recently changed?" "What was the last major feature?"
  A (Architecture): "What are the main components?" "How does X connect to Y?"
  D (Direction):   "What are the planned next steps?" "What's the current TODO?"
  K (Knowledge):   "Why was X designed this way?" "What constraints exist?"

Ground truth sources:
  - CLAUDE.md (project description, decisions, next steps)
  - docs/ directory (architecture, research notes)
  - Code structure (imports, class hierarchy)
  - README.md (overview, setup)

Usage:
  python3 benchmarks/eval/project_understanding_g1_eval.py [--project-path .] [--dry-run]
"""

import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

RESULTS_DIR = ROOT / "benchmarks" / "results"


# ─── Scenario Definition ───────────────────────────────────────────────────

@dataclass
class ProjectQuestion:
    """A question about a project's state, with ground truth answer."""
    qid: str
    category: str           # H=history, A=architecture, D=direction, K=knowledge
    question: str           # Natural language question
    keywords: List[str]     # Expected keywords in correct answer
    ground_truth: str       # Full correct answer (for reference)
    ctx_query: str          # Query to send to CTX adaptive_trigger
    difficulty: str = "medium"  # easy/medium/hard


def extract_ground_truth_from_project(project_path: str) -> List[ProjectQuestion]:
    """Auto-generate questions + ground truth from project structure.

    Reads CLAUDE.md, docs/, README.md to extract factual claims about the project,
    then generates questions that test understanding of those facts.
    """
    questions = []
    qid = 0

    # ── Source 1: CLAUDE.md (richest source of project state)
    claude_md = os.path.join(project_path, "CLAUDE.md")
    if os.path.exists(claude_md):
        with open(claude_md, "r", errors="replace") as f:
            content = f.read()

        # H: History questions from "현재 성과" or "Phase" sections
        # Extract section headings as topics — use ASCII-friendly keywords
        headings = re.findall(r'^##\s+(.+)$', content, re.MULTILINE)
        if headings:
            # Extract English/numeric tokens from headings for matching
            heading_keywords = []
            for h in headings[:5]:
                tokens = re.findall(r'[a-zA-Z]{3,}|R@\d+|\d{4}', h)
                heading_keywords.extend(tokens[:2])
            heading_keywords = list(set(heading_keywords))[:5]
            if heading_keywords:
                questions.append(ProjectQuestion(
                    qid=f"pu_{qid:03d}", category="A", difficulty="easy",
                    question="What are the main sections/topics covered in this project's documentation?",
                    keywords=heading_keywords,
                    ground_truth=f"Main sections: {', '.join(headings[:5])}",
                    ctx_query="Show me the project overview and main documentation structure",
                ))
                qid += 1

        # Extract key metrics/numbers — use numeric values as keywords
        metrics = re.findall(r'(R@\d+)\s*[=:]\s*([\d.]+)', content)
        if metrics:
            # Use metric names AND values as keywords (language-independent)
            metric_keywords = [m[0] for m in metrics[:3]] + [m[1] for m in metrics[:3]]
            questions.append(ProjectQuestion(
                qid=f"pu_{qid:03d}", category="K", difficulty="medium",
                question="What are the key performance metrics (like R@5, NDCG) and their values?",
                keywords=metric_keywords,
                ground_truth=f"Key metrics: {', '.join(f'{m[0]}={m[1]}' for m in metrics[:3])}",
                ctx_query="Find code related to benchmark evaluation and retrieval metrics",
            ))
            qid += 1

        # D: Direction questions from "다음 세션" or "TODO" or "후보 작업" sections
        next_steps = re.findall(
            r'(?:다음|next|TODO|future|planned|후보|즉시|중기|장기)[^\n]*\n((?:\s*[-*\d].+\n)+)',
            content, re.IGNORECASE)
        if next_steps:
            steps_text = next_steps[0].strip()
            step_items = re.findall(r'[-*\d]+\.?\s*(.+)', steps_text)
            if step_items:
                # Extract English/technical keywords from step items
                step_keywords = []
                for item in step_items[:3]:
                    tokens = re.findall(r'[a-zA-Z_]{4,}|R@\d+|[\d.]+(?:%|%p)', item)
                    step_keywords.extend(tokens[:2])
                step_keywords = list(set(step_keywords))[:5]
                if step_keywords:
                    questions.append(ProjectQuestion(
                        qid=f"pu_{qid:03d}", category="D", difficulty="medium",
                        question="What are the planned next steps or future work for this project?",
                        keywords=step_keywords,
                        ground_truth=f"Next steps: {'; '.join(step_items[:3])}",
                        ctx_query="Show me project roadmap and planned improvements",
                    ))
                    qid += 1

        # K: Key decisions — extract technical terms
        decision_blocks = re.findall(
            r'(?:BM25|TF-IDF|dense|heuristic|import.graph|AST)[^\n]+',
            content, re.IGNORECASE)
        if decision_blocks:
            decision_keywords = []
            for block in decision_blocks[:3]:
                tokens = re.findall(r'[a-zA-Z_]{4,}|BM25|TF-IDF|R@\d+', block)
                decision_keywords.extend(tokens[:2])
            decision_keywords = list(set(decision_keywords))[:5]
            if decision_keywords:
                questions.append(ProjectQuestion(
                    qid=f"pu_{qid:03d}", category="K", difficulty="hard",
                    question="What key technical decisions were made in this project (e.g., algorithm choices)?",
                    keywords=decision_keywords,
                    ground_truth=f"Technical decisions: {'; '.join(decision_blocks[:3])}",
                    ctx_query="Find documentation about technical decisions and algorithm choices",
                ))
                qid += 1

    # ── Source 2: Code structure (architecture questions)
    src_dir = os.path.join(project_path, "src")
    if os.path.isdir(src_dir):
        # Find top-level modules
        modules = []
        for item in sorted(os.listdir(src_dir)):
            item_path = os.path.join(src_dir, item)
            if os.path.isdir(item_path) and not item.startswith("_"):
                modules.append(item)
            elif item.endswith(".py") and not item.startswith("_"):
                modules.append(item.replace(".py", ""))

        if modules:
            questions.append(ProjectQuestion(
                qid=f"pu_{qid:03d}", category="A", difficulty="easy",
                question="What are the main source code modules/packages in this project?",
                keywords=modules[:5],
                ground_truth=f"Main modules: {', '.join(modules[:5])}",
                ctx_query="Show me the project source code structure and main modules",
            ))
            qid += 1

    # ── Source 3: Key Python files (architecture deep-dive)
    key_files = []
    for root_d, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"
                   and d != "node_modules" and d != ".git"]
        for fname in files:
            if fname.endswith(".py") and not fname.startswith("test_"):
                fpath = os.path.relpath(os.path.join(root_d, fname), project_path)
                key_files.append(fpath)

    if key_files:
        # Find the "main" entry point or core module
        core_candidates = [f for f in key_files if any(kw in f.lower()
                          for kw in ["main", "app", "core", "engine", "trigger", "retrieval"])]
        if core_candidates:
            core_file = core_candidates[0]
            questions.append(ProjectQuestion(
                qid=f"pu_{qid:03d}", category="A", difficulty="medium",
                question=f"What is the role of {core_file} in this project?",
                keywords=[os.path.basename(core_file).replace(".py", "")],
                ground_truth=f"{core_file} is a core module in the project",
                ctx_query=f"Show me the code for {os.path.basename(core_file).replace('.py', '')}",
            ))
            qid += 1

    # ── Source 4: README.md
    readme = os.path.join(project_path, "README.md")
    if os.path.exists(readme):
        with open(readme, "r", errors="replace") as f:
            readme_content = f.read()[:3000]

        # Extract project name/description from first heading + paragraph
        first_heading = re.search(r'^#\s+(.+)$', readme_content, re.MULTILINE)
        first_para = re.search(r'^#.+\n\n(.+?)(?:\n\n|\n#)', readme_content, re.MULTILINE | re.DOTALL)

        if first_heading:
            project_name = first_heading.group(1).strip()
            desc = first_para.group(1).strip() if first_para else ""
            desc_keywords = [w for w in re.findall(r'\b[a-zA-Z]{4,}\b', desc) if w.lower() not in
                            {"this", "that", "with", "from", "have", "been", "will", "your"}][:5]
            questions.append(ProjectQuestion(
                qid=f"pu_{qid:03d}", category="H", difficulty="easy",
                question="What is this project about? Give a brief description.",
                keywords=[project_name] + desc_keywords[:3],
                ground_truth=f"{project_name}: {desc[:200]}",
                ctx_query="Show me the project overview and description",
            ))
            qid += 1

    # ── Source 5: docs/ directory structure
    docs_dir = os.path.join(project_path, "docs")
    if os.path.isdir(docs_dir):
        doc_files = []
        for root_d, dirs, files in os.walk(docs_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if fname.endswith(".md"):
                    rel = os.path.relpath(os.path.join(root_d, fname), docs_dir)
                    doc_files.append(rel)

        if doc_files:
            # Recent research docs (by filename date pattern)
            dated_docs = sorted(
                [d for d in doc_files if re.search(r'2026\d{4}', d)],
                reverse=True
            )
            if dated_docs:
                recent = dated_docs[:3]
                questions.append(ProjectQuestion(
                    qid=f"pu_{qid:03d}", category="H", difficulty="medium",
                    question="What research or investigation has been done recently in this project?",
                    keywords=[os.path.basename(d).replace(".md", "")[:30] for d in recent],
                    ground_truth=f"Recent docs: {', '.join(recent[:3])}",
                    ctx_query="Find recent research documents and investigation notes",
                ))
                qid += 1

    return questions


def score_answer(response: str, question: ProjectQuestion) -> Tuple[float, List[str], List[str]]:
    """Score LLM response against ground truth keywords.

    Returns (accuracy, matched_keywords, missed_keywords).
    """
    response_lower = response.lower()
    matched = []
    missed = []

    for kw in question.keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        # Check for keyword presence (allow partial matches for long keywords)
        if kw_lower in response_lower:
            matched.append(kw)
        elif len(kw_lower) > 5 and any(part in response_lower for part in kw_lower.split("_")):
            matched.append(kw)  # partial match for compound terms
        else:
            missed.append(kw)

    total = len(matched) + len(missed)
    accuracy = len(matched) / total if total > 0 else 0.0
    return accuracy, matched, missed


def build_ctx_context(retriever: AdaptiveTriggerRetriever, query: str, k: int = 5) -> str:
    """Get CTX-retrieved context for a query."""
    result = retriever.retrieve("g1_eval", query, k=k)
    context_parts = []
    for fpath in result.retrieved_files[:k]:
        content = retriever.files.get(fpath, "")
        # Truncate to first 2000 chars per file
        context_parts.append(f"--- {fpath} ---\n{content[:2000]}")
    return "\n\n".join(context_parts)


def ask_llm(client, question: str, context: str = "") -> str:
    """Ask LLM a project question with optional context."""
    if context:
        system = "You are analyzing a software project. Use ONLY the provided code/doc context to answer."
        user = f"Context:\n{context}\n\nQuestion: {question}\n\nAnswer concisely based on the context above."
    else:
        system = "You are analyzing a software project. Answer based on your general knowledge only."
        user = f"Question: {question}\n\nAnswer concisely."

    try:
        msg = client.messages.create(
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        # Handle ThinkingBlock + TextBlock responses (MiniMax M2.5)
        text_parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        return " ".join(text_parts).strip() if text_parts else "[NO TEXT IN RESPONSE]"
    except Exception as e:
        return f"[LLM ERROR: {e}]"


def simulate_with_ctx(question: ProjectQuestion) -> str:
    """Simulate CTX-assisted answer (for dry-run mode)."""
    return f"Based on the project files, {', '.join(question.keywords[:3])} are relevant. " + question.ground_truth[:100]


def simulate_without_ctx(question: ProjectQuestion) -> str:
    """Simulate no-context answer (for dry-run mode)."""
    return "I don't have specific information about this project's current state."


def run_evaluation(
    project_path: str = ".",
    k: int = 5,
    dry_run: bool = False,
) -> dict:
    """Run G1 project understanding evaluation."""
    project_path = os.path.abspath(project_path)

    # Generate questions from project
    questions = extract_ground_truth_from_project(project_path)
    print(f"Generated {len(questions)} project understanding questions")
    for q in questions:
        print(f"  [{q.category}] {q.question[:60]}... ({len(q.keywords)} keywords)")

    if not questions:
        print("ERROR: No questions generated. Check project structure.")
        return {"error": "no_questions"}

    # Build CTX retriever
    retriever = AdaptiveTriggerRetriever(codebase_dir=project_path, use_dense=False)

    # Get LLM client (or use dry-run simulation)
    client = None
    if not dry_run:
        # Load API keys
        env_file = os.path.expanduser("~/.claude/env/shared.env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, val = line.split("=", 1)
                        os.environ[key.strip()] = val.strip()  # force override
        client = get_llm_client()
        if client is None:
            print("WARN: No LLM client available, falling back to dry-run")
            dry_run = True

    # Evaluate each question
    results = []
    with_scores = []
    without_scores = []

    for q in questions:
        # WITH CTX: retrieve context, then ask LLM
        ctx_context = build_ctx_context(retriever, q.ctx_query, k=k)

        if dry_run:
            with_answer = simulate_with_ctx(q)
            without_answer = simulate_without_ctx(q)
        else:
            with_answer = ask_llm(client, q.question, context=ctx_context)
            without_answer = ask_llm(client, q.question, context="")

        with_acc, with_matched, with_missed = score_answer(with_answer, q)
        without_acc, without_matched, without_missed = score_answer(without_answer, q)

        with_scores.append(with_acc)
        without_scores.append(without_acc)

        results.append({
            "qid": q.qid,
            "category": q.category,
            "question": q.question,
            "difficulty": q.difficulty,
            "with_ctx_accuracy": round(with_acc, 3),
            "without_ctx_accuracy": round(without_acc, 3),
            "delta": round(with_acc - without_acc, 3),
            "with_matched": with_matched,
            "with_missed": with_missed,
            "without_matched": without_matched,
        })

    # Aggregates
    mean_with = float(np.mean(with_scores)) if with_scores else 0.0
    mean_without = float(np.mean(without_scores)) if without_scores else 0.0
    delta = mean_with - mean_without

    # Per-category
    by_category = {}
    for cat in ["H", "A", "D", "K"]:
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            by_category[cat] = {
                "n": len(cat_results),
                "with_ctx": round(float(np.mean([r["with_ctx_accuracy"] for r in cat_results])), 3),
                "without_ctx": round(float(np.mean([r["without_ctx_accuracy"] for r in cat_results])), 3),
            }

    output = {
        "eval_type": "project_understanding_g1",
        "project_path": project_path,
        "timestamp": datetime.now().isoformat(),
        "n_questions": len(questions),
        "k": k,
        "dry_run": dry_run,
        "overall": {
            "with_ctx_accuracy": round(mean_with, 4),
            "without_ctx_accuracy": round(mean_without, 4),
            "delta": round(delta, 4),
        },
        "by_category": by_category,
        "per_question": results,
    }

    return output


def get_llm_client():
    """Get LLM client for evaluation."""
    try:
        import anthropic
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
        if minimax_key and minimax_url:
            return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
    except ImportError:
        pass
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-path", default=".")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("G1 Project Understanding Evaluation")
    print("=" * 60)

    result = run_evaluation(args.project_path, args.k, args.dry_run)

    if "error" in result:
        print(f"ERROR: {result['error']}")
        return

    print(f"\n{'='*60}")
    print(f"RESULTS — G1 Project Understanding")
    print(f"{'='*60}")
    o = result["overall"]
    print(f"WITH CTX accuracy:    {o['with_ctx_accuracy']:.4f}")
    print(f"WITHOUT CTX accuracy: {o['without_ctx_accuracy']:.4f}")
    print(f"Delta (CTX benefit):  {o['delta']:+.4f}")

    print(f"\nBy category:")
    cat_names = {"H": "History", "A": "Architecture", "D": "Direction", "K": "Knowledge"}
    for cat, data in result.get("by_category", {}).items():
        name = cat_names.get(cat, cat)
        print(f"  {name:<15} WITH={data['with_ctx']:.3f}  WITHOUT={data['without_ctx']:.3f}  n={data['n']}")

    # Save
    out_path = RESULTS_DIR / "project_understanding_g1_results.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
