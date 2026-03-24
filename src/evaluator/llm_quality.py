"""
LLM Downstream Quality Evaluator for CTX experiment.

Measures pass@1 using actual LLM API calls (MiniMax M2.5):
1. Sample functions from a real codebase
2. For each function, provide context via different retrieval strategies
3. Ask LLM to generate the function body
4. Use LLM self-evaluation to judge correctness (YES/NO)

This addresses the limitation noted in the paper: "we do not measure
downstream LLM generation quality (e.g., pass@1 on code tasks)."
"""

import ast
import json
import os
import random
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

from openai import OpenAI

from src.retrieval.full_context import RetrievalResult, estimate_tokens


@dataclass
class FunctionSample:
    """A function extracted from the codebase for evaluation."""
    file_path: str        # relative path within codebase
    name: str             # function name
    docstring: str        # function docstring (or empty)
    signature: str        # full def line
    body: str             # function body (source code)
    full_source: str      # entire function source including def line


@dataclass
class GenerationResult:
    """Result of a single code generation attempt."""
    function_name: str
    strategy: str
    prompt: str
    context_tokens: int
    generated_code: str
    reference_code: str
    passed: bool
    eval_response: str
    error: Optional[str] = None


@dataclass
class LLMQualityResult:
    """Aggregated LLM quality evaluation results."""
    model: str
    n_samples: int
    project: str
    strategies: Dict[str, Dict] = field(default_factory=dict)
    per_sample: List[Dict] = field(default_factory=list)
    timestamp: str = ""


class LLMQualityEvaluator:
    """Evaluates downstream code generation quality using LLM API calls."""

    def __init__(self, max_retries: int = 1):
        self.client = OpenAI(
            api_key=os.environ["MINIMAX_API_KEY"],
            base_url=os.environ["MINIMAX_BASE_URL"],
        )
        self.model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
        self.max_retries = max_retries

    def _strip_thinking(self, text: str) -> str:
        """Remove MiniMax M2.5 <think>...</think> tags."""
        return re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()

    def generate_code(self, task_prompt: str, context: str) -> str:
        """Generate code given a task prompt and context.

        Args:
            task_prompt: Description of the function to implement
            context: Code context (other files/functions)

        Returns:
            Generated code string
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Python code completion assistant. "
                    "Generate only the function implementation (the def line "
                    "and body). Do not include explanations, markdown, or "
                    "anything other than Python code."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Here is the codebase context:\n\n{context}\n\n"
                    f"---\n\nTask: {task_prompt}\n\n"
                    f"Generate the Python function:"
                ),
            },
        ]

        for attempt in range(1 + self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=800,
                    temperature=0.0,
                )
                raw = response.choices[0].message.content or ""
                return self._strip_thinking(raw)
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(2)
                    continue
                raise

    def evaluate_pass(
        self, generated: str, reference: str, task_desc: str
    ) -> Tuple[bool, str]:
        """Judge whether generated code correctly implements the task.

        Uses LLM self-evaluation (YES/NO).

        Args:
            generated: The generated code
            reference: The reference (ground-truth) code
            task_desc: Description of the task

        Returns:
            Tuple of (passed: bool, raw_response: str)
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a code correctness evaluator. Compare the "
                    "generated code against the reference implementation. "
                    "Judge whether the generated code correctly implements "
                    "the core logic described in the task. Minor style "
                    "differences (variable names, comments, import order) "
                    "are acceptable. Answer only YES or NO."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Task: {task_desc}\n\n"
                    f"--- Generated Code ---\n{generated}\n\n"
                    f"--- Reference Code ---\n{reference}\n\n"
                    f"Does the generated code correctly implement the task? "
                    f"(YES/NO)"
                ),
            },
        ]

        for attempt in range(1 + self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=20,
                    temperature=0.0,
                )
                raw = response.choices[0].message.content or ""
                cleaned = self._strip_thinking(raw).upper()
                passed = "YES" in cleaned
                return passed, raw
            except Exception as e:
                if attempt < self.max_retries:
                    time.sleep(2)
                    continue
                return False, f"ERROR: {e}"


