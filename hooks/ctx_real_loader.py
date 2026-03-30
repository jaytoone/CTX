#!/usr/bin/env python3
"""
CTX Real Loader Hook — UserPromptSubmit

AdaptiveTriggerRetriever (CTX 프로덕션 라이브러리) 기반 컨텍스트 주입 훅.
/home/jayone/Project/CTX의 실제 구현을 사용 — ctx_loader.py 인라인 구현 대체.

개선 사항:
  - 프로덕션급 TriggerClassifier (COMMON_WORDS 필터, CONCEPT_EXTRACT_PATTERNS)
  - BM25L 기반 시맨틱 검색
  - Intent 판단 위임: hook에서 키워드/regex 분류 제거 → Claude 자체 판단
    (Claude가 context + full prompt를 동시에 보므로 키워드보다 정확)
  - 인덱싱 P99=2.8ms @307files — 재인덱싱 비용 무시 가능

Skip 조건:
  - 프롬프트 < 15자  |  / 시작 (slash command)
  - [noctx] 태그  |  CTX import 실패 (무음 폴백)
"""

import json
import os
import sys
import time

CTX_PROJECT = "/home/jayone/Project/CTX"
SESSION_LOG  = os.path.expanduser("~/.claude/ctx_session_log.json")
PERSIST_MEM  = os.path.expanduser("~/.claude/ctx_persistent_memory.json")

MAX_FILES = 6
TOP_CORE  = 3   # top N files shown as "core" (★), rest as auxiliary (·)

EMPTY = json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": ""
    }
})

_EXCLUDED = frozenset({
    '.git', '__pycache__', 'node_modules', '.venv', 'venv',
    'dist', 'build', '.mypy_cache', '.pytest_cache', '.ruff_cache',
})


def _emit(context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context
        }
    }))


def _load_hook_input() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _should_skip(prompt: str) -> bool:
    return (
        len(prompt) < 15
        or prompt.startswith("/")
        or "[noctx]" in prompt.lower()
        or prompt.startswith("[raw]")
    )


def _count_src_files(cwd: str) -> int:
    count = 0
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in _EXCLUDED]
        count += sum(1 for f in files if f.endswith(('.py', '.ts', '.js', '.go')))
        if count > 10:
            return count
    return count


def _load_session_files(cwd: str = "") -> list:
    """ctx_session_tracker.py 포맷: {"sessions": {cwd_hash: {"cwd": ..., "files": {rel_path: {...}}}}}
    cwd 매칭 세션만 반환 — 타 프로젝트 파일 bleeding 방지.
    """
    try:
        if not os.path.exists(SESSION_LOG):
            return []
        with open(SESSION_LOG) as f:
            data = json.load(f)
        now = time.time()
        out = []
        seen: set = set()
        for session in data.get("sessions", {}).values():
            if (now - session.get("updated_at", 0)) / 3600 > 2:
                continue
            # cwd 필터: 현재 프로젝트 세션만 포함
            if cwd and session.get("cwd", "") != cwd:
                continue
            for rel_path, info in session.get("files", {}).items():
                if rel_path in seen:
                    continue
                if info.get("access_count", 0) >= 1:
                    out.append((rel_path, info.get("last_accessed", 0)))
                    seen.add(rel_path)
        # Sort by recency
        out.sort(key=lambda x: x[1], reverse=True)
        return [fp for fp, _ in out[:4]]
    except Exception:
        return []


def _load_persist_files(cwd: str) -> list:
    try:
        if not os.path.exists(PERSIST_MEM):
            return []
        with open(PERSIST_MEM) as f:
            data = json.load(f)
        for proj_path, entries in data.get("projects", {}).items():
            if cwd.startswith(proj_path) or proj_path.startswith(cwd):
                return [e["rel_path"] for e in entries[:3]]
        return []
    except Exception:
        return []


