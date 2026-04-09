#!/usr/bin/env python3
"""
G1 External Repo CHANGELOG-based Open-Set Benchmark
====================================================
Ground truth: CHANGELOG.md entries (curated by repo maintainers)
Corpus: full git history (open-set — answer not guaranteed in top-N)
Repos: Flask, Django, Requests

Contrast with closed-set eval (g1_longterm_eval.py):
  closed-set: corpus = 59 decision commits, answer guaranteed in corpus → BM25 0.881
  open-set:   corpus = full git log (1000s of commits), answer may be hard to find
"""

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import anthropic
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, util


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

REPOS = [
    {
        "name": "Flask",
        "url": "https://github.com/pallets/flask.git",
        "changelog": "CHANGES.rst",
        "clone_dir": "/tmp/g1_eval_flask",
    },
    {
        "name": "Requests",
        "url": "https://github.com/psf/requests.git",
        "changelog": "HISTORY.md",
        "clone_dir": "/tmp/g1_eval_requests",
    },
    {
        "name": "Django",
        "url": "https://github.com/django/django.git",
        "changelog": "docs/releases/index.txt",  # use release notes dir
        "clone_dir": "/tmp/g1_eval_django",
    },
]

MAX_QA_PER_REPO = 20     # QA pairs to generate per repo
TOP_K = 7                # retrieval top-K (same as closed-set)
MAX_COMMITS = 2000       # max commits to index per repo (open-set)
RESULTS_DIR = Path("benchmarks/results")


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ChangelogEntry:
    version: str
    date: str          # "YYYY-MM-DD" or approximate
    feature: str       # what was added/changed
    raw_text: str      # original changelog text


@dataclass
class QAPair:
    repo: str
    query: str                    # "When was X added to Flask?"
    ground_truth_version: str     # "0.11"
    ground_truth_date: str        # "2016-05-29"
    ground_truth_feature: str     # original feature description
    answer_keywords: List[str]    # keywords that must appear in correct answer


@dataclass
class RetrievalResult:
    baseline: str
    query: str
    retrieved_commits: List[str]   # top-K commit messages
    response: str                  # LLM answer
    score: float                   # 0 or 1 (recall@K)
    context_length: int
    latency_ms: float


# ──────────────────────────────────────────────────────────────────────────────
# LLM client
# ──────────────────────────────────────────────────────────────────────────────

def get_llm_client() -> Optional[anthropic.Anthropic]:
    minimax_key = os.environ.get("MINIMAX_API_KEY", "")
    minimax_url = os.environ.get("MINIMAX_BASE_URL", "")
    if minimax_key and minimax_url:
        return anthropic.Anthropic(api_key=minimax_key, base_url=minimax_url)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return anthropic.Anthropic(api_key=key)
    return None


def call_llm(client, system: str, user: str, max_tokens: int = 512) -> str:
    if client is None:
        return "[NO-CLIENT]"
    model = os.environ.get("MINIMAX_MODEL", "claude-haiku-4-5-20251001")
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": user}],
            system=system,
        )
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return "[EMPTY]"
    except Exception as e:
        return f"[LLM-ERROR: {e}]"


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1: Clone repos + extract git log
# ──────────────────────────────────────────────────────────────────────────────