def extract_functions_from_file(
    file_path: str, rel_path: str, min_body_lines: int = 3
) -> List[FunctionSample]:
    """Extract function definitions from a Python file.

    Filters for functions with:
    - At least min_body_lines lines in the body
    - A docstring or descriptive name
    - Not private (no leading underscore, except __init__)

    Args:
        file_path: Absolute path to the Python file
        rel_path: Relative path within the codebase
        min_body_lines: Minimum body lines to qualify

    Returns:
        List of FunctionSample objects
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, FileNotFoundError):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines()
    functions = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        name = node.name
        # Skip private functions (keep __init__ and public ones)
        if name.startswith("_") and name != "__init__":
            continue

        # Get docstring
        docstring = ast.get_docstring(node) or ""

        # Skip if no docstring and name is too short to be descriptive
        if not docstring and len(name) < 5:
            continue

        # Get source lines
        start_line = node.lineno - 1  # 0-indexed
        end_line = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start_line + 1
        func_lines = lines[start_line:end_line]
        full_source = "\n".join(func_lines)

        # Build signature (first line)
        signature = func_lines[0] if func_lines else f"def {name}():"

        # Body = everything after the def line
        body = "\n".join(func_lines[1:])
        body_line_count = len([l for l in func_lines[1:] if l.strip()])

        if body_line_count < min_body_lines:
            continue

        functions.append(FunctionSample(
            file_path=rel_path,
            name=name,
            docstring=docstring,
            signature=signature,
            body=body,
            full_source=full_source,
        ))

    return functions


def sample_functions(
    project_path: str, n: int = 15, seed: int = 42
) -> List[FunctionSample]:
    """Sample n functions from a Python project for evaluation.

    Prioritizes functions with docstrings and non-trivial bodies.

    Args:
        project_path: Root path of the Python project
        n: Number of functions to sample
        seed: Random seed for reproducibility

    Returns:
        List of FunctionSample objects
    """
    all_functions: List[FunctionSample] = []

    for root, _, filenames in os.walk(project_path):
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, project_path)
            funcs = extract_functions_from_file(fpath, rel_path)
            all_functions.extend(funcs)

    # Prioritize functions with docstrings
    with_doc = [f for f in all_functions if f.docstring]
    without_doc = [f for f in all_functions if not f.docstring]

    rng = random.Random(seed)
    rng.shuffle(with_doc)
    rng.shuffle(without_doc)

    # Take from docstring-having functions first
    sampled = with_doc[:n]
    if len(sampled) < n:
        sampled.extend(without_doc[:n - len(sampled)])

    return sampled[:n]


def build_full_context(project_path: str, max_tokens: int = 4000) -> str:
    """Build a full-context string from the project, truncated to max_tokens.

    Args:
        project_path: Root path of the Python project
        max_tokens: Approximate token budget

    Returns:
        Concatenated source code string
    """
    parts = []
    total_chars = 0
    char_budget = max_tokens * 4  # ~4 chars per token

    for root, _, filenames in os.walk(project_path):
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, project_path)
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except (OSError, FileNotFoundError):
                continue

            header = f"# === {rel_path} ===\n"
            chunk = header + content + "\n\n"

            if total_chars + len(chunk) > char_budget:
                remaining = char_budget - total_chars
                if remaining > 200:
                    parts.append(chunk[:remaining] + "\n# ... truncated")
                break

            parts.append(chunk)
            total_chars += len(chunk)

    return "".join(parts)


def build_adaptive_context(
    project_path: str,
    func: FunctionSample,
    max_tokens: int = 2000,
) -> str:
    """Build adaptive-trigger context for a function generation task.

    Uses the CTX adaptive trigger retriever to select relevant files.

    Args:
        project_path: Root path of the Python project
        func: The function being evaluated
        max_tokens: Approximate token budget

    Returns:
        Retrieved context string
    """
    from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

    retriever = AdaptiveTriggerRetriever(project_path)
    query_text = f"Implement function '{func.name}'"
    if func.docstring:
        query_text += f": {func.docstring[:200]}"

    result = retriever.retrieve(
        query_id=f"llm_eval_{func.name}",
        query_text=query_text,
        k=5,
    )

    parts = []
    total_chars = 0
    char_budget = max_tokens * 4

    for rel_path in result.retrieved_files:
        fpath = os.path.join(project_path, rel_path)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except (OSError, FileNotFoundError):
            continue

        header = f"# === {rel_path} ===\n"
        chunk = header + content + "\n\n"

        if total_chars + len(chunk) > char_budget:
            remaining = char_budget - total_chars
            if remaining > 200:
                parts.append(chunk[:remaining] + "\n# ... truncated")
            break

        parts.append(chunk)
        total_chars += len(chunk)

    return "".join(parts)
