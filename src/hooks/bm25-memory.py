#!/usr/bin/env python3
"""
bm25-memory: BM25-based reactive memory for Claude Code.
Replaces git-memory.py (G1 proactive, recall 0.169) + g2-augment.py (G2 graph).

G1: ALL git decision commits → BM25 query-time ranking → top-7 relevant to prompt
    Keyword-identical: Structural Recall@7=1.000 (inflated, token overlap=0.476)
    Paraphrase fair eval: Structural Recall@7=0.627 (bias=0.373, 20260410 g1_fair_eval.py)
    Type2/3/4 (why/what/rationale): Structural Recall@7=0.667
    Combined fair Recall@7=0.634 (71 queries) — vs proactive 0.169 → 3.7x improvement
    Fix: CTX YYYYMMDD-prefix commits now recognized as decisions

G2a: docs/research/*.md + CLAUDE.md + MEMORY.md → BM25 → top-5 relevant chunks
     Keyword-identical eval: 10/10 (1.000) | Paraphrase eval: 7/10 (0.700)
     Note: 1.000 is inflated — paraphrase 0.700 is the honest fairness-adjusted score
G2b: codebase graph (codebase-memory-mcp SQLite) → relevant code files (project-internal only)
     Fallback: git grep -c keyword ranking when no DB available
G2b-hooks: ~/.claude/hooks/*.py BM25 search (triggered by "hook/훅/bm25-memory/auto-index/..." keywords)
     Directly indexes hook file function signatures — solves G2b external file gap

Cache: .omc/decision_corpus.json (auto-invalidated on git HEAD change)
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from rank_bm25 import BM25Okapi
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

RICH = "--rich" in sys.argv


# ── Tokenizer ────────────────────────────────────────────────────

_KO_PARTICLES = re.compile(
    r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$'
)

# Conversational stopwords — filtered from QUERIES only (not the corpus).
# These appear in nearly every conversational prompt and make BM25 return
# noise matches on common words instead of real topic terms.
# Kept conservative — only words that are almost never content-bearing in
# a software-engineering commit subject.
_STOPWORDS = frozenset([
    # English function words
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "have", "has", "had", "will", "would",
    "could", "should", "may", "might", "can", "to", "of", "in", "on",
    "at", "by", "for", "with", "from", "as", "into", "about",
    "and", "or", "but", "if", "then", "than", "so", "not", "no",
    "i", "you", "we", "he", "she", "it", "they", "me", "my", "your",
    "our", "his", "her", "their", "this", "that", "these", "those",
    "there", "here", "what", "which", "when", "where", "why", "how",
    "who", "whom", "some", "any", "all", "each", "every", "both",
    "more", "most", "less", "few", "much", "many",
    "just", "only", "very", "too", "also", "even", "still", "yet",
    "now", "then", "up", "down", "out", "over", "again",
    # Conversational fillers
    "ok", "yeah", "yep", "pls", "please", "thanks", "thank",
    "hi", "hey", "hello", "want", "like", "think", "need",
    "make", "use", "using", "try", "trying", "get", "got",
    # Korean fillers (particles already stripped; these are standalone)
    "음", "어", "아", "그", "저", "이거", "저거", "그거",
])


def tokenize(text: str, drop_stopwords: bool = False):
    """Preserve decimal numbers (0.724) and numeric ranges (7-30) as single tokens.
    Also strips Korean particles from mixed Korean-ASCII tokens (e.g. 'BM25와' → 'bm25' + 'bm25와')
    so that Korean queries match English commit subjects correctly.

    When `drop_stopwords=True` (query-side only), conversational fillers are
    removed to prevent BM25 from matching on common words like "i", "to", "how",
    "would", etc. Corpus tokenization never drops stopwords — IDF handles those.
    """
    raw = re.findall(r'\d+[-\u2013]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        if drop_stopwords and tok in _STOPWORDS:
            continue
        cleaned = _KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            if not (drop_stopwords and cleaned in _STOPWORDS):
                result.append(cleaned)
        result.append(tok)
    return list(dict.fromkeys(result))


# ── G1: Decision Corpus ──────────────────────────────────────────

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
    re.IGNORECASE,
)
_YYYYMMDD_RE = re.compile(r"^\d{8}\s")  # CTX-style: "20260408 G1 temporal..."


def _is_structural_noise(subject):
    s = subject.strip()
    if _OMC_ITER_RE.match(s):
        return True
    if _STRICT_VERSION_RE.match(s):
        return not bool(_EMBEDDED_DECISION_RE.search(s))
    return False


def _is_decision(subject):
    """Detect decision commits: conventional, version-tagged, YYYYMMDD, or keyword."""
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
    if _YYYYMMDD_RE.match(s):  # CTX-style date-prefixed commits
        return True
    return any(kw.lower() in sl for kw in _DECISION_KEYWORDS)


def get_git_head(project_dir):
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_dir, capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def build_decision_corpus(project_dir, n=500):
    """Extract all decision commits from git log (no cap)."""
    try:
        r = subprocess.run(
            ["git", "log", f"-{n}", "--format=%H\x1f%s\x1f%ai"],
            cwd=project_dir, capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return []
    except Exception:
        return []

    corpus = []
    seen = set()
    for line in r.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split("\x1f", 2)
        if len(parts) < 2:
            continue
        commit_hash = parts[0]
        subject = parts[1][:120]
        date = parts[2][:10] if len(parts) == 3 else ""

        if _is_structural_noise(subject):
            continue
        key = subject[:60]
        if key in seen:
            continue
        seen.add(key)

        if _is_decision(subject):
            # 고우선순위 패턴 → text 중복 삽입으로 BM25 가중치 증폭
            is_milestone = any(p in subject for p in [
                "CONVERGED", "pivot", "완성", "완료", "검증", "수렴", "FAILED", "KILL"
            ])
            text = f"{date} {subject}"
            if is_milestone:
                text = f"{text}\n{text}"  # 2배 가중치
            corpus.append({
                "hash": commit_hash,
                "subject": subject,
                "date": date,
                "text": text,
            })

    return corpus


def get_decision_corpus(project_dir):
    """Return cached corpus or rebuild if git HEAD changed."""
    cache_path = Path(project_dir) / ".omc" / "decision_corpus.json"
    head = get_git_head(project_dir)

    if cache_path.exists() and head:
        try:
            cached = json.loads(cache_path.read_text())
            if cached.get("head") == head:
                return cached["corpus"]
        except Exception:
            pass

    corpus = build_decision_corpus(project_dir)
    if head and corpus:
        try:
            cache_path.parent.mkdir(exist_ok=True)
            cache_path.write_text(json.dumps({"head": head, "corpus": corpus}))
        except Exception:
            pass
    return corpus


def bm25_rank_decisions(corpus, query, top_k=7, min_score=0.5):
    """BM25-rank decision corpus against query, return top-k.

    Stopwords are dropped from the query (not the corpus) so conversational
    fillers like "i/to/how/would" don't dominate the ranking.

    `min_score`: if the best-matching decision scores below this, return [].
    Prevents the "no-topic-match → fallback to most-recent-7" anti-pattern
    where zero-score or near-zero queries got ranked purely by git-log order.
    """
    if not corpus:
        return []
    if not HAS_BM25 or not query.strip():
        return []

    query_tokens = tokenize(query, drop_stopwords=True)
    if not query_tokens:
        return []

    tokenized = [tokenize(c["text"]) for c in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query_tokens)
    if len(scores) == 0 or float(max(scores)) < min_score:
        return []
    ranked = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
    return [corpus[i] for i in ranked[:top_k] if scores[i] >= min_score]


# ── G2: Docs BM25 ────────────────────────────────────────────────

def _extra_doc_files(project_dir):
    """Return extra files to include in the docs index (project-agnostic)."""
    # MEMORY.md: ~/.claude/projects/{slug}/memory/MEMORY.md
    # Claude uses leading-dash slug: /home/foo/bar → -home-foo-bar
    slug = project_dir.replace("/", "-")
    memory_md = os.path.expanduser(f"~/.claude/projects/{slug}/memory/MEMORY.md")
    candidates = [
        os.path.join(project_dir, "CLAUDE.md"),
        os.path.join(project_dir, "README.md"),
        memory_md,
    ]
    return [p for p in candidates if os.path.exists(p)]


def chunk_document(filename, content):
    """Split by ## headers; each chunk = 'filename § header\\nbody'."""
    chunks = []
    parts = re.split(r"\n(?=## )", content)
    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.split("\n", 1)
        header = re.sub(r"^#+\s*", "", lines[0].strip())
        body = lines[1].strip() if len(lines) > 1 else ""
        text = f"{filename} § {header}\n{body}"
        if len(text) > 50:
            chunks.append(text[:2500])
    return chunks