def main() -> None:
    hook_input = _load_hook_input()
    prompt = hook_input.get("prompt", "")

    if _should_skip(prompt):
        print(EMPTY)
        return

    cwd = hook_input.get("cwd", os.getcwd())
    if cwd == os.path.expanduser("~/.claude/hooks"):
        print(EMPTY)
        return

    if _count_src_files(cwd) < 3:
        print(EMPTY)
        return

    # Import CTX
    if CTX_PROJECT not in sys.path:
        sys.path.insert(0, CTX_PROJECT)

    try:
        from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
    except ImportError:
        print(EMPTY)
        return

    # Build index + retrieve
    try:
        retriever = AdaptiveTriggerRetriever(cwd)
        result = retriever.retrieve(query_id="hook", query_text=prompt, k=MAX_FILES)
    except Exception:
        print(EMPTY)
        return

    if not result.retrieved_files:
        print(EMPTY)
        return

    n_total = len(retriever.file_paths)

    # Trigger info
    triggers = retriever.classifier.classify(prompt)
    primary = triggers[0] if triggers else None
    if primary:
        trigger_label = primary.trigger_type.name
        query_value   = str(primary.value).replace("\n", " ")[:50]
        confidence    = primary.confidence
    else:
        trigger_label = "DEFAULT"
        query_value   = prompt[:40].replace("\n", " ")
        confidence    = 0.5

    # Session + persistent context (cwd-filtered to avoid cross-project bleeding)
    session_files = _load_session_files(cwd)
    persist_files = _load_persist_files(cwd)

    # Build output
    lines = []

    # Token savings
    n_loaded = len(result.retrieved_files)
    saved_pct = int((1 - n_loaded / n_total) * 100) if n_total > 0 else 0
    low_conf  = confidence < 0.5 and trigger_label == "SEMANTIC_CONCEPT"

    # Header
    conf_tag = f" ⚠ low" if low_conf else ""
    lines.append(
        f"[CTX] {trigger_label} | {n_loaded}/{n_total} files — ~{saved_pct}% tokens saved"
        f" | conf {confidence:.2f}{conf_tag}"
    )
    if low_conf:
        lines.append("  ⚠ Low confidence — add specific symbol/file names for better results")

    # Code files: core (★ top 3) vs auxiliary (·)
    core_files = result.retrieved_files[:TOP_CORE]
    aux_files  = result.retrieved_files[TOP_CORE:]
    label = "Code files (★ core  · aux):" if aux_files else "Code files:"
    lines.append(label)
    for fp in core_files:
        rel = os.path.relpath(fp, cwd) if os.path.isabs(fp) else fp
        score = result.scores.get(fp, 0)
        lines.append(f"★ {rel} [score={score:.3f}]")
    for fp in aux_files:
        rel = os.path.relpath(fp, cwd) if os.path.isabs(fp) else fp
        score = result.scores.get(fp, 0)
        lines.append(f"· {rel} [score={score:.3f}]")

    # Session context (de-duped)
    retrieved_set = set(result.retrieved_files)
    fresh_session = [f for f in session_files if f not in retrieved_set]
    if fresh_session:
        lines.append(f"Recent session ({len(fresh_session)} files, <2h):")
        for fp in fresh_session[:3]:
            lines.append(f"• {fp}")

    # Persistent memory (de-duped)
    all_shown = retrieved_set | set(fresh_session)
    fresh_persist = [f for f in persist_files if f not in all_shown]
    if fresh_persist:
        lines.append(f"Persistent memory ({len(fresh_persist)} files, cross-session):")
        for fp in fresh_persist:
            lines.append(f"• {fp}")

    # Intent guidance for Claude — use the prompt to decide:
    # read → use files as reference only
    # modify → treat files as potentially buggy code to fix
    # create → use files as patterns but write new code
    lines.append("(Use the prompt intent to decide how to treat this context.)")

    _emit("\n".join(lines))


if __name__ == "__main__":
    main()