def clone_or_update(repo_cfg: dict) -> bool:
    """Clone repo if not present, else fetch latest."""
    clone_dir = repo_cfg["clone_dir"]
    if Path(clone_dir).exists():
        print(f"  [{repo_cfg['name']}] Already cloned at {clone_dir}")
        return True
    print(f"  [{repo_cfg['name']}] Cloning {repo_cfg['url']} → {clone_dir}")
    result = subprocess.run(
        ["git", "clone", "--depth=2000", repo_cfg["url"], clone_dir],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  [{repo_cfg['name']}] Clone failed: {result.stderr[:200]}")
        return False
    print(f"  [{repo_cfg['name']}] Cloned OK")
    return True


def get_commit_corpus(clone_dir: str, max_commits: int = MAX_COMMITS) -> List[Dict]:
    """Extract up to max_commits from full git history (open-set corpus)."""
    result = subprocess.run(
        ["git", "log", f"--max-count={max_commits}",
         "--format=%H\t%ai\t%s", "--no-merges"],
        capture_output=True, text=True, cwd=clone_dir
    )
    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t", 2)
        if len(parts) == 3:
            commits.append({
                "hash": parts[0][:7],
                "date": parts[1][:10],
                "message": parts[2].strip(),
            })
    return commits


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2: Parse CHANGELOG → ground truth entries
# ──────────────────────────────────────────────────────────────────────────────

def parse_changelog_rst(text: str) -> List[ChangelogEntry]:
    """Parse Flask CHANGES.rst format:
    Version X.Y.Z
    -------------
    Released YYYY-MM-DD  (optional)

    -   bullet
    """
    entries = []
    # Split on version headers: "Version X.Y.Z\n---..."
    sections = re.split(r'\nVersion (\d+\.\d+[\.\d]*)\n[-=~]+\n', text)
    # sections[0] = preamble, then alternating: version, body
    i = 1
    while i < len(sections) - 1:
        version = sections[i].strip()
        body = sections[i + 1] if i + 1 < len(sections) else ""

        # Extract date from first line of body
        date_raw = ""
        date_match = re.match(r'Released\s+(\d{4}-\d{2}-\d{2}|\w+ \d+,? \d{4})', body.strip())
        if date_match:
            date_raw = date_match.group(1)

        # Extract bullet points (-   text)
        bullets = re.findall(r'^-\s{1,3}(.+?)(?=\n-\s|\n\n\w|\Z)', body, re.MULTILINE | re.DOTALL)
        for bullet in bullets[:5]:
            clean = bullet.strip().replace('\n', ' ')
            # Remove RST refs like :pr:`123`, :issue:`456`
            clean = re.sub(r'\s*:\w+:`[^`]+`', '', clean).strip()
            if len(clean) > 15:
                entries.append(ChangelogEntry(
                    version=version,
                    date=normalize_date(date_raw),
                    feature=clean[:200],
                    raw_text=f"Version {version} ({date_raw}): {clean[:150]}"
                ))
        i += 2
    return entries


def parse_changelog_md(text: str) -> List[ChangelogEntry]:
    """Parse Markdown HISTORY (## X.Y.Z (YYYY-MM-DD) style)."""
    entries = []
    # Pattern: ## version (YYYY-MM-DD)
    version_pattern = re.compile(
        r'^##\s+(\d+\.\d+[\.\d]*)\s*\((\d{4}-\d{2}-\d{2}|[A-Za-z]+ \d+,? \d{4})\)',
        re.MULTILINE
    )
    matches = list(version_pattern.finditer(text))

    for idx, match in enumerate(matches):
        version = match.group(1)
        date_raw = match.group(2)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        bullets = re.findall(r'^[-*+]\s+(.+)$', body, re.MULTILINE)
        for bullet in bullets[:5]:
            entries.append(ChangelogEntry(
                version=version,
                date=normalize_date(date_raw),
                feature=bullet.strip()[:200],
                raw_text=f"{version} ({date_raw}): {bullet.strip()[:150]}"
            ))
    return entries


def parse_changelog_requests(text: str) -> List[ChangelogEntry]:
    """Parse Requests HISTORY.md — RST underline style: X.Y.Z (YYYY-MM-DD)\\n---"""
    entries = []
    # Match: "X.Y.Z (YYYY-MM-DD)\n-+"
    version_pattern = re.compile(
        r'^(\d+\.\d+[\.\d]*)\s+\((\d{4}-\d{2}-\d{2})\)\n[-]+',
        re.MULTILINE
    )
    matches = list(version_pattern.finditer(text))

    for idx, match in enumerate(matches):
        version = match.group(1)
        date_raw = match.group(2)
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        bullets = re.findall(r'^[-*+]\s+(.+)$', body, re.MULTILINE)
        for bullet in bullets[:5]:
            entries.append(ChangelogEntry(
                version=version,
                date=normalize_date(date_raw),
                feature=bullet.strip()[:200],
                raw_text=f"{version} ({date_raw}): {bullet.strip()[:150]}"
            ))
    return entries


def normalize_date(raw: str) -> str:
    """Convert various date formats to YYYY-MM-DD."""
    if not raw:
        return ""
    # Already ISO format
    if re.match(r'\d{4}-\d{2}-\d{2}', raw):
        return raw[:10]
    # Month DD, YYYY
    months = {"january":"01","february":"02","march":"03","april":"04",
              "may":"05","june":"06","july":"07","august":"08",
              "september":"09","october":"10","november":"11","december":"12",
              "jan":"01","feb":"02","mar":"03","apr":"04","jun":"06",
              "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12"}
    m = re.match(r'(\w+)\s+(\d+),?\s+(\d{4})', raw, re.IGNORECASE)
    if m:
        month = months.get(m.group(1).lower(), "00")
        day = m.group(2).zfill(2)
        year = m.group(3)
        return f"{year}-{month}-{day}"
    return raw[:10]


def parse_changelog(repo_cfg: dict) -> List[ChangelogEntry]:
    """Parse changelog based on repo format."""
    changelog_path = Path(repo_cfg["clone_dir"]) / repo_cfg["changelog"]
    if not changelog_path.exists():
        print(f"  [{repo_cfg['name']}] Changelog not found at {changelog_path}")
        return []

    text = changelog_path.read_text(encoding="utf-8", errors="replace")
    name = repo_cfg["name"]

    if name == "Flask":
        entries = parse_changelog_rst(text)
    elif name == "Requests":
        entries = parse_changelog_requests(text)
    elif name == "Django":
        # Django: parse release notes index to find version dates
        entries = parse_django_releases(repo_cfg["clone_dir"])
    else:
        entries = parse_changelog_md(text)

    print(f"  [{name}] Parsed {len(entries)} changelog entries")
    return entries


def parse_django_releases(clone_dir: str) -> List[ChangelogEntry]:
    """Parse Django release notes (docs/releases/*.txt)."""
    entries = []
    releases_dir = Path(clone_dir) / "docs" / "releases"
    if not releases_dir.exists():
        return []

    # Only version files like "6.0.txt", "5.2.1.txt" — skip index.txt, security.txt
    release_files = sorted(releases_dir.glob("*.txt"), reverse=True)
    release_files = [f for f in release_files if re.match(r'^\d+\.\d+', f.stem)][:25]

    for rf in release_files:
        text = rf.read_text(encoding="utf-8", errors="replace")
        version = rf.stem  # e.g., "6.0", "5.2.1"

        # Skip dev/unreleased entries
        if "UNDER DEVELOPMENT" in text[:300] or (
            "Expected" in text[:200] and re.search(r'\*Expected', text[:200])
        ):
            continue

        # Find release date: "*Month DD, YYYY*"
        date_match = re.search(r'\*(\w+ \d+,?\s*\d{4})\*', text[:400])
        if not date_match:
            continue
        date_raw = date_match.group(1)

        # Extract feature names from "What's new" subsections (headers underlined with -)
        whats_new_match = re.search(
            r"What's new in Django.*?\n[=]+\n(.*?)(?:\n\w[^\n]+\n[=]+|\Z)",
            text, re.DOTALL
        )
        if whats_new_match:
            section = whats_new_match.group(1)
        else:
            bc_pos = text.find("Backwards incompatible")
            section = text[:bc_pos] if bc_pos > 0 else text[:5000]

        features = re.findall(r'^([A-Z][^\n]{10,80})\n[-~]+', section, re.MULTILINE)
        for feature in features[:5]:
            clean = feature.strip()
            if len(clean) > 10 and not clean.lower().startswith("django"):
                entries.append(ChangelogEntry(
                    version=version,
                    date=normalize_date(date_raw),
                    feature=clean,
                    raw_text=f"Django {version} ({date_raw}): {clean[:150]}"
                ))
    return entries


# ──────────────────────────────────────────────────────────────────────────────
# Phase 3: Generate QA pairs from changelog entries
# ──────────────────────────────────────────────────────────────────────────────

def generate_qa_pairs(
    repo_name: str,
    entries: List[ChangelogEntry],
    client,
    max_pairs: int = MAX_QA_PER_REPO
) -> List[QAPair]:
    """Generate QA pairs from changelog entries using LLM."""
    # Filter to entries with dates and meaningful features
    valid = [e for e in entries if e.date and len(e.feature) > 15][:max_pairs * 3]

    qa_pairs = []
    for entry in valid[:max_pairs * 2]:  # try 2x entries to compensate for filtering
        if len(qa_pairs) >= max_pairs:
            break
        # Generate a natural language question
        system = "You are generating evaluation questions for a retrieval benchmark."
        user = f"""Given this changelog entry from {repo_name}:
"{entry.raw_text}"

Generate ONE natural question that:
1. Asks when this feature was added (Type 1: timestamp query)
2. Mentions the feature by name/description
3. Is phrased as a developer would ask

Output EXACTLY:
question: <the question>
keywords: <3-5 key terms from the feature that must appear in the answer>

Example:
question: When was async support added to Flask?
keywords: async, support, 2023"""

        response = call_llm(client, system, user, max_tokens=150)

        # Parse response
        q_match = re.search(r'question:\s*(.+)', response)
        k_match = re.search(r'keywords:\s*(.+)', response)

        if q_match and not "[LLM-ERROR" in response and not "[NO-CLIENT" in response:
            question = re.sub(r'^[-*"\'`\s]+', '', q_match.group(1).strip()).strip('"\'`')
            # Strip nested "question:" prefix (LLM sometimes doubles it)
            question = re.sub(r'^question:\s*', '', question, flags=re.IGNORECASE)
            # Strip template placeholders like <the question>
            question = re.sub(r'^<[^>]{1,30}>', '', question).strip()
            question = question.strip('"\'`')

            # Quality filter: must be a real question
            valid_start = any(question.lower().startswith(w)
                              for w in ['when', 'what', 'which', 'how', 'why', 'who', 'where'])
            if len(question) < 20 or not valid_start:
                continue
            if '<' in question or question.lower().startswith('should'):
                continue

            keywords = [k.strip() for k in (k_match.group(1) if k_match else "").split(",")]

            qa_pairs.append(QAPair(
                repo=repo_name,
                query=question,
                ground_truth_version=entry.version,
                ground_truth_date=entry.date,
                ground_truth_feature=entry.feature,
                answer_keywords=keywords[:5]
            ))

    print(f"  [{repo_name}] Generated {len(qa_pairs)} QA pairs")
    return qa_pairs


# ──────────────────────────────────────────────────────────────────────────────
# Phase 4: Retrieval baselines (open-set)
# ──────────────────────────────────────────────────────────────────────────────

def build_bm25_index(commits: List[Dict]):
    """Build BM25 index over full commit corpus."""
    def tokenize(text: str) -> List[str]:
        text = re.sub(r'^(feat|fix|refactor|docs|test|chore|style|perf|build|ci)(\(.+?\))?:?\s*', '', text, flags=re.IGNORECASE)
        return re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', text.lower())

    corpus = [tokenize(c["message"]) for c in commits]
    return BM25Okapi(corpus), corpus


_dense_model = None
def get_dense_model():
    global _dense_model
    if _dense_model is None:
        _dense_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _dense_model


def bm25_retrieve(query: str, commits: List[Dict], bm25_index, top_k: int = TOP_K) -> List[Dict]:
    """BM25 retrieval over full commit history."""
    # Strip question words
    clean = re.sub(r'^(when|what|why|how|which|who|where)\s+(was|were|did|is|are|has|have)\s+', '', query.lower()).strip()
    clean = re.sub(r'\?$', '', clean).strip()
    tokens = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_-]{2,}\b', clean)

    scores = bm25_index.get_scores(tokens)
    top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [commits[i] for i in top_indices]