def build_docs_bm25(project_dir):
    """Build BM25 index over docs/research/*.md + CLAUDE.md + MEMORY.md.
    Strategy: full-doc (no chunking) — A/B test 2026-04-11 confirms +9.1% recall@5
    vs header-chunked approach (0.758 vs 0.667 on 33 paraphrase pairs).
    Full-doc wins on temporal/open-set/perf queries where answers span multiple sections.
    """
    all_units = []
    docs_dir = Path(project_dir) / "docs" / "research"
    if docs_dir.exists():
        for md_file in sorted(docs_dir.glob("*.md")):
            try:
                text = f"{md_file.name}\n{md_file.read_text()}"
                if len(text) > 50:
                    all_units.append(text)
            except Exception:
                pass

    for fpath in _extra_doc_files(project_dir):
        try:
            p = Path(fpath)
            text = f"{p.name}\n{p.read_text()}"
            if len(text) > 50:
                all_units.append(text)
        except Exception:
            pass

    if not all_units or not HAS_BM25:
        return None, []
    tokenized = [tokenize(u) for u in all_units]
    return BM25Okapi(tokenized), all_units


def bm25_search_docs(project_dir, query, top_k=5):
    """Return top-k docs most relevant to query (full-doc BM25, no chunking).
    Query-side stopword filter prevents conversational fillers from dominating.
    """
    if not query.strip():
        return []
    bm25, units = build_docs_bm25(project_dir)
    if not bm25:
        return []
    query_tokens = tokenize(query, drop_stopwords=True)
    if not query_tokens:
        return []
    scores = bm25.get_scores(query_tokens)
    ranked = sorted(range(len(units)), key=lambda i: scores[i], reverse=True)
    # threshold=1.0: full-doc scores for relevant queries are 3.0-6.0; 0.0 = no overlap
    return [units[i] for i in ranked[:top_k] if scores[i] > 1.0]


