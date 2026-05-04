"""
output.py — Output formatting and emission for bm25-memory orchestrator.

Provides:
  build_header_lines(g1_header, g2_files, g2_keywords, vec_sock, vec_disabled,
                     bge_sock, use_cross_encoder, auto_tune, auto_tune_active)
                     -> list[str]
  emit_output(lines, header_lines) -> None
"""
import json
import sys


def build_header_lines(
    g1_header: str,
    g2_files: list,
    g2_keywords: list,
    vec_sock,
    vec_disabled: bool,
    bge_sock,
    use_cross_encoder: bool,
    auto_tune: dict,
    auto_tune_active: bool,
) -> list:
    """Build the forced-display header block prepended to injection output."""
    header_lines = []
    if g1_header:
        header_lines.append(g1_header)
    if g2_files or g2_keywords:
        files_str = ", ".join(f"`{f}`" for f in g2_files[:3]) if g2_files else "(docs BM25)"
        kw_str = " ".join(g2_keywords[:3]) if g2_keywords else ""
        via_str = f' — found via "{kw_str}"' if kw_str else ""
        header_lines.append(f"> **G2** (space search): {files_str}{via_str}")
    # Daemon degradation warnings
    daemon_warns = []
    if not vec_disabled and not vec_sock.exists():
        daemon_warns.append("vec-daemon down — BM25-only mode (semantic rerank disabled)")
    if use_cross_encoder and not bge_sock.exists():
        daemon_warns.append("bge-daemon down — cross-encoder rerank disabled")
    if daemon_warns:
        header_lines.append("> **⚠ Semantic layer**: " + " | ".join(daemon_warns))
    # Auto-tune active badge
    if auto_tune_active:
        n_rec = auto_tune.get("based_on_n", "?")
        prefer_hybrid = auto_tune.get("prefer_hybrid_G1", False)
        temporal_gap = auto_tune.get("temporal_utility_gap")
        proj_hint = auto_tune.get("project_type_hint")
        proj_conf = auto_tune.get("project_type_confidence", "LOW")
        parts = [f"n={n_rec}"]
        if prefer_hybrid:
            parts.append("hybrid✓")
        if temporal_gap and temporal_gap > 0.05:
            parts.append(f"temporal-gap={temporal_gap*100:.0f}pp")
        if proj_hint and proj_hint != "multi_lang" and proj_conf in ("HIGH", "MEDIUM"):
            parts.append(proj_hint)
        header_lines.append(
            f"> **CTX auto-tune** [{', '.join(parts)}] — run `ctx-telemetry tune` to refresh"
        )
    return header_lines


def emit_output(lines: list, header_lines: list) -> None:
    """Emit hook output to stdout + header summary to stderr."""
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