def dense_retrieve(query: str, commits: List[Dict], top_k: int = TOP_K) -> List[Dict]:
    """Dense embedding retrieval over full commit history."""
    model = get_dense_model()
    messages = [c["message"] for c in commits]

    query_emb = model.encode(query, convert_to_tensor=True)
    corpus_emb = model.encode(messages, convert_to_tensor=True, batch_size=256, show_progress_bar=False)

    scores = util.cos_sim(query_emb, corpus_emb)[0]
    top_indices = scores.topk(top_k).indices.tolist()
    return [commits[i] for i in top_indices]


def git_memory_real_retrieve(commits: List[Dict], top_k: int = TOP_K) -> List[Dict]:
    """Simulate git_memory_real: proactive, query-agnostic, most recent N commits."""
    # Replicate git-memory.py behavior: take most recent commits, no query
    decision_keywords = {
        "implement", "add", "introduce", "replace", "rewrite", "redesign",
        "remove", "deprecate", "drop", "change", "update", "refactor",
        "fix", "resolve", "patch", "bump"
    }

    def is_decision(msg: str) -> bool:
        msg_lower = msg.lower()
        if re.match(r'^(feat|fix|refactor|docs|test|chore)(\(.+?\))?:', msg_lower):
            return True
        if re.match(r'^v?\d+\.\d+', msg_lower):
            return True
        return any(kw in msg_lower for kw in decision_keywords)

    decisions = [c for c in commits[:100] if is_decision(c["message"])][:top_k]
    return decisions


