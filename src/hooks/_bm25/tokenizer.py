"""
tokenizer.py — BM25 tokenizer for bm25-memory.

Provides:
  tokenize(text, drop_stopwords=False) -> list[str]
  expand_query_tokens(query_tokens) -> list[str]

Korean particle stripping + Porter stemmer (opt-in via CTX_STEM=1, default ON).
Synonym expansion bridges Korean<->English lexical gaps.
"""
import os
import re

# ── Korean particle stripper ─────────────────────────────────────────────────

_KO_PARTICLES = re.compile(
    r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$'
)

# Conversational stopwords — filtered from QUERIES only (not the corpus).
# These appear in nearly every conversational prompt and make BM25 return
# noise matches on common words instead of real topic terms.
# Kept conservative — only words that are almost never content-bearing in
# a software-engineering commit subject.
_STOPWORDS = frozenset([
    # English function words
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "am", "do", "does", "did", "have", "has", "had", "will", "would",
    "could", "should", "may", "might", "can", "to", "of", "in", "on",
    "at", "by", "for", "with", "from", "as", "into", "about",
    "and", "or", "but", "if", "then", "than", "so", "not", "no",
    "i", "you", "we", "he", "she", "it", "they", "me", "my", "your",
    "our", "his", "her", "their", "this", "that", "these", "those",
    "there", "here", "what", "which", "when", "where", "why", "how",
    "who", "whom", "some", "any", "all", "each", "every", "both",
    "more", "most", "less", "few", "much", "many",
    "just", "only", "very", "too", "also", "even", "still", "yet",
    "now", "then", "up", "down", "out", "over", "again",
    # Conversational fillers
    "ok", "yeah", "yep", "pls", "please", "thanks", "thank",
    "hi", "hey", "hello", "want", "like", "think", "need",
    "make", "use", "using", "try", "trying", "get", "got",
    # Korean fillers (particles already stripped; these are standalone)
    "음", "어", "아", "그", "저", "이거", "저거", "그거",
])

# Small Korean-English synonym map for query expansion (Layer 2).
# Keys are case-folded. Additions expand the query token set — BM25 will match
# commits mentioning either side of each pair. Focused on CTX domain vocabulary
# that commonly appears in Korean prompts but English commits (and vice versa).
_SYNONYM_EXPANSION = {
    "cross-session":   ["long-term", "persistent", "inter-session", "장기기억"],
    "long-term":       ["cross-session", "persistent", "장기", "장기기억"],
    "memory":          ["recall", "retrieval", "기억"],
    "retrieval":       ["search", "recall", "fetch", "검색", "조회"],
    "search":          ["retrieval", "lookup", "검색"],
    "hook":            ["plugin", "extension", "훅"],
    "embed":           ["embedding", "vector", "임베딩"],
    "embedding":       ["embed", "vector", "임베딩"],
    "rerank":          ["rank", "reorder", "재정렬", "순위"],
    "semantic":        ["vector", "dense", "의미"],
    "context":         ["memory", "state", "컨텍스트"],
    "prompt":          ["query", "question", "프롬프트"],
    "improve":         ["enhance", "boost", "optimize", "개선", "향상"],
    "quality":         ["accuracy", "score", "품질"],
    "noise":           ["garbage", "irrelevant", "노이즈"],
    "cluster":         ["group", "dedup", "중복"],
    "dashboard":       ["ui", "visualization", "대시보드"],
    "bootstrap":       ["install", "setup", "부트스트랩"],
    "gpu":             ["cuda", "device", "가속"],
    "claude":          ["anthropic", "llm"],
    "korean":          ["한국어", "ko", "hangul"],
    "기억":             ["memory", "recall"],
    "검색":             ["search", "retrieval"],
    "장기기억":          ["long-term memory", "cross-session", "persistent"],
    "의사결정":          ["decision", "choice"],
    "훅":               ["hook", "plugin"],
    "임베딩":            ["embedding", "vector"],
}

# ── Porter stemmer ───────────────────────────────────────────────────────────
# opt-in via CTX_STEM=1, default ON 2026-04-24 after G1 regression showed +0.034
# improvement on Recall@7 with zero losses.
_USE_STEMMER = os.environ.get("CTX_STEM", "1") != "0"
_STEMMER = None
if _USE_STEMMER:
    try:
        from nltk.stem.porter import PorterStemmer as _PS
        _STEMMER = _PS()
    except ImportError:
        _STEMMER = None   # stemming silently disabled if nltk not installed


def tokenize(text: str, drop_stopwords: bool = False):
    """Preserve decimal numbers (0.724) and numeric ranges (7-30) as single tokens.
    Also strips Korean particles from mixed Korean-ASCII tokens (e.g. 'BM25와' → 'bm25' + 'bm25와')
    so that Korean queries match English commit subjects correctly.

    When `drop_stopwords=True` (query-side only), conversational fillers are
    removed to prevent BM25 from matching on common words like "i", "to", "how",
    "would", etc. Corpus tokenization never drops stopwords — IDF handles those.

    Porter stemmer (2026-04-24): adds stemmed variant for each token so "logs"
    matches "logging". Preserves the original token too so exact-match precision
    is never lost (dedup handles duplicates). Opt-out via CTX_STEM=0.
    """
    raw = re.findall(r'\d+[-–]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        if drop_stopwords and tok in _STOPWORDS:
            continue
        cleaned = _KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            if not (drop_stopwords and cleaned in _STOPWORDS):
                result.append(cleaned)
        result.append(tok)
        # Porter stem — adds a THIRD variant. Dedup at return preserves order
        # so original tokens remain ranked; stem is a recall-rescue fallback.
        if _STEMMER is not None and tok.isalpha() and len(tok) > 3:
            stemmed = _STEMMER.stem(tok)
            if stemmed != tok:
                result.append(stemmed)
    return list(dict.fromkeys(result))


def expand_query_tokens(query_tokens):
    """Layer 2: bridge Korean<->English lexical gaps via synonym map.
    Returns the original tokens + synonym expansions (capped at 2x length)."""
    out = list(query_tokens)
    for t in query_tokens:
        syns = _SYNONYM_EXPANSION.get(t.lower())
        if syns:
            out.extend(syns)
    # Dedupe while preserving order
    seen = set(); uniq = []
    for t in out:
        k = t.lower()
        if k not in seen:
            seen.add(k); uniq.append(t)
    return uniq[:len(query_tokens) * 2 + 5]   # cap growth
