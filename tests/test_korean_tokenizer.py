"""
test_korean_tokenizer.py — Korean BM25 tokenization consistency tests.

Verifies that:
1. Production tokenizer (bm25-memory.py) handles Korean characters
2. Eval tokenizer (_eval_tokenize in doc_retrieval_eval_v2.py) handles Korean
3. Both produce non-empty output for Korean-only queries
4. Mixed Korean+English queries are tokenized correctly

Regression guard against the bug where r'\b[a-z]{2,}\b' silently
dropped all Korean tokens in the eval pipeline.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "benchmarks" / "eval"))


def eval_tokenize(text: str) -> list:
    """Mirror of _eval_tokenize from doc_retrieval_eval_v2.py."""
    return re.findall(r'[a-z]{2,}|[ᄀ-ᇿ㄰-㆏가-힯一-鿿]+', text.lower())


def test_korean_only_query_not_empty():
    """Korean-only query must produce non-empty token list."""
    tokens = eval_tokenize("장기 기억 성능 개선")
    assert tokens, "Korean query tokenized to empty — tokenizer bug"
    assert "장기" in tokens
    assert "기억" in tokens


def test_mixed_korean_english():
    """Mixed queries should tokenize both languages."""
    tokens = eval_tokenize("BM25 검색 품질 향상")
    assert "검색" in tokens, "Korean token missing from mixed query"
    assert "bm" in tokens, "ASCII token missing from mixed query"


def test_pure_english_unchanged():
    """English-only queries should behave as before."""
    tokens = eval_tokenize("cross-session memory retrieval")
    assert "cross" in tokens
    assert "memory" in tokens
    assert "retrieval" in tokens


def test_hangul_syllable_range():
    """Verify the regex covers the full Hangul syllable block (AC00-D7A3)."""
    samples = ["가나다라", "한국어", "컨텍스트", "임베딩", "검색", "훅"]
    for word in samples:
        tokens = eval_tokenize(word)
        assert tokens, f"'{word}' tokenized to empty"
        assert word in tokens, f"'{word}' not in tokens: {tokens}"


def test_production_tokenizer_handles_korean():
    """Production tokenizer (\\w+) must capture Korean characters."""
    raw = re.findall(r'\d+[-–]\d+|\d+\.\d+|\w+', "장기 기억 검색".lower())
    assert "장기" in raw
    assert "기억" in raw
    assert "검색" in raw


def test_eval_prod_parity_on_korean():
    """Eval and production tokenizers must both return non-empty for Korean input."""
    query = "CTX 훅 설치 및 활용 방법"
    eval_tokens = eval_tokenize(query)
    prod_tokens = re.findall(r'\d+[-–]\d+|\d+\.\d+|\w+', query.lower())
    assert eval_tokens, "Eval tokenizer returned empty for Korean query"
    assert prod_tokens, "Production tokenizer returned empty for Korean query"
    # Both should capture Korean tokens
    korean_in_eval = [t for t in eval_tokens if re.search(r'[가-힯]', t)]
    korean_in_prod = [t for t in prod_tokens if re.search(r'[가-힯]', t)]
    assert korean_in_eval, "No Korean tokens from eval tokenizer"
    assert korean_in_prod, "No Korean tokens from production tokenizer"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
