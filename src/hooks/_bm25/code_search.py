"""
code_search.py — G2 code file discovery for bm25-memory.

Provides:
  extract_keywords(prompt) -> list[str]
  find_db(project_dir) -> str|None
  log_retrieved_nodes(project_dir, session_id, prompt, block, items)
  check_and_trigger_reindex(project_dir, db_path) -> str|None
  search_graph_for_prompt(db_path, keywords, limit=5) -> list[tuple]
  search_files_by_grep(project_dir, keywords, limit=5) -> list[str]
"""
import json
import os
import re
import subprocess

# ── Code keyword / mapping ───────────────────────────────────────────────────

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

_REINDEX_LOCK = os.path.expanduser("~/.cache/codebase-memory-mcp/.reindex_in_progress")
_STALE_THRESHOLD_HOURS = 24


# ── Keyword extraction ────────────────────────────────────────────────────────

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


# ── DB discovery ─────────────────────────────────────────────────────────────

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


# ── Citation probe ───────────────────────────────────────────────────────────

def log_retrieved_nodes(project_dir, session_id, prompt, block, items):
    """
    Append a retrieval event to .omc/retrieval_log.jsonl.

    Args:
        project_dir: project root path
        session_id: Claude session ID (from input_data)
        prompt: user prompt (first 120 chars stored)
        block: "g1_decisions" | "g2_docs" | "g2_prefetch" | "g2_hooks"
        items: list of dicts, each with at minimum {"id": str, "text": str}
               g1: {"id": hash, "text": subject, "date": date}
               g2_docs: {"id": filename, "text": unit_preview}
               g2_prefetch: {"id": fpath, "text": f"{label}:{name}"}
    """
    if not items:
        return
    try:
        import time as _t
        log_path = os.path.join(project_dir, ".omc", "retrieval_log.jsonl")
        entry = {
            "ts": _t.time(),
            "session_id": session_id,
            "prompt_prefix": prompt[:120],
            "block": block,
            "items": items[:10],
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── Staleness check + reindex ─────────────────────────────────────────────────

def check_and_trigger_reindex(project_dir, db_path):
    """
    Check if codebase-memory-mcp DB is stale (>24h). If so, spawn an incremental
    reindex in the background (non-blocking). Returns a warning string if stale,
    or None if fresh.
    """
    try:
        import time as _t_mod
        age_hours = (_t_mod.time() - os.path.getmtime(db_path)) / 3600
    except OSError:
        return None

    if age_hours < _STALE_THRESHOLD_HOURS:
        return None

    age_str = f"{age_hours:.0f}h" if age_hours < 48 else f"{age_hours/24:.1f}d"

    if os.path.exists(_REINDEX_LOCK):
        try:
            import time as _t_mod
            lock_age = (_t_mod.time() - os.path.getmtime(_REINDEX_LOCK)) / 60
            if lock_age < 10:
                return f"⚠ G2-CODE DB stale ({age_str}) — reindex already running"
        except OSError:
            pass

    try:
        args = json.dumps({"repo_path": project_dir, "mode": "fast"})
        cmd = ["codebase-memory-mcp", "cli", "index_repository", args]
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        open(_REINDEX_LOCK, "w").close()
        return f"⚠ G2-CODE DB stale ({age_str}) — auto-reindex triggered (fast mode, background)"
    except Exception:
        return f"⚠ G2-CODE DB stale ({age_str}) — run: codebase-memory-mcp cli index_repository to reindex"


# ── Graph and grep search ─────────────────────────────────────────────────────

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