# ── G2: Code File Discovery ──────────────────────────────────────

_STOP_WORDS = {
    "the","a","an","is","are","was","were","be","been","have","has","had",
    "do","does","did","will","would","could","should","may","might","can",
    "to","of","in","for","on","with","at","by","from","as","into",
    "it","this","that","i","you","he","she","we","they","me",
    "and","or","but","not","no","if","then","else","when","where","how","what",
    "해줘","해","바람","좀","것","수","있","없","하다","되다","이","그","저","뭐","어떻게",
    "기능","작업","관련","파일","코드","문서","수정","추가","변경","확인","돌려봐",
    "올려","실행","해봐","분석","개선","확인해",
}
_KO_EN = {
    "검색": "search,retrieve,find", "엔진": "engine,retriever",
    "벤치마크": "benchmark,eval", "평가": "eval,evaluate",
    "트리거": "trigger", "분류": "classify,classifier",
    "밀도": "dense,density", "테스트": "test",
    "결과": "result", "스코어": "score",
    "그래프": "graph", "다운스트림": "downstream",
    "외부": "external,reeval", "정확도": "accuracy,precision",
    "이메일": "email,mail", "발송": "send,outreach",
    "대시보드": "dashboard,admin", "구독": "subscription,subscribe",
    "인증": "auth,authenticate", "로그인": "login,signin",
    "사용자": "user,member", "데이터베이스": "database,schema",
    "함수": "function,handler", "컴포넌트": "component",
    "페이지": "page,route", "설정": "config,settings",
    "환경": "env,environment", "서버": "server,backend",
    "실험": "experiment,trial", "배포": "deploy,deployment",
    "오류": "error,exception", "버그": "bug,error",
    "성능": "performance,latency", "최적화": "optimize,cache",
    "알림": "notification,alert", "권한": "permission,auth",
    "훅": "hook", "메모리": "memory", "인덱스": "index",
}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".sh", ".bash", ".yaml", ".yml", ".toml", ".sql", ".css", ".html",
    ".c", ".cpp", ".h", ".rb", ".php", ".swift", ".kt",
}
_SKIP_PREFIXES = (".omc/", "docs/", "benchmarks/results/", "tests/fixtures/")


