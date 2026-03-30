"""
Tests for AST-based improvements in CTX:
- _index_symbols(): AST symbol extraction
- _index_imports(): AST import extraction
- context_selector: signature-only extraction
"""

import sys
import os
import textwrap

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
from src.retrieval.context_selector import extract_signatures, load_signature_context


# ── AdaptiveTriggerRetriever fixture ──────────────────────────────────────────

@pytest.fixture(scope="module")
def retriever(tmp_path_factory):
    """Create a small fake codebase for indexing."""
    base = tmp_path_factory.mktemp("codebase")

    (base / "module_a.py").write_text(textwrap.dedent("""
        '''Module A — document retrieval.'''
        from module_b import helper

        class Retriever:
            '''Retrieves documents.'''
            def search(self, query: str) -> list:
                '''Search for documents.'''
                return []

            @staticmethod
            def _normalize(text: str) -> str:
                return text.lower()

        async def fetch_async(url: str) -> bytes:
            '''Async fetch.'''
            return b""
    """))

    (base / "module_b.py").write_text(textwrap.dedent("""
        '''Module B — helpers.'''

        def helper(x):
            return x

        class lowercase_class:
            '''Lowercase class name.'''
            pass
    """))

    return AdaptiveTriggerRetriever(str(base))


# ── Symbol index tests ────────────────────────────────────────────────────────

class TestASTSymbolIndex:
    def test_class_indexed(self, retriever):
        assert "Retriever" in retriever.symbol_index

    def test_method_indexed(self, retriever):
        """Methods inside classes should be indexed (regex would miss with MULTILINE)."""
        assert "search" in retriever.symbol_index

    def test_static_method_indexed(self, retriever):
        assert "_normalize" in retriever.symbol_index

    def test_async_function_indexed(self, retriever):
        """async def should be indexed."""
        assert "fetch_async" in retriever.symbol_index

    def test_lowercase_class_indexed(self, retriever):
        """Lowercase class names should be indexed (old regex missed these)."""
        assert "lowercase_class" in retriever.symbol_index

    def test_symbol_points_to_correct_file(self, retriever):
        assert any("module_a" in f for f in retriever.symbol_index.get("Retriever", []))

    def test_helper_in_module_b(self, retriever):
        assert any("module_b" in f for f in retriever.symbol_index.get("helper", []))


# ── Import graph tests ────────────────────────────────────────────────────────

class TestASTImportIndex:
    def test_import_graph_built(self, retriever):
        assert len(retriever.import_graph) >= 2

    def test_module_a_imports_module_b(self, retriever):
        """from module_b import helper → module_a should have module_b in imports."""
        imports_a = [
            imports
            for path, imports in retriever.import_graph.items()
            if "module_a" in path
        ]
        assert imports_a, "module_a not in import graph"
        assert "module_b" in imports_a[0]


# ── Signature extraction tests ────────────────────────────────────────────────

class TestExtractSignatures:
    def test_class_signature_present(self):
        code = textwrap.dedent("""
            class Foo:
                '''A foo class.'''
                def bar(self, x: int) -> str:
                    '''Does bar.'''
                    return str(x)
        """)
        result = extract_signatures(code)
        assert "class Foo:" in result
        assert "def bar" in result

    def test_body_not_present(self):
        code = textwrap.dedent("""
            def compute(x: int) -> int:
                '''Compute something.'''
                result = x * 2
                return result
        """)
        result = extract_signatures(code)
        assert "result = x * 2" not in result
        assert "return result" not in result

    def test_docstring_first_line_present(self):
        code = textwrap.dedent("""
            def foo():
                '''Does foo things. More details here.'''
                pass
        """)
        result = extract_signatures(code)
        assert "Does foo things." in result

    def test_ellipsis_placeholder(self):
        code = "def bar(): pass"
        result = extract_signatures(code)
        assert "..." in result

    def test_max_chars_truncation(self):
        code = "\n".join(f"def func_{i}(): pass" for i in range(100))
        result = extract_signatures(code, max_chars=200)
        assert len(result) <= 200

    def test_syntax_error_fallback(self):
        """Invalid Python should return partial content, not raise."""
        code = "def foo( :\n    pass"
        result = extract_signatures(code)
        assert isinstance(result, str)

    def test_async_function(self):
        code = "async def my_coroutine(x: int) -> None:\n    pass"
        result = extract_signatures(code)
        assert "my_coroutine" in result


class TestLoadSignatureContext:
    def test_returns_string(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo(): pass")
        result = load_signature_context("test.py", root=tmp_path)
        assert isinstance(result, str)
        assert "signatures only" in result

    def test_missing_file(self, tmp_path):
        result = load_signature_context("nonexistent.py", root=tmp_path)
        assert "FILE NOT FOUND" in result

    def test_non_python_file(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("key: value\n")
        result = load_signature_context("config.yaml", root=tmp_path)
        assert "config.yaml" in result
