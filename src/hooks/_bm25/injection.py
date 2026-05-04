"""
injection.py — P1 injection tracking for bm25-memory utility-rate measurement.

Provides:
  write_injection_record(prompt, lines, retrieval_meta, vec_sock, vec_disabled,
                         bge_sock, session_id) -> None
"""
import json
import os
from pathlib import Path

# Meta/filler words that are never meaningful injection tokens
_META_WORDS = frozenset([
    "live-infinite", "live-inf", "omc-live", "iter", "live",
    "goal_v1", "goal_v2", "goal_v3", "goal",
    "feat", "fix", "refactor", "perf", "docs", "test", "chore",
    "success", "section", "update", "add", "remove", "change",
    "fixed", "added", "removed", "completed",
])


def _is_header_line(s: str) -> bool:
    return s.startswith("> **") and "** (" in s


def _extract_content_tokens(subject: str, n: int = 5) -> list:
    """Pick up to N distinctive content tokens from a commit subject."""
    candidates = []
    for w in subject.split():
        w_clean = w.strip(".,()[]{}:;!?\"'").lower()
        if len(w_clean) < 4:
            continue
        if w_clean in _META_WORDS:
            continue
        if w_clean.replace("/", "").replace(".", "").replace("-", "").isdigit():
            continue
        candidates.append(w.strip(".,()[]{}:;!?\"'"))
    seen: set = set()
    uniq = [t for t in candidates if not (t.lower() in seen or seen.add(t.lower()))]
    uniq.sort(key=lambda t: -len(t))
    return uniq[:n]


def _collect_items(lines: list) -> list:
    """Parse injected output lines into structured items for utility tracking."""
    items = []
    for line in lines:
        s = line.strip()
        if _is_header_line(s):
            continue
        # G1 decisions: "> [YYYY-MM-DD] subject"
        if s.startswith("> [") and "]" in s:
            close_idx = s.index("]")
            date_str = s[3:close_idx]
            subj = s[close_idx + 1:].strip()
            tokens = _extract_content_tokens(subj, n=5)
            if tokens:
                item: dict = {
                    "block": "g1_decisions",
                    "tokens": tokens,
                    "subject": subj[:200],
                }
                if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                    item["date"] = date_str
                items.append(item)
        # G2-DOCS entries: "  > filename.md § section"
        elif s.startswith("> ") and (".md" in s or s.endswith(".py")):
            fname = s.lstrip("> ").strip().split(" §")[0].split()[0]
            if fname:
                stem = fname.rsplit(".", 1)[0]
                parts = [p for p in stem.replace("-", " ").replace("_", " ").split()
                         if len(p) >= 4 and not p.isdigit()]
                tokens = [fname] + parts[:4]
                subject = " ".join(parts) if parts else fname
                items.append({"block": "g2_docs", "tokens": tokens, "subject": subject[:200]})
        # G2-PREFETCH: "Function: name @ path"
        elif ": " in s and "@" in s and any(k in s for k in
                                             ("Function:", "Class:", "Method:", "Module:", "File:")):
            try:
                name = s.split(":", 1)[1].split("@")[0].strip()
                path = s.split("@", 1)[1].strip() if "@" in s else ""
                path_base = path.rsplit("/", 1)[-1] if path else ""
                tokens = [t for t in [name, path_base] if t and len(t) >= 4]
                if tokens:
                    items.append({
                        "block": "g2_prefetch",
                        "tokens": tokens,
                        "subject": f"{name} in {path}"[:200],
                    })
            except Exception:
                pass
    return items


def write_injection_record(
    prompt: str,
    lines: list,
    retrieval_meta: dict,
    vec_sock,
    vec_disabled: bool,
    bge_sock,
    session_id: str,
) -> None:
    """Write ~/.claude/last-injection.json and ~/.claude/last-retrieval-meta.json.

    Silent no-op if CTX_DASHBOARD_INTERNAL=1 or any exception occurs.
    """
    if os.environ.get("CTX_DASHBOARD_INTERNAL") == "1":
        return
    try:
        import time as _t
        preview = (prompt or "")[:120].replace("\n", " ").replace("\r", " ")
        prompt_full_str = (prompt or "").replace("\r", "")
        try:
            _proj = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
            _project_name = os.path.basename(_proj.rstrip("/")) if _proj else None
        except Exception:
            _project_name = None

        injection = {
            "ts": _t.time(),
            "prompt_len": len(prompt) if prompt else 0,
            "prompt_preview": preview,
            "prompt_full": prompt_full_str,
            "project": _project_name,
            "items": _collect_items(lines),
        }
        Path(os.path.expanduser("~/.claude/last-injection.json")).write_text(
            json.dumps(injection)
        )

        retrieval_meta["vec_daemon_up"] = vec_sock.exists() and not vec_disabled
        retrieval_meta["bge_daemon_up"] = bge_sock.exists() and bool(
            os.environ.get("CTX_CROSS_ENCODER", "1") != "0"
        )
        retrieval_meta["query_char_count"] = len(prompt) if prompt else 0
        retrieval_meta["session_id"] = session_id or ""
        Path(os.path.expanduser("~/.claude/last-retrieval-meta.json")).write_text(
            json.dumps(retrieval_meta)
        )
    except Exception:
        pass
