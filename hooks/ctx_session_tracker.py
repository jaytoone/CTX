#!/usr/bin/env python3
"""
CTX Session Tracker — PostToolUse Hook
Read/Edit/Write 이벤트를 캡처하여 세션 컨텍스트 로그 업데이트.
ctx_real_loader.py가 이 로그를 읽어 장기 세션 컨텍스트 유지에 활용.
"""

import hashlib
import json
import os
import sys
import time

LOG_PATH = os.path.expanduser("~/.claude/ctx_session_log.json")
PERSISTENT_PATH = os.path.expanduser("~/.claude/ctx_persistent_memory.json")
MAX_FILES_PER_SESSION = 50
SESSION_TTL = 86400      # 24 hours (ephemeral session log)
PERSISTENT_TTL = 2592000 # 30 days (cross-session persistent memory)
PROMOTE_THRESHOLD = 3    # accesses within a session to promote to persistent


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Read", "Edit", "Write"):
        return

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    cwd = data.get("cwd", "")

    if not file_path or not cwd:
        return

    # Resolve absolute path
    if not os.path.isabs(file_path):
        file_path = os.path.join(cwd, file_path)

    # Only track files within the cwd
    try:
        rel_path = os.path.relpath(file_path, cwd)
    except ValueError:
        return

    # Skip paths that escape cwd (e.g. "../something")
    if rel_path.startswith(".."):
        return

    # Skip files in .git / __pycache__ / node_modules
    skip_prefixes = (".git", "__pycache__", "node_modules", ".venv", "venv")
    parts = rel_path.replace("\\", "/").split("/")
    if any(p in skip_prefixes for p in parts):
        return

    cwd_hash = hashlib.md5(cwd.encode()).hexdigest()[:8]
    now = time.time()

    # Load existing log
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            log_data = json.load(f)
    except Exception:
        log_data = {"sessions": {}}

    sessions = log_data.setdefault("sessions", {})

    # Purge sessions older than TTL
    expired = [h for h, s in sessions.items()
               if now - s.get("updated_at", 0) > SESSION_TTL]
    for h in expired:
        del sessions[h]

    # Get or create current session
    session = sessions.setdefault(cwd_hash, {
        "cwd": cwd,
        "files": {},
        "updated_at": now,
    })
    session["cwd"] = cwd
    session["updated_at"] = now

    files = session.setdefault("files", {})

    # Update file entry
    entry = files.get(rel_path, {"access_count": 0})
    entry["last_accessed"] = now
    entry["access_count"] = entry.get("access_count", 0) + 1
    entry["tool"] = tool_name
    files[rel_path] = entry

    # Trim to MAX_FILES_PER_SESSION (remove oldest by last_accessed)
    if len(files) > MAX_FILES_PER_SESSION:
        sorted_files = sorted(files.items(), key=lambda x: x[1].get("last_accessed", 0))
        excess = len(files) - MAX_FILES_PER_SESSION
        for rel, _ in sorted_files[:excess]:
            del files[rel]

    session["files"] = files

    # Write back
    try:
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
    except Exception:
        pass

    # Promote frequently-accessed files to cross-session persistent memory
    promote_to_persistent(cwd, cwd_hash, files, now)


def promote_to_persistent(cwd: str, cwd_hash: str, files: dict, now: float) -> None:
    """Promote files with access_count >= PROMOTE_THRESHOLD to persistent memory."""
    candidates = {
        rel: info for rel, info in files.items()
        if info.get("access_count", 0) >= PROMOTE_THRESHOLD
    }
    if not candidates:
        return

    try:
        with open(PERSISTENT_PATH, "r", encoding="utf-8") as f:
            pm = json.load(f)
    except Exception:
        pm = {"projects": {}}

    projects = pm.setdefault("projects", {})

    # Purge projects older than TTL
    expired = [h for h, p in projects.items()
               if now - p.get("last_updated", 0) > PERSISTENT_TTL]
    for h in expired:
        del projects[h]

    project = projects.setdefault(cwd_hash, {
        "cwd": cwd, "files": {}, "last_updated": now,
    })
    project["cwd"] = cwd
    project["last_updated"] = now

    pm_files = project.setdefault("files", {})
    for rel, info in candidates.items():
        existing = pm_files.get(rel, {"cumulative_count": 0})
        existing["cumulative_count"] = existing.get("cumulative_count", 0) + info.get("access_count", 0)
        existing["last_accessed"] = info.get("last_accessed", now)
        existing["last_tool"] = info.get("tool", "Read")
        pm_files[rel] = existing

    # Cap at 100 files per project (keep most-accessed)
    if len(pm_files) > 100:
        sorted_pm = sorted(pm_files.items(), key=lambda x: x[1].get("cumulative_count", 0), reverse=True)
        pm_files = dict(sorted_pm[:100])
        project["files"] = pm_files

    try:
        with open(PERSISTENT_PATH, "w", encoding="utf-8") as f:
            json.dump(pm, f, indent=2)
    except Exception:
        pass


if __name__ == "__main__":
    main()
