#!/usr/bin/env python3
"""
G1 Long-Term Memory Baseline Evaluation

7 baselines:
  - no_ctx:           LLM answers without any context
  - full_dump:        Full git log dump (oracle upper bound)
  - g1_raw:           git-memory style (n=20, no filter, SIMULATION)
  - g1_filtered:      git-memory style (n=30, filter+dedup, SIMULATION)
  - git_memory_real:  Actual git-memory.py logic replicated inline (NEW)
  - bm25_retrieval:   BM25 query-time retrieval over full corpus (NEW)
  - dense_embedding:  Sentence-transformer semantic retrieval (NEW)
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── LLM client ───────────────────────────────────────────────────────────────

def get_llm_client():
    """Get LLM client (MiniMax or Anthropic)"""
    try:
        import anthropic
        minimax_key = os.environ.get("MINIMAX_API_KEY", "")
        minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
        if minimax_key and minimax_url:
            return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
        return None
    except ImportError:
        return None


def call_llm(client, system: str, user: str, model: str = "", max_tokens: int = 1024) -> str:
    """Call LLM with system + user prompt"""
    if not model:
        model = os.environ.get("MINIMAX_MODEL") or "claude-haiku-4-5-20251001"
    if client is None:
        return "[NO-CLIENT]"
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            system=system,
        )
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as exc:
        return f"[LLM-ERROR] {exc}"


# ── Git retrieval helpers ─────────────────────────────────────────────────────

def get_git_log_full(repo_path: Path, n: int = 100) -> str:
    """Full git log without filtering."""
    result = subprocess.run(
        ["git", "log", f"-n", str(n), "--format=%h|%aI|%s"],
        cwd=repo_path, capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"[GIT-ERROR] {result.stderr}"
    return result.stdout.strip()


def get_git_memory_output(repo_path: Path, n: int = 20, filtered: bool = False) -> str:
    """Simplified simulation of git-memory.py output (backward compat)."""
    n_arg = "30" if filtered else str(n)
    result = subprocess.run(
        ["git", "log", "-n", n_arg, "--format=%h %aI %s"],
        cwd=repo_path, capture_output=True, text=True
    )
    if result.returncode != 0:
        return f"[GIT-ERROR] {result.stderr}"

    lines = result.stdout.strip().split('\n')
    decisions = [
        line for line in lines
        if any(p in line.lower() for p in ['20260', 'feat:', 'fix:', 'refactor:'])
    ]
    if filtered and len(decisions) > 10:
        decisions = decisions[::2][:7]
    return "\n".join(decisions)


# ── git-memory REAL logic (replicated from ~/.claude/hooks/git-memory.py) ────

_CONV_PREFIXES = (
    "feat:", "fix:", "refactor:", "perf:", "security:", "design:", "test:",
    "feat(", "fix(", "refactor(", "perf(",
)
_VERSION_RE = re.compile(r"^v\d+\.\d+")
_DECISION_KEYWORDS = (
    "pivot", "revert", "dead-end", "rejected", "chose", "switched",
    "CONVERGED", "failed", "success", "fix", "improvement",
    "benchmark", "eval", "decision", "iter",
)
_NOISE_PREFIXES = ("# ", "wip:", "merge ", 'revert "')
_STRICT_VERSION_RE = re.compile(r"^v\d+\.\d+\.\d+")
_OMC_ITER_RE = re.compile(r"^(omc-live|live-inf)\s+iter", re.IGNORECASE)
_EMBEDDED_DECISION_RE = re.compile(
    r"\s[-\u2014]\s*(feat|fix|refactor|perf|security|design|implement|add|remove|replace|switch|migrate)",
    re.IGNORECASE
)
DECISION_CAP = 7


def _is_structural_noise(subject: str) -> bool:
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True
    if _STRICT_VERSION_RE.match(s):
        return not bool(_EMBEDDED_DECISION_RE.search(s))
    return False


def _is_decision(subject: str) -> bool:
    s = subject.strip()
    if not s:
        return False
    sl = s.lower()
    if any(sl.startswith(p) for p in _NOISE_PREFIXES):
        return False
    if any(sl.startswith(p) for p in _CONV_PREFIXES):
        return True
    if _VERSION_RE.match(s):
        return True
    return any(kw.lower() in sl for kw in _DECISION_KEYWORDS)


def _topic_key(files: List[str]):
    code = [
        f for f in files
        if f.endswith((".py", ".ts", ".tsx", ".js", ".go", ".rs"))
        and not f.startswith(("tests/", "test_", "docs/"))
    ]
    return frozenset(sorted(code)[:2]) if code else None


def _get_files_for_commit(project_dir: str, commit_hash: str) -> List[str]:
    try:
        result = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "-r", "--name-only", commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=3
        )
        if result.returncode != 0:
            return []
        return [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    except Exception:
        return []


def get_git_decisions_real(project_dir: str, n: int = 30) -> Tuple[List[str], List[str]]:
    """
    Replicated get_git_decisions() from git-memory.py.
    Returns (decisions, work_items) with DECISION_CAP=7.
    """
    try:
        result = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s\x1f%ai"],
            cwd=project_dir, capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return [], []
    except Exception:
        return [], []

    candidates, work = [], []
    seen_subjects: set = set()

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        subject = parts[1] if len(parts) == 3 else line.strip()[:120]
        commit_hash = parts[0] if len(parts) == 3 else ""

        if len(subject) > 120:
            cut = subject[:120].rfind(" ")
            subject = subject[:cut] if cut > 80 else subject[:120]

        if _is_structural_noise(subject):
            continue

        subject_key = subject[:60]
        if subject_key in seen_subjects:
            continue
        seen_subjects.add(subject_key)

        if _is_decision(subject):
            candidates.append({"hash": commit_hash, "subject": subject})
        elif len(work) < 3:
            work.append(subject)

    if not candidates:
        return [], work[:3]

    scan_limit = min(DECISION_CAP * 2, len(candidates))
    for c in candidates[:scan_limit]:
        c["files"] = _get_files_for_commit(project_dir, c["hash"]) if c["hash"] else []
        c["topic"] = _topic_key(c["files"])

    selected = []
    seen_topics: set = set()
    remainder = []
    for c in candidates[:scan_limit]:
        tk = c.get("topic")
        if tk is not None and tk not in seen_topics:
            seen_topics.add(tk)
            selected.append(c)
        else:
            remainder.append(c)

    for c in remainder:
        if len(selected) >= DECISION_CAP:
            break
        selected.append(c)

    if len(selected) < DECISION_CAP:
        for c in candidates[scan_limit:]:
            if len(selected) >= DECISION_CAP:
                break
            c.setdefault("files", [])
            c.setdefault("topic", None)
            selected.append(c)

    decisions = [c["subject"][:180] for c in selected[:DECISION_CAP]]
    return decisions[:DECISION_CAP], work[:3]


def get_git_memory_real_context(repo_path: Path) -> Tuple[str, int]:
    """Format git-memory real output as context string."""
    decisions, work = get_git_decisions_real(str(repo_path), n=30)
    if not decisions:
        return "[No decisions found]", 0
    lines = [f"  > {d}" for d in decisions]
    if work:
        lines += ["[RECENT WORK]"] + [f"  - {w}" for w in work]
    formatted = "\n".join(lines)
    return formatted, len(formatted)


# ── BM25 retrieval ────────────────────────────────────────────────────────────

def get_bm25_context(query: str, commit_corpus: List[Dict], top_k: int = 7) -> Tuple[str, int]:
    """BM25 retrieval over full commit corpus (query-aware)."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        return "[rank_bm25 not installed]", 0

    if not commit_corpus:
        return "[Empty corpus]", 0

    def tokenize(text: str) -> List[str]:
        return re.findall(r'\b\w+\b', text.lower())

    subjects = [c.get('subject', '') for c in commit_corpus]
    tokenized = [tokenize(s) for s in subjects]
    bm25 = BM25Okapi(tokenized)

    # Clean query: remove question prefixes to focus on topic keywords
    clean = re.sub(r'^(when did we|why did we|what is|how did|when was)\s+', '', query.lower())
    query_tokens = tokenize(clean)
    scores = bm25.get_scores(query_tokens)

    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    lines = []
    for idx in top_indices:
        commit = commit_corpus[idx]
        if scores[idx] > 0:
            date = commit.get('date', '')[:10]
            h = commit.get('hash', '')[:7]
            lines.append(f"  {h} {date} {commit.get('subject', '')} [bm25={scores[idx]:.2f}]")

    if not lines:
        return "[No relevant commits found by BM25]", 0
    formatted = "\n".join(lines)
    return formatted, len(formatted)


