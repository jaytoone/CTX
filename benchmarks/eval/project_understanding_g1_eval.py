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
            ctx_query="What modules are needed to understand adaptive_trigger",
        ),
        ProjectQuestion(
            qid="pu_h03", category="H", difficulty="medium",
            question="What external codebases were used for evaluation? Name at least two.",
            keywords=["Flask", "FastAPI", "Requests"],
            ground_truth="Evaluated on Flask, FastAPI, and Requests codebases",
            ctx_query="Find code related to Flask FastAPI Requests evaluation",
        ),
        # ── A (Architecture): How is it structured? ──
        ProjectQuestion(
            qid="pu_a01", category="A", difficulty="easy",
            question="What are the main source code packages/directories in this project?",
            keywords=["retrieval", "trigger", "analysis"],
            ground_truth="src/retrieval/, src/trigger/, src/analysis/",
            ctx_query="Show me the code for retrieval trigger analysis modules",
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
            ctx_query="Find the function AdaptiveTriggerRetriever and show its implementation",
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
            ctx_query="Find code related to FastAPI evaluation and IMPLICIT_CONTEXT weakness",
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
            question="What specific R@5 score does CTX achieve on Flask vs FastAPI external codebases?",
            keywords=["0.66", "0.65", "0.40", "0.41", "Flask", "FastAPI"],
            ground_truth="Flask R@5~0.66, FastAPI R@5~0.41 — large gap due to FastAPI structural issues",
            ctx_query="Find benchmark results for Flask and FastAPI external codebase evaluation",
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


def score_answer_keyword(response: str, question: ProjectQuestion) -> Tuple[float, List[str], List[str]]:
    """Legacy keyword-based scoring (kept for comparison only)."""
    response_lower = response.lower()
    matched = []
    missed = []
    for kw in question.keywords:
        kw_lower = kw.lower().strip()
        if not kw_lower:
            continue
        if kw_lower in response_lower:
            matched.append(kw)
        elif len(kw_lower) > 5 and any(part in response_lower for part in kw_lower.split("_")):
            matched.append(kw)
        else:
            missed.append(kw)
    total = len(matched) + len(missed)
    accuracy = len(matched) / total if total > 0 else 0.0
    return accuracy, matched, missed


def score_answer_llm_judge(
    client, response: str, question: ProjectQuestion
) -> Tuple[float, str]:
    """LLM-as-judge factual accuracy scoring.

    Instead of keyword matching, asks a separate LLM call to judge whether
    the response factually answers the question correctly.

    Returns (score 0.0-1.0, judge_reasoning).
    """
    judge_prompt = f"""Rate this answer's factual accuracy from 0 to 10.

Question: {question.question}
Correct answer: {question.ground_truth}
Key facts: {', '.join(question.keywords)}

Answer to rate:
{response[:800]}

Reply with ONLY a number from 0 to 10. Nothing else."""

    try:
        msg = client.messages.create(
            model=os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5"),
            max_tokens=100,
            system="You are a strict, objective answer quality judge. Be conservative with scores.",
            messages=[{"role": "user", "content": judge_prompt}],
        )
        text_parts = []
        for block in msg.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        judge_text = " ".join(text_parts).strip()

        # Parse: expect a single number 0-10
        numbers = re.findall(r'(\d+(?:\.\d+)?)', judge_text)
        if numbers:
            raw = float(numbers[0])
            score = raw / 10.0 if raw > 1.0 else raw  # normalize to 0-1
            score = max(0.0, min(1.0, score))
            return score, judge_text[:100]
        return 0.5, f"[PARSE FAIL: {judge_text[:80]}]"
    except Exception as e:
        return 0.5, f"[JUDGE ERROR: {e}]"


def build_random_context(retriever: AdaptiveTriggerRetriever, k: int = 5) -> str:
    """Build context from k RANDOM files (baseline for CTX comparison)."""
    import random as _random
    _random.seed(42)
    if not retriever.file_paths:
        return ""
    selected = _random.sample(retriever.file_paths, min(k, len(retriever.file_paths)))
    context_parts = []
    for fpath in selected:
        content = retriever.files.get(fpath, "")
        context_parts.append(f"--- {fpath} ---\n{content[:2000]}")
    return "\n\n".join(context_parts)


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

    # Build random baseline context (same for all questions — fair comparison)
    random_context = build_random_context(retriever, k=k)

    # Evaluate each question with 3-arm comparison
    results = []
    ctx_scores, random_scores, none_scores = [], [], []

    for q in questions:
        print(f"  Evaluating [{q.category}] {q.question[:40]}...")

        # ARM 1: CTX retrieval (actual adaptive_trigger.retrieve() call)
        ctx_context = build_ctx_context(retriever, q.ctx_query, k=k)

        # ARM 2: Random files (baseline — isolates CTX contribution)
        # ARM 3: No context (general knowledge only)

        if dry_run:
            ctx_answer = simulate_with_ctx(q)
            random_answer = "Based on some project files, this appears to be a software project."
            none_answer = simulate_without_ctx(q)
            ctx_score, ctx_reason = 0.8, "dry-run"
            random_score, random_reason = 0.3, "dry-run"
            none_score, none_reason = 0.1, "dry-run"
            # Also compute legacy keyword scores for comparison
            kw_ctx, _, _ = score_answer_keyword(ctx_answer, q)
            kw_none, _, _ = score_answer_keyword(none_answer, q)
        else:
            ctx_answer = ask_llm(client, q.question, context=ctx_context)
            random_answer = ask_llm(client, q.question, context=random_context)
            none_answer = ask_llm(client, q.question, context="")

            # LLM-as-judge scoring (factual accuracy)
            ctx_score, ctx_reason = score_answer_llm_judge(client, ctx_answer, q)
            random_score, random_reason = score_answer_llm_judge(client, random_answer, q)
            none_score, none_reason = score_answer_llm_judge(client, none_answer, q)

            # Legacy keyword scores for comparison
            kw_ctx, _, _ = score_answer_keyword(ctx_answer, q)
            kw_none, _, _ = score_answer_keyword(none_answer, q)

        ctx_scores.append(ctx_score)
        random_scores.append(random_score)
        none_scores.append(none_score)

        results.append({
            "qid": q.qid,
            "category": q.category,
            "question": q.question,
            "difficulty": q.difficulty,
            # LLM-as-judge scores (primary metric)
            "ctx_score": round(ctx_score, 3),
            "random_score": round(random_score, 3),
            "none_score": round(none_score, 3),
            "ctx_vs_random_delta": round(ctx_score - random_score, 3),
            "ctx_vs_none_delta": round(ctx_score - none_score, 3),
            "judge_reason_ctx": ctx_reason,
            "judge_reason_random": random_reason,
            # Legacy keyword scores (for comparison only)
            "keyword_ctx": round(kw_ctx, 3),
            "keyword_none": round(kw_none, 3),
        })

    # Aggregates
    mean_ctx = float(np.mean(ctx_scores)) if ctx_scores else 0.0
    mean_random = float(np.mean(random_scores)) if random_scores else 0.0
    mean_none = float(np.mean(none_scores)) if none_scores else 0.0

    # Per-category
    by_category = {}
    for cat in ["H", "A", "D", "K"]:
        cat_results = [r for r in results if r["category"] == cat]
        if cat_results:
            by_category[cat] = {
                "n": len(cat_results),
                "ctx": round(float(np.mean([r["ctx_score"] for r in cat_results])), 3),
                "random": round(float(np.mean([r["random_score"] for r in cat_results])), 3),
                "none": round(float(np.mean([r["none_score"] for r in cat_results])), 3),
            }

    output = {
        "eval_type": "project_understanding_g1_v2",
        "scoring": "llm_as_judge (factual accuracy)",
        "arms": ["CTX_retrieve", "random_files", "no_context"],
        "project_path": project_path,
        "timestamp": datetime.now().isoformat(),
        "n_questions": len(questions),
        "k": k,
        "dry_run": dry_run,
        "overall": {
            "ctx_accuracy": round(mean_ctx, 4),
            "random_accuracy": round(mean_random, 4),
            "none_accuracy": round(mean_none, 4),
            "ctx_vs_random_delta": round(mean_ctx - mean_random, 4),
            "ctx_vs_none_delta": round(mean_ctx - mean_none, 4),
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
    print(f"RESULTS — G1 Project Understanding (LLM-as-Judge)")
    print(f"{'='*60}")
    o = result["overall"]
    print(f"CTX accuracy:         {o['ctx_accuracy']:.4f}")
    print(f"Random accuracy:      {o['random_accuracy']:.4f}")
    print(f"No-context accuracy:  {o['none_accuracy']:.4f}")
    print(f"CTX vs Random delta:  {o['ctx_vs_random_delta']:+.4f}  ← CTX contribution")
    print(f"CTX vs None delta:    {o['ctx_vs_none_delta']:+.4f}")

    print(f"\nBy category:")
    cat_names = {"H": "History", "A": "Architecture", "D": "Direction", "K": "Knowledge"}
    for cat, data in result.get("by_category", {}).items():
        name = cat_names.get(cat, cat)
        print(f"  {name:<15} CTX={data['ctx']:.3f}  Random={data['random']:.3f}  None={data['none']:.3f}  n={data['n']}")

    # Save
    out_path = RESULTS_DIR / "project_understanding_g1_results.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\nSaved -> {out_path}")


if __name__ == "__main__":
    main()