def no_ctx_retrieve() -> List[Dict]:
    return []


def full_dump_retrieve(commits: List[Dict], top_k: int = 100) -> List[Dict]:
    """full_dump: most recent 100 commits, no filtering."""
    return commits[:top_k]


# ──────────────────────────────────────────────────────────────────────────────
# Phase 5: Scoring
# ──────────────────────────────────────────────────────────────────────────────

def format_context(retrieved: List[Dict]) -> str:
    if not retrieved:
        return ""
    lines = []
    for c in retrieved:
        lines.append(f"[{c['date']}] {c['hash']}: {c['message']}")
    return "\n".join(lines)


def score_response(response: str, qa: QAPair) -> float:
    """Score 0/1: does response mention correct date or version?"""
    resp_lower = response.lower()

    # Check for exact date match
    if qa.ground_truth_date and qa.ground_truth_date in response:
        return 1.0

    # Check for version
    if qa.ground_truth_version and qa.ground_truth_version in response:
        return 1.0

    # Check for date parts
    if qa.ground_truth_date:
        parts = qa.ground_truth_date.split("-")
        if len(parts) == 3:
            year, month, day = parts
            month_names = {
                "01": "january", "02": "february", "03": "march", "04": "april",
                "05": "may", "06": "june", "07": "july", "08": "august",
                "09": "september", "10": "october", "11": "november", "12": "december"
            }
            month_name = month_names.get(month, "")
            day_int = str(int(day))  # remove zero-padding

            if year in response and month_name in resp_lower:
                return 1.0
            if year in response and day_int in response:
                return 1.0

    return 0.0