def extract_keywords(prompt):
    """Extract meaningful keywords from prompt; expand Korean→English."""
    words = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]{2,}|[가-힣]{2,}', prompt)
    keywords = []
    for w in words:
        if w.lower() in _STOP_WORDS or len(w) < 2:
            continue
        if re.match(r'[가-힣]', w) and w in _KO_EN:
            keywords.extend(_KO_EN[w].split(","))
        else:
            keywords.append(w)
    return keywords[:8]


def find_db(project_dir):
    """Locate codebase-memory-mcp SQLite DB for this project."""
    cache_dir = os.path.expanduser("~/.cache/codebase-memory-mcp")
    if not os.path.isdir(cache_dir):
        return None
    slug = project_dir.replace("/", "-").lstrip("-")
    db_path = os.path.join(cache_dir, f"{slug}.db")
    if os.path.exists(db_path):
        return db_path
    for f in os.listdir(cache_dir):
        if f.endswith(".db") and os.path.basename(project_dir).lower() in f.lower():
            return os.path.join(cache_dir, f)
    return None


def search_graph_for_prompt(db_path, keywords, limit=5):
    """Query codebase graph nodes matching keywords."""
    if not keywords:
        return []
    try:
        import sqlite3
        db = sqlite3.connect(db_path)
        results, seen = [], set()
        for kw in keywords:
            rows = db.execute(
                "SELECT DISTINCT label, name, file_path FROM nodes "
                "WHERE name LIKE ? AND label IN ('Function','Method','Class') "
                "ORDER BY length(name) ASC LIMIT ?",
                (f"%{kw}%", 3),
            ).fetchall()
            for r in rows:
                key = (r[1], r[2])
                if key not in seen:
                    seen.add(key)
                    results.append(r)
            if len(results) < limit:
                frows = db.execute(
                    "SELECT DISTINCT label, name, file_path FROM nodes "
                    "WHERE file_path LIKE ? AND label IN ('Module','File') "
                    "ORDER BY length(file_path) ASC LIMIT ?",
                    (f"%{kw}%", 2),
                ).fetchall()
                for r in frows:
                    key = (r[1], r[2])
                    if key not in seen:
                        seen.add(key)
                        results.append(r)
        db.close()
        return results[:limit]
    except Exception:
        return []


