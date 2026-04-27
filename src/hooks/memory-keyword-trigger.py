#!/usr/bin/env python3
"""
memory-keyword-trigger.py
UserPromptSubmit Hook: 중요 결정 키워드 감지 → MEMORY.md 즉시 저장 강제
"""
import json
import sys
import os
import re
from pathlib import Path

DECISION_PATTERNS = [
    # 사람 제외/포함
    r"제외하기로",
    r"제외\s*(했|한|함|결정|예정)",
    r"더\s*이상\s*(연락|팔로업|DM|메시지)\s*(안|하지\s*않|하지\s*말)",
    r"(팔로업|follow.?up)\s*(안|하지\s*말|중단|skip)",
    r"(제거|빼기|빼기로|제외)\s*(했|한|함)",
    r"(kill|킬|중단|종료|접다|포기)\s*(했|한|함|결정|예정|하기로)",
    # 프로젝트 상태
    r"(프로젝트|아이템|서비스|kool|CL|commentlens)\s*(kill|킬|중단|종료|접다|사망)",
    r"(kill|킬)\s*(confirmed|완료|됐|됨|했어)",
    # 일정/마감
    r"(기준|기한|데드라인|deadline)\s*.{0,10}(4/|월|일|week|주)",
    # 채널/전략 결정
    r"(채널|전략|방법|접근)\s*(변경|바꾸기로|결정|확정)",
    r"(linkedin|이메일|콜드)\s*(안\s*함|중단|그만)",
    # 명시적 기억 요청
    r"기억\s*(해|해줘|해라|해두)",
    r"저장\s*(해|해줘|해라|해두)",
    r"메모\s*(해|해줘|해라|해두)",
    # 기술 결정 (CTX/오개발 프로젝트)
    r"(rollback|롤백|되돌리기로|원복)\s*(했|한|함|결정|예정|하기로)",
    r"(iter|iteration)\s*\d+\s*(완료|complete|success|done)",
    r"(goal|목표)\s*(변경|바꾸기로|새로운|new)\s*(했|한|함|결정|예정|하기로|:)",
    r"(캐시|cache)\s*(구현|완료|설계|도입|추가)\s*(됐|됨|완료|했)",
    r"(eval|평가|benchmark)\s*(안정화|고정|확정|완료)",
    r"(recall|score|수치|성능)\s*[\d.]+\s*(달성|고정|확정|완료)",
    r"/live\s+\w",  # /live <새목표> — omc goal 변경
]

DECISION_PATTERNS_COMPILED = [re.compile(p, re.IGNORECASE) for p in DECISION_PATTERNS]

def detect_decision(prompt: str) -> list[str]:
    """감지된 결정 패턴 반환"""
    matched = []
    for pat in DECISION_PATTERNS_COMPILED:
        m = pat.search(prompt)
        if m:
            # 매치 주변 컨텍스트 (±20자)
            start = max(0, m.start() - 20)
            end = min(len(prompt), m.end() + 20)
            matched.append(prompt[start:end].strip())
    return matched

def get_memory_path() -> str:
    """현재 프로젝트의 MEMORY.md 경로 계산 — Claude Code 규칙: / → - (leading dash 포함)"""
    cwd = os.getcwd()
    # Claude Code: /home/jayone/Project/Sales → -home-jayone-Project-Sales (leading - 유지)
    safe_path = cwd.replace("/", "-").replace(" ", "-")
    return os.path.expanduser(f"~/.claude/projects/{safe_path}/memory/MEMORY.md")

def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    prompt = data.get("prompt", "")
    if not prompt or len(prompt) < 3:
        sys.exit(0)

    # A/B scaffold: control arm skips even the decision-keyword nudge.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import ab_disabled, log_event
        if ab_disabled():
            log_event("ab_skipped", {"hook": "memory-keyword-trigger", "reason": "CTX_AB_DISABLE"})
            sys.exit(0)
    except Exception:
        pass

    decisions = detect_decision(prompt)
    if not decisions:
        sys.exit(0)

    # Opt-in telemetry: record that a decision keyword fired (no prompt content)
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from _ctx_telemetry import log_event
        log_event("decision_captured", {
            "hook": "memory-keyword-trigger",
            "category": "keyword_match",
            "pattern_id": str(len(decisions)),  # count of matches as coarse id, no content
        })
    except Exception:
        pass

    memory_path = get_memory_path()

    # 감지된 결정 출력 → Claude에게 MEMORY.md 즉시 저장 강제
    print("[MEMORY TRIGGER] 중요 결정이 감지되었습니다.")
    print(f"감지된 내용: {' / '.join(decisions[:3])}")
    print(f"MEMORY.md 경로: {memory_path}")
    print()
    print("MANDATORY: 이 응답에서 반드시 아래 작업을 수행하세요:")
    print(f"  1. Edit tool로 {memory_path} 에 이 결정을 기록하세요.")
    print("  2. 형식: '- [이름/항목]: [결정 내용] — [날짜/이유]'")
    print("  3. 다른 작업보다 MEMORY.md 업데이트를 먼저 실행하세요.")

    sys.exit(0)

if __name__ == "__main__":
    main()