def evaluate_qa(
    qa: QAPair,
    commits: List[Dict],
    bm25_index,
    client,
    repo_name: str,
) -> Dict[str, RetrievalResult]:
    """Evaluate all baselines for one QA pair."""
    system = f"""You are a {repo_name} expert. Answer the user's question about when a feature was implemented.
Be specific about the date or version. Use the provided git history context if available.
Keep your answer to 2-3 sentences."""

    results = {}

    baselines = {
        "no_ctx": no_ctx_retrieve(),
        "full_dump": full_dump_retrieve(commits),
        "git_memory_real": git_memory_real_retrieve(commits),
        "bm25_retrieval": bm25_retrieve(qa.query, commits, bm25_index),
        "dense_embedding": dense_retrieve(qa.query, commits),
    }

    for baseline_name, retrieved in baselines.items():
        context = format_context(retrieved)

        if context:
            user_msg = f"Git history context:\n{context}\n\nQuestion: {qa.query}"
        else:
            user_msg = f"Question: {qa.query}"

        t0 = time.time()
        response = call_llm(client, system, user_msg, max_tokens=256)
        latency_ms = (time.time() - t0) * 1000

        score = score_response(response, qa) if "[NO-CLIENT]" not in response else 0.0

        results[baseline_name] = RetrievalResult(
            baseline=baseline_name,
            query=qa.query,
            retrieved_commits=[c["message"] for c in retrieved[:5]],
            response=response,
            score=score,
            context_length=len(context),
            latency_ms=latency_ms,
        )

    return results


