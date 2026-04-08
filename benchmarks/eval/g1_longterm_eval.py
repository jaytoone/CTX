#!/usr/bin/env python3
"""
G1 Long-Term Memory Evaluation Framework

Evaluates CTX G1's ability to retain and recall important decision history over time.
Based on research findings from LongMemEval (ICLR 2025), LoCoMo, GitGoodBench.

Usage:
    python g1_longterm_eval.py --repo-path /path/to/CTX --output results.json
"""

import argparse
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class DecisionCommit:
    """Represents a decision commit extracted from git log"""
    def __init__(self, hash: str, date: datetime, subject: str, body: str, files_changed: List[str]):
        self.hash = hash
        self.date = date
        self.subject = subject
        self.body = body
        self.files_changed = files_changed
        self.decision_type = self._extract_decision_type()

    def _extract_decision_type(self) -> str:
        """Extract decision type from commit message"""
        patterns = [
            (r"^feat:", "feat"),
            (r"^fix:", "fix"),
            (r"^refactor:", "refactor"),
            (r"^perf:", "perf"),
            (r"^v\d+\.\d+\.\d+ - (feat|fix|refactor)", "version"),
        ]
        for pattern, dtype in patterns:
            if re.search(pattern, self.subject, re.IGNORECASE):
                return dtype
        return "other"

    def to_dict(self) -> Dict:
        return {
            "hash": self.hash,
            "date": self.date.isoformat(),
            "subject": self.subject,
            "body": self.body,
            "files_changed": self.files_changed,
            "decision_type": self.decision_type,
        }


