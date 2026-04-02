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


def build_ctx_specific_questions() -> List[ProjectQuestion]:
    """CTX-project-specific curated questions with language-independent keywords.

    These questions test whether an LLM can understand the CTX project's
    history, architecture, direction, and key decisions using only code/docs.
    All keywords are English technical terms to ensure cross-language matching.
    """
    return [
        # ── H (History): What has been done? ──
        ProjectQuestion(
            qid="pu_h01", category="H", difficulty="easy",
            question="What is this project about? Describe its core purpose in 2-3 sentences.",
            keywords=["retrieval", "trigger", "context", "code", "deterministic"],
            ground_truth="CTX is a rule-based code/doc retrieval system using trigger classification",
            ctx_query="Show me the project overview and main README",
        ),
        ProjectQuestion(
            qid="pu_h02", category="H", difficulty="medium",
            question="What retrieval algorithm does this project use? Was it changed from an earlier approach?",
            keywords=["BM25", "TF-IDF", "adaptive_trigger"],
            ground_truth="Switched from TF-IDF to BM25 for better keyword retrieval",
            ctx_query="Find code related to BM25 and retrieval algorithm",
        ),
        ProjectQuestion(
            qid="pu_h03", category="H", difficulty="medium",
            question="What external codebases were used for evaluation? Name at least two.",
            keywords=["Flask", "FastAPI", "Requests"],
            ground_truth="Evaluated on Flask, FastAPI, and Requests codebases",
            ctx_query="Find benchmark evaluation code for external codebases",
        ),
        # ── A (Architecture): How is it structured? ──
        ProjectQuestion(
            qid="pu_a01", category="A", difficulty="easy",
            question="What are the main source code packages/directories in this project?",
            keywords=["retrieval", "trigger", "analysis"],
            ground_truth="src/retrieval/, src/trigger/, src/analysis/",
            ctx_query="Show me the project source code structure and main modules",
        ),
        ProjectQuestion(
            qid="pu_a02", category="A", difficulty="medium",
            question="What are the four trigger types used in query classification?",
            keywords=["EXPLICIT_SYMBOL", "SEMANTIC_CONCEPT", "TEMPORAL_HISTORY", "IMPLICIT_CONTEXT"],
            ground_truth="EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, IMPLICIT_CONTEXT",
            ctx_query="Show me the trigger classifier and its trigger types",
        ),
        ProjectQuestion(
            qid="pu_a03", category="A", difficulty="medium",
            question="What is the role of adaptive_trigger.py? What class does it define?",
            keywords=["AdaptiveTriggerRetriever", "retrieve", "BM25", "symbol_index", "import_graph"],
            ground_truth="adaptive_trigger.py defines AdaptiveTriggerRetriever — the core retrieval engine",
            ctx_query="Show me the code for adaptive_trigger",
        ),
        ProjectQuestion(
            qid="pu_a04", category="A", difficulty="hard",
            question="How does the import graph work in this retrieval system?",
            keywords=["import_graph", "reverse_import", "traverse", "BFS", "module_to_file"],
            ground_truth="Import graph maps file dependencies; BFS traversal finds related files",
            ctx_query="Find code related to import graph traversal and dependency tracking",
        ),
        # ── D (Direction): What's next? ──
        ProjectQuestion(
            qid="pu_d01", category="D", difficulty="medium",
            question="What are the known weaknesses or areas for improvement in this project?",
            keywords=["external", "FastAPI", "IMPLICIT_CONTEXT", "keyword"],
            ground_truth="FastAPI R@5 is low, IMPLICIT_CONTEXT needs improvement, keyword queries limited",
            ctx_query="Find documentation about project weaknesses and improvement areas",
        ),
        ProjectQuestion(
            qid="pu_d02", category="D", difficulty="hard",
            question="What benchmark metrics does this project track? Name the key ones.",
            keywords=["R@5", "NDCG", "MRR", "TES"],
            ground_truth="R@5, NDCG@5, MRR, TES (Token Efficiency Score)",
            ctx_query="Find benchmark evaluation metrics and scoring code",
        ),
        # ── K (Knowledge): Why were decisions made? ──
        ProjectQuestion(
            qid="pu_k01", category="K", difficulty="medium",
            question="Why was BM25 chosen over TF-IDF for this project?",
            keywords=["BM25", "keyword", "TF-IDF", "IDF"],
            ground_truth="BM25 replaced TF-IDF for better keyword query handling; IDF was harmful on small corpora",
            ctx_query="Find documentation about BM25 vs TF-IDF decision",
        ),
        ProjectQuestion(
            qid="pu_k02", category="K", difficulty="hard",
            question="What is the trigger classification approach? Is it ML-based or rule-based?",
            keywords=["rule-based", "deterministic", "heuristic", "pattern", "regex"],
            ground_truth="Rule-based trigger classification using regex patterns — no ML, deterministic",
            ctx_query="Show me the trigger classifier implementation",
        ),
        ProjectQuestion(
            qid="pu_k03", category="K", difficulty="hard",
            question="How does this project handle large codebases differently from small ones?",
            keywords=["large", "BM25", "fallback", "import_graph", "sparse"],
            ground_truth="Large repos use BM25 fallback when import graph is sparse; special handling for >200 files",
            ctx_query="Find code related to large codebase handling and BM25 fallback",
        ),
    ]


def extract_ground_truth_from_project(project_path: str) -> List[ProjectQuestion]:
    """Generate project understanding questions.

    Uses curated CTX-specific questions (high quality, language-independent)
    supplemented by auto-generated questions from project structure.
    """
    questions = build_ctx_specific_questions()

    # Also add auto-generated architecture questions from code structure
    src_dir = os.path.join(project_path, "src")
    qid = len(questions)
    if os.path.isdir(src_dir):
        modules = []
        for item in sorted(os.listdir(src_dir)):
            item_path = os.path.join(src_dir, item)
            if os.path.isdir(item_path) and not item.startswith("_"):
                modules.append(item)
        # Only add if we have modules not already covered
        if modules and len(modules) > 3:
            questions.append(ProjectQuestion(
                qid=f"pu_{qid:03d}", category="A", difficulty="easy",
                question="List all source code packages in this project.",
                keywords=modules[:5],
                ground_truth=f"Packages: {', '.join(modules[:5])}",
                ctx_query="Show me the project source code structure",
            ))

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