def search_files_by_grep(project_dir, keywords, limit=5):
    """Fallback: git grep -c to rank files by keyword match count."""
    long_kws = [k for k in keywords if len(k) >= 4 and not re.match(r'[가-힣]', k)]
    if not long_kws:
        return []
    try:
        pattern = "|".join(re.escape(k) for k in long_kws[:4])
        r = subprocess.run(
            ["git", "grep", "-c", "-E", "-i", "--", pattern],
            cwd=project_dir, capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return []
        scored = []
        for line in r.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                fpath, count = line.rsplit(":", 1)
                scored.append((int(count), fpath.strip()))
            except ValueError:
                continue
        scored.sort(key=lambda x: -x[0])
        files = [f for _, f in scored]
        code = [
            f for f in files
            if any(f.endswith(ext) for ext in _CODE_EXT)
            and not any(f.startswith(p) for p in _SKIP_PREFIXES)
        ]
        return code[:limit]
    except Exception:
        return []


# ── G2: Hooks File Discovery ─────────────────────────────────────

_HOOKS_DIR = Path.home() / ".claude" / "hooks"
_HOOKS_TRIGGER_KWS = frozenset({
    # English
    "hook", "hooks", "bm25-memory", "bm25_memory", "git-memory", "git_memory",
    "auto-index", "auto_index", "g2-augment", "g2_augment",
    "userPromptSubmit", "sessionstart", "posttooluse",
    # Korean
    "훅", "후크",
})


def _build_hook_doc(py_path: Path) -> str:
    """Extract file name + docstring + function/class signatures from a hook file."""
    try:
        src = py_path.read_text(errors="replace")
    except Exception:
        return ""
    lines = src.split("\n")
    header_lines = []
    # Collect: module docstring (first triple-quoted block) + def/class lines
    in_docstring = False
    docstring_done = False
    for line in lines[:80]:
        stripped = line.strip()
        if not docstring_done:
            if stripped.startswith('"""') or stripped.startswith("'''"):
                in_docstring = not in_docstring
                header_lines.append(stripped[:200])
                if stripped.count('"""') >= 2 or stripped.count("'''") >= 2:
                    in_docstring = False
                    docstring_done = True
                continue
            if in_docstring:
                header_lines.append(stripped[:200])
                if '"""' in stripped or "'''" in stripped:
                    in_docstring = False
                    docstring_done = True
                continue
            else:
                docstring_done = True
        if stripped.startswith("def ") or stripped.startswith("class "):
            header_lines.append(stripped[:120])
    return f"{py_path.name}\n" + "\n".join(header_lines)


def search_hooks_files(query: str, limit: int = 3):
    """BM25-search ~/.claude/hooks/*.py for hook function/filename matches."""
    if not _HOOKS_DIR.exists() or not HAS_BM25:
        return []
    py_files = sorted(_HOOKS_DIR.glob("*.py"))
    if not py_files:
        return []
    docs = [(p, _build_hook_doc(p)) for p in py_files]
    docs = [(p, d) for p, d in docs if d]
    if not docs:
        return []
    tokenized = [tokenize(d) for _, d in docs]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    return [(docs[i][0], scores[i]) for i in ranked[:limit] if scores[i] > 0]


def _has_hooks_keywords(prompt: str) -> bool:
    """Return True if prompt mentions hook-related terms."""
    low = prompt.lower()
    return any(kw in low for kw in _HOOKS_TRIGGER_KWS)


# ── Rich Mode: World Model ────────────────────────────────────────

def get_world_model(project_dir):
    """Load dead-ends and facts from .omc/world-model.json (--rich mode)."""
    wm_path = Path(project_dir) / ".omc" / "world-model.json"
    if not wm_path.exists():
        return [], []
    try:
        wm = json.loads(wm_path.read_text())
    except Exception:
        return [], []
    dead_ends = [
        f"  x {de.get('goal','')[:60]} -- {de.get('reason','')[:80]}"
        for de in wm.get("dead_ends", [])[-5:]
    ]
    facts = []
    for fact in wm.get("known_facts", []):
        if isinstance(fact, dict):
            facts.append(f"  * {fact['fact'][:80]}")
        elif isinstance(fact, str) and not any(
            fact.startswith(p) for p in ("paper:", "README:", "uncertain:")
        ):
            facts.append(f"  * {fact[:80]}")
    return dead_ends, facts[-8:]


# ── Session Decisions ─────────────────────────────────────────────

def get_session_decisions(project_dir):
    """Read .omc/session-decisions.md for uncommitted decisions."""
    p = Path(project_dir) / ".omc" / "session-decisions.md"
    if not p.exists():
        return []
    try:
        lines = p.read_text().strip().split("\n")
        return [l.strip() for l in lines if l.strip().startswith(">")][-5:]
    except Exception:
        return []


# ── Pending Decisions (from previous session Stop hook) ──────────

def consume_pending_decisions(project_dir: str):
    """
    이전 세션 stop-decision-capture.py가 남긴 .pending-decisions.json 읽고 삭제.
    Returns list of formatted strings for additionalContext injection, or [].
    """
    slug = project_dir.replace("/", "-")
    pending_path = Path.home() / ".claude" / "projects" / slug / "memory" / ".pending-decisions.json"
    if not pending_path.exists():
        return []

    try:
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
        decisions = payload.get("decisions", [])
        captured_at = payload.get("captured_at", "")[:16]  # "2026-04-14T12:34"
    except Exception:
        try:
            pending_path.unlink(missing_ok=True)
        except Exception:
            pass
        return []

    # 읽은 즉시 삭제 (1회성 전달)
    try:
        pending_path.unlink(missing_ok=True)
    except Exception:
        pass

    if not decisions:
        return []

    lines = [f"[PENDING MEMORY] 이전 세션({captured_at}) 결정 후보 — MEMORY.md 업데이트 필요 여부 판단:"]
    for d in decisions:
        tag = d.get("tag", "")
        ctx = d.get("context", "")
        lines.append(f"  [{tag}] {ctx}")
    lines.append("→ 위 항목 중 MEMORY.md에 없는 중요한 결정이 있으면 즉시 Edit tool로 기록하세요.")
    return lines


# ── Main ──────────────────────────────────────────────────────────

def _log_event(event_type, payload):
    """Opt-in telemetry wrapper — silent no-op if gate off. Never breaks hook path."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        log_event(event_type, payload)
    except Exception:
        pass


def main():
    import time as _time
    _t_start = _time.perf_counter()
    try:
        input_data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    prompt = input_data.get("prompt", "")

    # A/B scaffold: control arm skips injection entirely (CTX_AB_DISABLE=1).
    # Dashboard uses the logged ab_skipped events to count control-arm sessions.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import ab_disabled, log_event
        if ab_disabled():
            log_event("ab_skipped", {"hook": "bm25-memory", "reason": "CTX_AB_DISABLE"})
            sys.exit(0)
    except Exception:
        pass
    lines = []
    _blocks_fired = []  # for final hook_invoked telemetry summary

    # 0a. Pending decisions from previous session (Stop hook → queue file)
    pending = consume_pending_decisions(project_dir)
    if pending:
        lines.extend(pending)

    # 0b. Session decisions (uncommitted notes)
    session_notes = get_session_decisions(project_dir)
    if session_notes:
        lines.append("[SESSION NOTES (미커밋 판단)]")
        lines.extend(session_notes)

    # 1. G1: BM25 over decision corpus
    _t_g1 = _time.perf_counter()
    corpus = get_decision_corpus(project_dir)
    g1_header = ""
    if corpus:
        relevant = bm25_rank_decisions(corpus, prompt, top_k=7)
        if relevant:
            # Build forced display header (mechanically injected, not advisory)
            first_subj = relevant[0]["subject"][:70]
            rest_count = len(relevant) - 1
            g1_header = f'> **G1** (time memory): "{first_subj}" and {rest_count} more'

            lines.append(
                f"[RECENT DECISIONS] (BM25: top {len(relevant)} of {len(corpus)})"
            )
            for c in relevant:
                date = c.get("date", "")
                subj = c["subject"]
                prefix = f"  > [{date}] " if date else "  > "
                lines.append(f"{prefix}{subj}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g1_decisions",
                "count": len(relevant),
                "duration_ms": int((_time.perf_counter() - _t_g1) * 1000),
            })
            _blocks_fired.append("g1")

    # 2. G2: BM25 over project docs
    g2_files = []
    g2_keywords = []
    if prompt:
        _t_g2d = _time.perf_counter()
        doc_chunks = bm25_search_docs(project_dir, prompt, top_k=5)
        if doc_chunks:
            lines.append("[G2-DOCS] (BM25 relevant research docs)")
            for chunk in doc_chunks:
                chunk_lines = chunk.strip().split("\n")
                header = chunk_lines[0]  # "filename § section"
                fname = header.split(" §")[0].strip()
                if fname and fname not in g2_files:
                    g2_files.append(fname)
                snippet = ""
                if len(chunk_lines) > 1:
                    # Find first non-empty content line
                    for cl in chunk_lines[1:]:
                        cl = cl.strip()
                        if cl and not cl.startswith("#"):
                            snippet = cl[:120]
                            break
                lines.append(f"  > {header}")
                if snippet:
                    lines.append(f"    {snippet}")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_docs",
                "count": len(doc_chunks),
                "duration_ms": int((_time.perf_counter() - _t_g2d) * 1000),
            })
            _blocks_fired.append("g2_docs")

    # 3. G2: Code file discovery (graph → grep fallback)
    if prompt:
        keywords = extract_keywords(prompt)
        g2_keywords = keywords[:3]
        if keywords:
            _t_g2p = _time.perf_counter()
            db_path = find_db(project_dir)
            if db_path:
                graph_results = search_graph_for_prompt(db_path, keywords)
                if graph_results:
                    lines.append(f"[G2-PREFETCH] Related code for '{' '.join(keywords[:3])}':")
                    seen_files = set()
                    for label, name, fpath in graph_results:
                        lines.append(f"  {label}: {name} @ {fpath}")
                        seen_files.add(fpath)
                    if seen_files:
                        lines.append(f"  Start with: {', '.join(sorted(seen_files)[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_prefetch",
                        "count": len(graph_results),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_prefetch")
            else:
                # Fallback: git grep
                files = search_files_by_grep(project_dir, keywords)
                if files:
                    lines.append(f"[G2-GREP] Files matching '{' '.join(keywords[:3])}' (grep):")
                    for f in files:
                        lines.append(f"  {f}")
                    lines.append(f"  Start with: {', '.join(files[:3])}")
                    _log_event("block_fired", {
                        "hook": "bm25-memory", "block": "g2_grep",
                        "count": len(files),
                        "duration_ms": int((_time.perf_counter() - _t_g2p) * 1000),
                    })
                    _blocks_fired.append("g2_grep")

    # 3b. G2: Hooks file discovery (when hook-related terms in prompt)
    if prompt and _has_hooks_keywords(prompt):
        _t_g2h = _time.perf_counter()
        hook_results = search_hooks_files(prompt)
        if hook_results:
            lines.append(f"[G2-HOOKS] Hook files matching '{prompt[:40]}':")
            for hp, score in hook_results:
                lines.append(f"  {hp}  (score={score:.1f})")
            _log_event("block_fired", {
                "hook": "bm25-memory", "block": "g2_hooks",
                "count": len(hook_results),
                "duration_ms": int((_time.perf_counter() - _t_g2h) * 1000),
            })
            _blocks_fired.append("g2_hooks")

    # 4. World model (--rich)
    if RICH:
        dead_ends, facts = get_world_model(project_dir)
        if dead_ends:
            lines.append("[DEAD-ENDS -- do not retry]")
            lines.extend(dead_ends)
        if facts:
            lines.append("[KNOWN FACTS]")
            lines.extend(facts)

    if lines:
        # Prepend forced display header (mechanically enforced, replaces CLAUDE.md advisory)
        header_lines = []
        if g1_header:
            header_lines.append(g1_header)
        if g2_files or g2_keywords:
            files_str = ", ".join(f"`{f}`" for f in g2_files[:3]) if g2_files else "(docs BM25)"
            kw_str = " ".join(g2_keywords[:3]) if g2_keywords else ""
            via_str = f' — found via "{kw_str}"' if kw_str else ""
            header_lines.append(f"> **G2** (space search): {files_str}{via_str}")
        if header_lines:
            lines = header_lines + [""] + lines

        output = {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": "\n".join(lines),
            }
        }
        json.dump(output, sys.stdout)
        sys.stdout.flush()
        if header_lines:
            print("\n".join(header_lines), file=sys.stderr)
            sys.stderr.flush()

    # Final summary event: one record per hook invocation (outside `if lines:`)
    _log_event("hook_invoked", {
        "hook": "bm25-memory",
        "duration_ms": int((_time.perf_counter() - _t_start) * 1000),
        "prompt_len": len(prompt) if prompt else 0,
    })

    # ── P1: record what we injected for utility-rate measurement ─────
    # Stop hook reads this + the latest assistant turn + substring-matches
    # each item's distinctive tokens. Not stored when dashboard-internal.
    if os.environ.get("CTX_DASHBOARD_INTERNAL") != "1":
        try:
            # Preview = first 120 chars, newlines stripped (same privacy surface
            # as vault.db which already stores full prompts; this just makes the
            # dashboard see new prompts *before* vault.db incremental fires on Stop).
            preview = (prompt or "")[:120].replace("\n", " ").replace("\r", " ")
            injection = {
                "ts": _time.time(),
                "prompt_len": len(prompt) if prompt else 0,
                "prompt_preview": preview,
                "items": [],
            }
            # Collect distinctive substrings from emitted blocks.
            # Each item is (block, signature) — signature is a 4-20 char
            # distinctive substring the assistant's response can echo.
            # Meta/filler words from commit subjects that never represent a topic.
            # Drops CTX's internal taxonomy (live-infinite, iter, goal_vN) + conventional
            # commit prefixes + common English verbs — anything that would generate
            # false-positive matches against unrelated responses.
            _META_WORDS = frozenset([
                "live-infinite", "live-inf", "omc-live", "iter", "live",
                "goal_v1", "goal_v2", "goal_v3", "goal",
                "feat", "fix", "refactor", "perf", "docs", "test", "chore",
                "success", "section", "update", "add", "remove", "change",
                "fixed", "added", "removed", "completed",
            ])
            # Header-row detector for "> **G1/G2**" and similar markdown headers
            _is_header_line = lambda st: st.startswith("> **") and "** (" in st

            def _extract_content_tokens(subject: str, n: int = 5) -> list:
                """Pick up to N distinctive content tokens from a commit subject.
                Filters meta words, pure digits, punctuation-only fragments.
                Prefers longer words (more specific = better substring hit rate)."""
                candidates = []
                for w in subject.split():
                    w_clean = w.strip(".,()[]{}:;!?\"'").lower()
                    if len(w_clean) < 4:
                        continue
                    if w_clean in _META_WORDS:
                        continue
                    if w_clean.replace("/", "").replace(".", "").replace("-", "").isdigit():
                        continue   # 20260402, 58/∞, etc.
                    # Keep case of original for better citation-style match
                    candidates.append(w.strip(".,()[]{}:;!?\"'"))
                # Dedup preserving order, sort by length desc for specificity
                seen = set()
                uniq = [t for t in candidates if not (t.lower() in seen or seen.add(t.lower()))]
                uniq.sort(key=lambda t: -len(t))
                return uniq[:n]

            for line in lines:
                s = line.strip()
                # Skip markdown headers like "> **G1** (time memory): ..." — they are
                # not items, they're section labels that would leak into signatures.
                if _is_header_line(s):
                    continue
                # G1 decisions: "> [YYYY-MM-DD] subject" — capture date for age-based wow trigger
                if s.startswith("> [") and "]" in s:
                    close_idx = s.index("]")
                    date_str = s[3:close_idx]
                    subj = s[close_idx + 1:].strip()
                    tokens = _extract_content_tokens(subj, n=5)
                    if tokens:
                        item = {
                            "block": "g1",
                            "tokens": tokens,
                            "subject": subj[:200],  # preserved for semantic scoring
                        }
                        if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                            item["date"] = date_str
                        injection["items"].append(item)
                # G2-DOCS entries: "  > filename.md" → filename AS signature AND
                # also extract date-token + topic words from filename for more hit
                # surface (e.g. "20260411-g1-generalization-validation.md" also
                # matches on "generalization" / "validation").
                elif s.startswith("> ") and (".md" in s or s.endswith(".py")):
                    fname = s.lstrip("> ").strip().split(" §")[0].split()[0]
                    if fname:
                        # filename + its stem words as tokens
                        stem = fname.rsplit(".", 1)[0]
                        parts = [p for p in stem.replace("-", " ").replace("_", " ").split()
                                 if len(p) >= 4 and not p.isdigit()]
                        tokens = [fname] + parts[:4]
                        # Subject for semantic: the filename's natural-language form
                        subject = " ".join(parts) if parts else fname
                        injection["items"].append({
                            "block": "g2_docs", "tokens": tokens, "subject": subject[:200]
                        })
                # G2-PREFETCH: symbol names (function/class) + their path
                elif ": " in s and "@" in s and any(k in s for k in ("Function:", "Class:", "Method:", "Module:", "File:")):
                    try:
                        name = s.split(":", 1)[1].split("@")[0].strip()
                        path = s.split("@", 1)[1].strip() if "@" in s else ""
                        path_base = path.rsplit("/", 1)[-1] if path else ""
                        tokens = [t for t in [name, path_base] if t and len(t) >= 4]
                        if tokens:
                            injection["items"].append({
                                "block": "g2_prefetch",
                                "tokens": tokens,
                                "subject": f"{name} in {path}"[:200],
                            })
                    except Exception:
                        pass
            Path(os.path.expanduser("~/.claude/last-injection.json")).write_text(
                json.dumps(injection)
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