def extract_decision_commits(repo_path: Path, cutoff_date: Optional[datetime] = None) -> List[DecisionCommit]:
    """
    Extract decision commits from git log using CTX's git-memory patterns.

    Args:
        repo_path: Path to git repository
        cutoff_date: Evaluation cutoff (SWE-bench style temporal isolation)

    Returns:
        List of DecisionCommit objects
    """
    # Decision patterns adapted for CTX's date-prefix format
    # CTX uses: "YYYYMMDD Description: details" format
    DECISION_PATTERNS = [
        r"^\d{8}",  # Date-prefix (main CTX pattern)
        r"^feat:",
        r"^fix:",
        r"^refactor:",
        r"^perf:",
        r"^security:",
        r"^v\d+\.\d+\.\d+ - (feat|fix|refactor)",
    ]

    # Additional filters: skip commits that are just version bumps or trivial
    SKIP_PATTERNS = [
        r"^v\d+\.\d+\.\d+$",  # Pure version tag
        r"^wip\b",  # Work in progress
        r"^fixup\b",  # Fixup commits
    ]

    # Get git log - simplified format
    cmd = [
        "git", "log",
        "--format=%H|%aI|%s",  # hash|date|subject only (body via separate call if needed)
        "-n", "500",  # Get last 500 commits for temporal coverage
    ]

    if cutoff_date:
        cmd.extend(["--before", cutoff_date.isoformat()])

    result = subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True
    )

    commits = []

    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue

        parts = line.split('|')
        if len(parts) < 3:
            continue

        commit_hash, date_str, subject = parts[0], parts[1], '|'.join(parts[2:])  # Handle | in subject

        # Check if this is a decision commit
        is_decision = any(re.search(pattern, subject, re.IGNORECASE) for pattern in DECISION_PATTERNS)
        is_skip = any(re.search(pattern, subject, re.IGNORECASE) for pattern in SKIP_PATTERNS)

        if is_decision and not is_skip:
            # Get commit body and files
            body_result = subprocess.run(
                ["git", "show", "--format=%b", "--no-patch", commit_hash],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            body = body_result.stdout.strip()

            files_result = subprocess.run(
                ["git", "show", "--name-only", "--format=", commit_hash],
                cwd=repo_path,
                capture_output=True,
                text=True
            )
            files = [f for f in files_result.stdout.strip().split('\n') if f.strip()]

            commits.append({
                'hash': commit_hash,
                'date': datetime.fromisoformat(date_str.replace('Z', '+00:00')),
                'subject': subject,
                'body': body,
                'files': files
            })

    # Convert to DecisionCommit objects
    decision_commits = [
        DecisionCommit(
            hash=c['hash'],
            date=c['date'],
            subject=c['subject'],
            body=c['body'],
            files_changed=c['files']
        )
        for c in commits
    ]

    return decision_commits


def compute_age_bucket(commit_date: datetime, now: Optional[datetime] = None) -> str:
    """Compute age bucket for a commit"""
    if now is None:
        now = datetime.now(commit_date.tzinfo)

    age_days = (now - commit_date).days

    if age_days <= 7:
        return "0-7d"
    elif age_days <= 30:
        return "7-30d"
    elif age_days <= 90:
        return "30-90d"
    else:
        return "90d+"


def extract_topic(commit: DecisionCommit) -> str:
    """Extract main topic from commit, handling date-prefix format"""
    subject = commit.subject

    # Remove date prefix (YYYYMMDD format)
    subject = re.sub(r"^\d{8}\s+", "", subject)

    # Remove decision type prefix
    subject = re.sub(r"^(feat|fix|refactor|perf|security):\s*", "", subject, flags=re.IGNORECASE)

    # Remove version prefix
    subject = re.sub(r"^v\d+\.\d+\.\d+\s*[-:]\s*", "", subject)

    # Take first meaningful phrase (up to first colon or 60 chars)
    if ':' in subject:
        subject = subject.split(':')[0]

    # Limit length
    words = subject.split()[:8]
    topic = " ".join(words)

    # Truncate if too long
    if len(topic) > 60:
        topic = topic[:60].rsplit(' ', 1)[0] + "..."

    return topic.strip()


def extract_action(commit: DecisionCommit) -> str:
    """Extract action from commit for rationale questions"""
    topic = extract_topic(commit)
    subject_lower = commit.subject.lower()

    # Determine verb based on commit patterns
    if "implement" in subject_lower or re.search(r"^\d{8}", commit.subject):
        return f"implement {topic}"
    elif "add" in subject_lower or "feat:" in subject_lower:
        return f"add {topic}"
    elif "fix" in subject_lower or "fix:" in subject_lower:
        return f"fix {topic}"
    elif "refactor" in subject_lower:
        return f"refactor {topic}"
    elif "perf:" in subject_lower or "optimize" in subject_lower:
        return f"optimize {topic}"
    else:
        return topic


def has_meaningful_message(commit: DecisionCommit) -> bool:
    """Check if commit has a meaningful message beyond just the subject"""
    return len(commit.body.strip()) > 20


def generate_qa_pairs(
    decision_commits: List[DecisionCommit],
    query_types: List[str] = ["type1", "type2"]
) -> List[Dict]:
    """
    Generate QA pairs from decision commits.

    Type 1 (automated): timestamp/hash queries
    Type 2 (semi-automated): rationale extraction

    Args:
        decision_commits: List of DecisionCommit objects
        query_types: Types of queries to generate

    Returns:
        List of QA pair dictionaries
    """
    qa_pairs = []
    now = datetime.now(decision_commits[0].date.tzinfo) if decision_commits else datetime.now()

    for commit in decision_commits:
        # Type 1: Simple fact query
        if "type1" in query_types:
            topic = extract_topic(commit)
            qa_pairs.append({
                "query": f"When did we implement {topic}?",
                "query_type": "type1",
                "ground_truth": {
                    "commit_hash": commit.hash,
                    "timestamp": commit.date.isoformat(),
                    "subject": commit.subject,
                },
                "age_bucket": compute_age_bucket(commit.date, now),
            })

        # Type 2: Rationale query (for commits with meaningful messages)
        if "type2" in query_types and has_meaningful_message(commit):
            action = extract_action(commit)
            qa_pairs.append({
                "query": f"Why did we {action}?",
                "query_type": "type2",
                "ground_truth": {
                    "commit_hash": commit.hash,
                    "rationale": commit.body.strip(),
                    "subject": commit.subject,
                },
                "age_bucket": compute_age_bucket(commit.date, now),
            })

    return qa_pairs


def compute_decision_recall(ctx_output: List[str], ground_truth: List[str], k: int = 5) -> float:
    """
    Metric: Decision Recall@K

    Args:
        ctx_output: List of commit hashes returned by CTX
        ground_truth: List of expected commit hashes
        k: top-K to consider

    Returns:
        recall@K score
    """
    if not ground_truth:
        return 0.0

    ctx_top_k = set(ctx_output[:k])
    gt_set = set(ground_truth)

    return len(ctx_top_k & gt_set) / len(gt_set)


def extract_keywords(text: str) -> set:
    """Extract keywords from text for deterministic comparison"""
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or', 'but', 'is', 'are', 'was', 'were'}
    words = re.findall(r'\b\w+\b', text.lower())
    return set(w for w in words if w not in stop_words and len(w) > 2)


def compute_rationale_f1_deterministic(ctx_rationale: str, gt_rationale: str) -> float:
    """
    Deterministic component of Rationale F1: keyword overlap

    Args:
        ctx_rationale: CTX's extracted rationale text
        gt_rationale: Ground truth rationale

    Returns:
        F1 score based on keyword overlap
    """
    ctx_keywords = extract_keywords(ctx_rationale)
    gt_keywords = extract_keywords(gt_rationale)

    if not ctx_keywords or not gt_keywords:
        return 0.0

    intersection = len(ctx_keywords & gt_keywords)

    if intersection == 0:
        return 0.0

    precision = intersection / len(ctx_keywords) if ctx_keywords else 0
    recall = intersection / len(gt_keywords) if gt_keywords else 0

    if precision + recall == 0:
        return 0.0

    return 2 * precision * recall / (precision + recall)


def main():
    parser = argparse.ArgumentParser(description="G1 Long-Term Memory Evaluation")
    parser.add_argument("--repo-path", default="/home/jayone/Project/CTX", help="Path to git repository")
    parser.add_argument("--output", default="benchmarks/results/g1_longterm_eval.json", help="Output file")
    parser.add_argument("--cutoff-days", type=int, default=None, help="Temporal cutoff (days before today)")
    parser.add_argument("--query-types", nargs="+", default=["type1", "type2"], help="Query types to generate")
    args = parser.parse_args()

    repo_path = Path(args.repo_path)
    output_path = repo_path / args.output

    print("[1/5] Extracting decision commits...")
    cutoff_date = datetime.now() - timedelta(days=args.cutoff_days) if args.cutoff_days else None
    decision_commits = extract_decision_commits(repo_path, cutoff_date)
    print(f"  Found {len(decision_commits)} decision commits")

    if not decision_commits:
        print("ERROR: No decision commits found. Check git history and decision patterns.")
        return 1

    print("[2/5] Generating QA pairs...")
    qa_pairs = generate_qa_pairs(decision_commits, query_types=args.query_types)
    print(f"  Generated {len(qa_pairs)} QA pairs")

    # Save QA pairs for manual review
    qa_pairs_path = repo_path / "benchmarks/results/g1_qa_pairs.json"
    qa_pairs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(qa_pairs_path, "w") as f:
        json.dump(qa_pairs, f, indent=2)
    print(f"  Saved to {qa_pairs_path}")

    # Save decision commits
    commits_path = repo_path / "benchmarks/results/g1_decision_commits.json"
    with open(commits_path, "w") as f:
        json.dump([c.to_dict() for c in decision_commits], f, indent=2, default=str)
    print(f"  Saved commits to {commits_path}")

    print("\n[3/5] Evaluation baselines not yet implemented")
    print("  TODO: Implement baseline evaluation (no_ctx, full_dump, g1_raw, g1_filtered)")

    print("\n[4/5] Computing metrics not yet implemented")
    print("  TODO: Implement metric computation")

    print("\n[5/5] Report generation not yet implemented")
    print("  TODO: Generate comparison report")

    # Save metadata
    metadata = {
        "metadata": {
            "repo_path": str(repo_path),
            "cutoff_date": cutoff_date.isoformat() if cutoff_date else None,
            "query_types": args.query_types,
            "num_decision_commits": len(decision_commits),
            "num_qa_pairs": len(qa_pairs),
            "timestamp": datetime.now().isoformat(),
        },
        "status": "PARTIAL — QA pairs generated, baseline evaluation pending"
    }

    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nPartial results saved to {output_path}")
    print("\nNext steps:")
    print("1. Review QA pairs in benchmarks/results/g1_qa_pairs.json")
    print("2. Implement baseline evaluation functions")
    print("3. Implement LLM judge for hybrid Rationale F1 scoring")
    print("4. Run full evaluation")

    return 0


if __name__ == "__main__":
    sys.exit(main())
