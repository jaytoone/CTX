"""Atomic settings.json patcher for ctx-install.

patch_settings(path, new_hooks, dry_run) — merge CTX hook entries in.
unpatch_settings(path, commands, dry_run) — remove CTX hook entries by command string.
_load(path) — read settings.json safely (returns {} on missing/corrupt).

Safety guarantees:
- Settings file is NEVER partially written (write-to-temp then atomic rename).
- A timestamped backup is created before every write.
- Existing hooks from other tools are never removed.
- Idempotent: re-running install never duplicates entries.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PatchResult:
    ok: bool
    added: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    backup: str | None = None
    error: str | None = None

    def summary(self) -> str:
        lines = []
        if self.error:
            lines.append(f"  ERROR: {self.error}")
            return "\n".join(lines)
        if self.backup:
            lines.append(f"  backup: {self.backup}")
        if self.added:
            lines.append(f"  added {len(self.added)} hook(s): {', '.join(self.added)}")
        if self.skipped:
            lines.append(f"  already present ({len(self.skipped)} skipped): {', '.join(self.skipped)}")
        if not self.added and not self.skipped:
            lines.append("  no changes")
        return "\n".join(lines) if lines else "  ok"


def _load(path: Path) -> dict:
    """Read settings.json. Returns {} on missing or invalid JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_atomic(path: Path, data: dict) -> str:
    """Write data to path atomically (temp file + rename). Returns backup path or ''."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup = path.with_suffix(f".backup_{ts}.json")
    backup_made = False
    if path.exists():
        shutil.copy2(path, backup)
        backup_made = True

    tmp = path.with_suffix(".tmp_ctx")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return str(backup) if backup_made else ""


def _cmd_in_settings(settings: dict, command: str) -> bool:
    """Return True if this exact command string already exists anywhere in hooks."""
    for entries in settings.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("command") == command:
                    return True
    return False


def patch_settings(path: Path, new_hooks: dict, dry_run: bool = False) -> PatchResult:
    """Merge new_hooks into settings.json.

    new_hooks format (same as what _new_hooks_block() returns):
      {
        "UserPromptSubmit": [{"hooks": [{"type": "command", "command": "..."}]}],
        "PostToolUse": [{"matcher": "Grep", "hooks": [...]}],
        ...
      }
    Entries that already exist (by command string) are skipped.
    """
    settings = _load(path)
    hooks_block = settings.setdefault("hooks", {})
    added, skipped = [], []

    for event, entries in new_hooks.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if _cmd_in_settings(settings, cmd):
                    skipped.append(_short(cmd))
                    continue
                if not dry_run:
                    # Merge: append entry to the event list
                    event_list = hooks_block.setdefault(event, [])
                    # For PostToolUse, try to find an existing entry with same matcher
                    if event == "PostToolUse" and "matcher" in entry:
                        matcher = entry["matcher"]
                        existing = next(
                            (e for e in event_list if e.get("matcher") == matcher), None
                        )
                        if existing:
                            existing.setdefault("hooks", []).append(hook)
                        else:
                            event_list.append({"matcher": matcher, "hooks": [hook]})
                    else:
                        event_list.append({"hooks": [hook]})
                added.append(_short(cmd))

    if dry_run:
        return PatchResult(ok=True, added=added, skipped=skipped)

    if not added:
        return PatchResult(ok=True, added=[], skipped=skipped)

    try:
        backup = _save_atomic(path, settings)
        return PatchResult(ok=True, added=added, skipped=skipped, backup=backup)
    except OSError as e:
        return PatchResult(ok=False, error=str(e))


def unpatch_settings(path: Path, commands: list[str], dry_run: bool = False) -> PatchResult:
    """Remove hook entries whose command matches any string in `commands`."""
    settings = _load(path)
    removed, not_found = [], []
    hooks_block = settings.get("hooks", {})

    for event, entries in list(hooks_block.items()):
        new_entries = []
        for entry in entries:
            remaining = [h for h in entry.get("hooks", []) if h.get("command") not in commands]
            dropped = [h for h in entry.get("hooks", []) if h.get("command") in commands]
            for h in dropped:
                removed.append(_short(h["command"]))
            if remaining:
                entry = {**entry, "hooks": remaining}
                new_entries.append(entry)
        hooks_block[event] = new_entries

    for cmd in commands:
        if not any(cmd == r or _short(cmd) == r for r in removed):
            not_found.append(_short(cmd))

    if dry_run:
        return PatchResult(ok=True, added=removed, skipped=not_found)

    if not removed:
        return PatchResult(ok=True, added=[], skipped=not_found,
                           error=None if not_found else f"not found: {', '.join(not_found)}")

    try:
        backup = _save_atomic(path, settings)
        return PatchResult(ok=True, added=removed, backup=backup)
    except OSError as e:
        return PatchResult(ok=False, error=str(e))


def _short(cmd: str) -> str:
    """Truncate long command strings for display."""
    return cmd[:60] + "…" if len(cmd) > 60 else cmd