# ── Dense embedding retrieval ─────────────────────────────────────────────────

def get_dense_context(query: str, commit_corpus: List[Dict], top_k: int = 7) -> Tuple[str, int]:
    """
    Dense semantic retrieval using sentence-transformers.
    G1 uses NL commit messages (not code) — dense may help unlike Code→Code.
    """
    try:
        from sentence_transformers import SentenceTransformer
        import numpy as np
    except ImportError:
        return "[sentence-transformers not installed]", 0

    if not commit_corpus:
        return "[Empty corpus]", 0

    model = SentenceTransformer('all-MiniLM-L6-v2')
    subjects = [c.get('subject', '') for c in commit_corpus]
    corpus_emb = model.encode(subjects, convert_to_numpy=True)

    clean = re.sub(r'^(when did we|why did we|what is|how did|when was)\s+', '', query.lower())
    q_emb = model.encode([clean], convert_to_numpy=True)[0]

    norms = corpus_emb / (corpus_emb ** 2).sum(axis=1, keepdims=True) ** 0.5
    q_norm = q_emb / ((q_emb ** 2).sum() ** 0.5 + 1e-8)
    sims = norms @ q_norm

    top_indices = sims.argsort()[::-1][:top_k]
    lines = []
    for idx in top_indices:
        commit = commit_corpus[idx]
        date = commit.get('date', '')[:10]
        h = commit.get('hash', '')[:7]
        lines.append(f"  {h} {date} {commit.get('subject', '')} [sim={sims[idx]:.3f}]")

    formatted = "\n".join(lines)
    return formatted, len(formatted)