# ──────────────────────────────────────────────────────────────────────────────
# Phase 6: Report
# ──────────────────────────────────────────────────────────────────────────────

def generate_report(all_results: Dict, output_path: Path):
    """Generate markdown report comparing open-set vs closed-set."""

    CLOSED_SET = {
        "no_ctx": 0.000,
        "full_dump": 0.712,
        "git_memory_real": 0.169,
        "bm25_retrieval": 0.881,
        "dense_embedding": 0.644,
    }

    baselines = ["no_ctx", "full_dump", "git_memory_real", "bm25_retrieval", "dense_embedding"]

    lines = [
        "# G1 External Repo Open-Set Benchmark",
        "",
        f"**Date**: {time.strftime('%Y-%m-%d')}",
        "**Method**: CHANGELOG-based ground truth, open-set retrieval (full git history)",
        "",
        "## Results",
        "",
        "### Per-Repo Recall@7",
        "",
        f"| Baseline | Flask | Requests | Django | Mean | Closed-Set | Delta |",
        f"|----------|-------|----------|--------|------|------------|-------|",
    ]

    for bl in baselines:
        repo_scores = {}
        for repo_name, repo_results in all_results.items():
            bl_results = [r for r in repo_results if r.baseline == bl]
            if bl_results:
                repo_scores[repo_name] = sum(r.score for r in bl_results) / len(bl_results)
            else:
                repo_scores[repo_name] = 0.0

        mean = sum(repo_scores.values()) / len(repo_scores) if repo_scores else 0.0
        closed = CLOSED_SET.get(bl, 0.0)
        delta = mean - closed
        delta_str = f"{delta:+.3f}"

        flask_s = f"{repo_scores.get('Flask', 0):.3f}"
        req_s = f"{repo_scores.get('Requests', 0):.3f}"
        dj_s = f"{repo_scores.get('Django', 0):.3f}"

        lines.append(f"| {bl} | {flask_s} | {req_s} | {dj_s} | **{mean:.3f}** | {closed:.3f} | {delta_str} |")

    lines += [
        "",
        "## Key Findings",
        "",
        "### Open-Set vs Closed-Set Gap",
        "",
        "| Metric | Closed-Set (59 CTX commits) | Open-Set (full git history) |",
        "|--------|----------------------------|----------------------------|",
    ]

    # Overall means
    for bl in ["bm25_retrieval", "dense_embedding", "git_memory_real"]:
        all_scores = []
        for repo_results in all_results.values():
            all_scores.extend([r.score for r in repo_results if r.baseline == bl])
        open_mean = sum(all_scores) / len(all_scores) if all_scores else 0.0
        closed = CLOSED_SET.get(bl, 0.0)
        lines.append(f"| {bl} | {closed:.3f} | {open_mean:.3f} |")

    lines += [
        "",
        "## Methodology",
        "",
        "- **Ground truth**: CHANGELOG.md / HISTORY.md entries (curator-labeled decisions)",
        f"- **Corpus size**: up to {MAX_COMMITS} commits per repo (open-set)",
        f"- **QA pairs**: up to {MAX_QA_PER_REPO} per repo (Type 1: timestamp queries)",
        "- **Scoring**: Recall@7 — correct date/version in LLM response",
        "- **LLM**: MiniMax M2.5 (same as closed-set eval)",
    ]

    report = "\n".join(lines)
    output_path.write_text(report, encoding="utf-8")
    print(f"Report saved: {output_path}")
    return report


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("G1 External Repo Open-Set Benchmark")
    print("=" * 60)

    client = get_llm_client()
    if client is None:
        print("ERROR: No LLM client. Set MINIMAX_API_KEY or ANTHROPIC_API_KEY.")
        return

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_results: Dict[str, List[RetrievalResult]] = {}
    all_qa_pairs: Dict[str, List[QAPair]] = {}

    for repo_cfg in REPOS:
        repo_name = repo_cfg["name"]
        print(f"\n[{repo_name}]")

        # Phase 1: Clone
        if not clone_or_update(repo_cfg):
            continue

        # Phase 2: Get commit corpus
        print(f"  Indexing commits...")
        commits = get_commit_corpus(repo_cfg["clone_dir"])
        print(f"  Found {len(commits)} commits (open-set corpus)")

        # Phase 3: Parse changelog
        entries = parse_changelog(repo_cfg)
        if not entries:
            print(f"  No changelog entries — skipping")
            continue

        # Phase 4: Generate QA pairs
        print(f"  Generating QA pairs...")
        qa_pairs = generate_qa_pairs(repo_name, entries, client)
        all_qa_pairs[repo_name] = qa_pairs

        # Phase 5: Build index
        print(f"  Building BM25 index...")
        bm25_index, _ = build_bm25_index(commits)

        # Phase 6: Evaluate
        print(f"  Evaluating {len(qa_pairs)} QA pairs × 5 baselines...")
        repo_results: List[RetrievalResult] = []

        for i, qa in enumerate(qa_pairs, 1):
            print(f"    [{i}/{len(qa_pairs)}] {qa.query[:60]}...")
            results = evaluate_qa(qa, commits, bm25_index, client, repo_name)
            for bl_result in results.values():
                repo_results.append(bl_result)

        all_results[repo_name] = repo_results

        # Intermediate save
        intermediate = RESULTS_DIR / f"g1_openset_{repo_name.lower()}.json"
        with open(intermediate, "w") as f:
            json.dump([{
                "baseline": r.baseline,
                "query": r.query,
                "score": r.score,
                "context_length": r.context_length,
                "response": r.response[:200],
            } for r in repo_results], f, indent=2)
        print(f"  Saved intermediate: {intermediate}")

    # Save full results
    full_results_path = RESULTS_DIR / "g1_openset_results.json"
    with open(full_results_path, "w") as f:
        json.dump({
            repo: [{
                "baseline": r.baseline,
                "query": r.query,
                "score": r.score,
                "context_length": r.context_length,
                "latency_ms": r.latency_ms,
                "response": r.response[:300],
            } for r in results]
            for repo, results in all_results.items()
        }, f, indent=2)

    # Save QA pairs
    qa_path = RESULTS_DIR / "g1_openset_qa_pairs.json"
    with open(qa_path, "w") as f:
        json.dump({
            repo: [{
                "query": qa.query,
                "ground_truth_version": qa.ground_truth_version,
                "ground_truth_date": qa.ground_truth_date,
                "ground_truth_feature": qa.ground_truth_feature,
                "answer_keywords": qa.answer_keywords,
            } for qa in pairs]
            for repo, pairs in all_qa_pairs.items()
        }, f, indent=2, ensure_ascii=False)

    # Generate report
    report_path = RESULTS_DIR / "g1_openset_report.md"
    report = generate_report(all_results, report_path)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(report[:1000])


if __name__ == "__main__":
    main()
