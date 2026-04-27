#!/usr/bin/env python3
"""
grep_fallback_router.py — PostToolUse Hook (Grep)

Grep 결과 품질 신호 감지 → mcp__code-search__search_code 힌트 주입.
Claude가 다음 도구 선택시 semantic 검색을 자동으로 시도하도록 유도.

트리거 신호 (3가지):
  Signal 1: 결과 0개           — 명확한 검색 실패
  Signal 2: test/mock만 히트   — 구현 코드 못 찾음 (HIGH 가치)
  Signal 3: 결과 <3 + 다단어   — 개념 쿼리에 sparse 결과 (MEDIUM 가치)

출력: hookSpecificOutput.additionalContext (JSON to stdout)
"""

import json
import re
import sys
from typing import List, Optional, Tuple


TEST_PATH_PATTERNS = ("test", "spec", "mock", "fixture", "__test__", "_test.")


def parse_result(tool_response) -> Tuple[int, List[str]]:
    """결과 개수와 히트된 파일 경로 목록 반환."""
    raw = ""
    if tool_response is None:
        return 0, []
    if isinstance(tool_response, str):
        raw = tool_response
    elif isinstance(tool_response, dict):
        content = tool_response.get("content", "")
        if isinstance(content, str):
            raw = content
        elif isinstance(content, list):
            raw = " ".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            )

    raw = raw.strip()
    if not raw or "No matches found" in raw or raw == "[]":
        return 0, []

    # 파일 경로 추출 (줄의 첫 번째 필드, 콜론 앞)
    paths = []
    for line in raw.splitlines():
        m = re.match(r'^([^\s:][^:]+):\d+:', line)
        if m:
            paths.append(m.group(1).lower())
        elif line.strip() and not line.startswith(" "):
            paths.append(line.strip().lower())

    count = len(paths) if paths else (1 if raw else 0)
    return count, list(set(paths))


def detect_signal(pattern: str, count: int, paths: List[str]) -> Optional[str]:
    """
    백업 검색이 필요한 신호를 감지.
    신호 없으면 None 반환.
    """
    # Signal 1: 결과 없음
    if count == 0:
        return "zero_results"

    # Signal 2: test/mock 파일에만 히트 (구현 코드 없음)
    if count > 0 and paths:
        non_test = [p for p in paths
                    if not any(pat in p for pat in TEST_PATH_PATTERNS)]
        if len(non_test) == 0:
            return "test_only"

    # Signal 3: 결과 희소(<3) + 다단어 개념 쿼리
    words = pattern.strip().split()
    if count < 3 and len(words) >= 2 and not re.match(r'^[A-Z][a-z]+[A-Z]', pattern):
        return "sparse_concept"

    return None


SIGNAL_MESSAGES = {
    "zero_results": (
        "Grep returned 0 results",
        "No exact matches found — semantic search may find indirect/synonymous references"
    ),
    "test_only": (
        "Grep results are in test/mock files only",
        "Implementation code not found via text search — semantic search recommended for production code"
    ),
    "sparse_concept": (
        "Grep returned sparse results (<3) for multi-word concept query",
        "Concept-level query may have broader context — semantic search may find more relevant files"
    ),
}


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_name = data.get("tool_name", "")
    if tool_name != "Grep":
        return

    tool_input = data.get("tool_input", {})
    pattern = tool_input.get("pattern", "").strip()
    path = tool_input.get("path", data.get("cwd", "."))

    # 너무 짧은 패턴 제외
    if len(pattern) < 3:
        return

    # 순수 정규식 메타문자만 제외
    if all(c in r'.*+?^${}[]|()\\' for c in pattern):
        return

    tool_response = data.get("tool_response", "")
    count, paths = parse_result(tool_response)

    signal = detect_signal(pattern, count, paths)
    if signal is None:
        return

    # Opt-in telemetry: which grep-fallback signal fired (no content)
    try:
        import os as _os
        sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        log_event("grep_signal", {
            "hook": "g2-fallback",
            "signal": signal,
            "result_count": count,
        })
    except Exception:
        pass

    title, reason = SIGNAL_MESSAGES[signal]
    hint_lines = [
        f"[GREP-FALLBACK:{signal.upper()}] {title} for: \"{pattern}\"",
        f"Reason: {reason}",
        f"Semantic search → mcp__code-search__search_code",
        f"  Suggested: search_code(query=\"{pattern[:80]}\", project_path=\"{path}\")",
    ]

    result = json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(hint_lines)
        }
    })
    print(result)


if __name__ == "__main__":
    main()