# ── Corpus loader ─────────────────────────────────────────────────────────────

def load_commit_corpus(repo_path: Path) -> List[Dict]:
    """Load decision commit corpus from pre-generated JSON."""
    corpus_path = repo_path / "benchmarks/results/g1_decision_commits.json"
    if not corpus_path.exists():
        return []
    try:
        with open(corpus_path) as f:
            commits = json.load(f)
        return [
            {"hash": c.get("hash", ""), "date": c.get("date", ""), "subject": c.get("subject", ""), "body": c.get("body", "")}
            for c in commits
        ]
    except Exception:
        return []


# ── BaselineEvaluator ─────────────────────────────────────────────────────────

class BaselineEvaluator:
    """7-baseline evaluator for G1 long-term memory."""

    def __init__(self, repo_path: Path, llm_client=None):
        self.repo_path = repo_path
        self.llm_client = llm_client or get_llm_client()
        self._commit_corpus: Optional[List[Dict]] = None

    @property
    def commit_corpus(self) -> List[Dict]:
        if self._commit_corpus is None:
            self._commit_corpus = load_commit_corpus(self.repo_path)
        return self._commit_corpus

    def _base_result(self, baseline: str, qa_pair: Dict, response: str, ctx_len: int) -> Dict:
        return {
            "baseline": baseline,
            "query": qa_pair['query'],
            "query_type": qa_pair.get('query_type', 'unknown'),
            "age_bucket": qa_pair.get('age_bucket', 'unknown'),
            "response": response,
            "ground_truth": qa_pair['ground_truth'],
            "context_length": ctx_len,
        }

    def evaluate_no_ctx(self, qa_pair: Dict) -> Dict:
        resp = call_llm(
            self.llm_client,
            "You are a helpful AI assistant. Answer based on your knowledge of the CTX project.",
            qa_pair['query']
        )
        return self._base_result("no_ctx", qa_pair, resp, 0)

    def evaluate_full_dump(self, qa_pair: Dict) -> Dict:
        ctx = get_git_log_full(self.repo_path, n=100)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the provided git log to answer questions.",
            f"Git log (last 100 commits):\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the git log above."
        )
        return self._base_result("full_dump", qa_pair, resp, len(ctx))

    def evaluate_g1_raw(self, qa_pair: Dict) -> Dict:
        ctx = get_git_memory_output(self.repo_path, n=20, filtered=False)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the provided decision history to answer questions.",
            f"Recent decisions (git-memory, n=20):\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the decision history above."
        )
        return self._base_result("g1_raw", qa_pair, resp, len(ctx))

    def evaluate_g1_filtered(self, qa_pair: Dict) -> Dict:
        ctx = get_git_memory_output(self.repo_path, n=30, filtered=True)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the provided decision history to answer questions.",
            f"Recent decisions (git-memory filtered, n=30):\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the decision history above."
        )
        return self._base_result("g1_filtered", qa_pair, resp, len(ctx))

    def evaluate_git_memory_real(self, qa_pair: Dict) -> Dict:
        """Actual git-memory.py logic: query-agnostic, top-7 recent decisions."""
        ctx, ctx_len = get_git_memory_real_context(self.repo_path)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the provided recent decision history to answer questions.",
            f"Recent decisions (git-memory real, top-7):\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the decision history above."
        )
        return self._base_result("git_memory_real", qa_pair, resp, ctx_len)

    def evaluate_bm25_retrieval(self, qa_pair: Dict) -> Dict:
        """BM25 query-aware retrieval over full commit corpus."""
        ctx, ctx_len = get_bm25_context(qa_pair['query'], self.commit_corpus, top_k=7)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the BM25-retrieved commits to answer questions.",
            f"BM25-retrieved relevant commits:\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the retrieved commits above."
        )
        return self._base_result("bm25_retrieval", qa_pair, resp, ctx_len)

    def evaluate_dense_embedding(self, qa_pair: Dict) -> Dict:
        """Dense semantic retrieval — sentence-transformers on NL commit messages."""
        ctx, ctx_len = get_dense_context(qa_pair['query'], self.commit_corpus, top_k=7)
        resp = call_llm(
            self.llm_client,
            "You are analyzing a git repository. Use the semantically retrieved commits to answer questions.",
            f"Semantically retrieved commits (dense embedding):\n{ctx}\n\nQuestion: {qa_pair['query']}\n\nAnswer based on the retrieved commits above."
        )
        return self._base_result("dense_embedding", qa_pair, resp, ctx_len)

    def evaluate_all(self, qa_pair: Dict, baselines: Optional[List[str]] = None) -> Dict[str, Dict]:
        """Run specified (or all) baselines for one QA pair."""
        dispatch = {
            "no_ctx": self.evaluate_no_ctx,
            "full_dump": self.evaluate_full_dump,
            "g1_raw": self.evaluate_g1_raw,
            "g1_filtered": self.evaluate_g1_filtered,
            "git_memory_real": self.evaluate_git_memory_real,
            "bm25_retrieval": self.evaluate_bm25_retrieval,
            "dense_embedding": self.evaluate_dense_embedding,
        }
        if baselines is None:
            baselines = list(dispatch.keys())
        return {name: dispatch[name](qa_pair) for name in baselines if name in dispatch}


# ── Quick smoke test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    repo_path = Path("/home/jayone/Project/CTX")

    print("[1] git_memory_real context:")
    ctx, length = get_git_memory_real_context(repo_path)
    print(f"  {length} chars:\n{ctx}\n")

    print("[2] Loading commit corpus...")
    corpus = load_commit_corpus(repo_path)
    print(f"  {len(corpus)} commits loaded")

    query = "When did we implement G1 temporal retention?"
    print(f"\n[3] BM25 retrieval for: '{query}'")
    bm25_ctx, bm25_len = get_bm25_context(query, corpus, top_k=5)
    print(f"  {bm25_len} chars:\n{bm25_ctx}\n")

    print("[4] Dense embedding retrieval:")
    dense_ctx, dense_len = get_dense_context(query, corpus, top_k=5)
    print(f"  {dense_len} chars:\n{dense_ctx}")
