"""
Context Selector — Signature-Only Extraction for Over-Anchoring Prevention

Problem: providing full file content causes LLMs to anchor on the current
implementation rather than applying the desired fix (20% reverse-effect rate).

Solution: extract only function/class signatures + docstrings, omitting bodies.
This preserves the API surface (what's available) without exposing implementation
details (what might need to change).
"""

import ast
import textwrap
from pathlib import Path
from typing import List, Optional


def extract_signatures(source: str, max_chars: int = 2000) -> str:
    """
    Extract function/class signatures and one-line docstrings from Python source.

    Returns a compact API surface without implementation bodies:
      def foo(x: int, y: str = "bar") -> bool:
          '''Does foo-like things.'''
          ...

      class Bar:
          '''Represents a bar.'''
          def baz(self) -> None: ...
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Fall back to first N lines on parse failure
        return "\n".join(source.splitlines()[:40])

    lines = []
    _collect_sigs(tree.body, lines, indent=0)
    result = "\n".join(lines)
    return result[:max_chars] if len(result) > max_chars else result


def _collect_sigs(stmts: list, lines: List[str], indent: int) -> None:
    pad = "    " * indent
    for node in stmts:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig = _format_func_sig(node, pad)
            lines.append(sig)
            doc = ast.get_docstring(node)
            if doc:
                first_line = doc.splitlines()[0].strip()
                lines.append(f"{pad}    '''{first_line}'''")
            lines.append(f"{pad}    ...")
            lines.append("")

        elif isinstance(node, ast.ClassDef):
            bases = ", ".join(ast.unparse(b) for b in node.bases) if node.bases else ""
            lines.append(f"{pad}class {node.name}({bases}):" if bases else f"{pad}class {node.name}:")
            doc = ast.get_docstring(node)
            if doc:
                first_line = doc.splitlines()[0].strip()
                lines.append(f"{pad}    '''{first_line}'''")
            # Recurse into class body (methods only)
            _collect_sigs(node.body, lines, indent + 1)
            lines.append("")


def _format_func_sig(node: ast.FunctionDef, pad: str) -> str:
    """Format function signature with type annotations."""
    try:
        # ast.unparse reconstructs the signature from the AST
        sig_line = ast.unparse(node)
        # Take only the def line (before the body)
        first_line = sig_line.splitlines()[0]
        # Remove trailing colon + body
        return f"{pad}{first_line.rstrip(':')}:"
    except Exception:
        return f"{pad}def {node.name}(...):"


def load_signature_context(
    filepath: str,
    root: Optional[Path] = None,
    max_chars: int = 2000,
) -> str:
    """
    Load a file and return only its API signature surface.

    Use instead of load_file_snippet() when the LLM should understand
    what a file *contains* without being anchored to its current implementation.

    Args:
        filepath: relative or absolute path to a .py file
        root: project root for relative paths (default: cwd)
        max_chars: max characters in output

    Returns:
        Formatted signature block with header comment
    """
    if root is None:
        root = Path.cwd()

    full_path = Path(root) / filepath if not Path(filepath).is_absolute() else Path(filepath)

    if not full_path.exists():
        return f"# [FILE NOT FOUND: {filepath}]"

    source = full_path.read_text(encoding="utf-8", errors="replace")

    if not filepath.endswith(".py"):
        # Non-Python: return truncated content
        lines = source.splitlines()[:40]
        return f"# File: {filepath} (first {len(lines)} lines)\n" + "\n".join(lines)

    sigs = extract_signatures(source, max_chars=max_chars)
    return f"# File: {filepath} [signatures only]\n```python\n{sigs}\n```"


def load_diverse_context(
    retrieved_files: List[str],
    root: Optional[Path] = None,
    max_files: int = 4,
    sig_only: bool = True,
    max_chars_per_file: int = 1500,
) -> str:
    """
    Load diverse context from multiple retrieved files to reduce over-anchoring.

    Instead of one file with full content, provides N files with signatures,
    giving the LLM a broader view of available APIs.

    Args:
        retrieved_files: list of file paths (typically from CTX retrieval)
        root: project root
        max_files: max files to include (default: 4)
        sig_only: if True, extract signatures only (recommended for Fix/Replace tasks)
        max_chars_per_file: max chars per file snippet

    Returns:
        Multi-file context block
    """
    if root is None:
        root = Path.cwd()

    blocks = []
    for fp in retrieved_files[:max_files]:
        if sig_only and fp.endswith(".py"):
            block = load_signature_context(fp, root=root, max_chars=max_chars_per_file)
        else:
            full_path = Path(root) / fp
            if not full_path.exists():
                continue
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            snippet = "\n".join(lines[:50])
            block = f"# File: {fp}\n```python\n{snippet}\n```"
        blocks.append(block)

    return "\n\n".join(blocks)
