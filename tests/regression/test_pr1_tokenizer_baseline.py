"""
PR-1 baseline: canonical _bm25.tokenize 와 4개 eval 사이트의 tokenize 결과 비교.

발행 전: 4 사이트 모두 자체 정의 → delta 측정
발행 후: 4 사이트 모두 canonical 호출 → 동일 (delta=0 또는 명시된 augmentation)
"""
import sys, re
sys.path.insert(0, '/Users/d9ng/privateProject/tunaCtx')
sys.path.insert(0, '/Users/d9ng/privateProject/tunaCtx/src/hooks')
from _bm25.tokenizer import tokenize as canonical_tokenize


SAMPLE_CORPUS = [
    "BM25 retrieval improves Recall@7 from 0.169 to 0.634 — 3.7x improvement.",
    "한국어 토크나이저는 조사 분리(은/는/이/가/을/를)를 수행한다",
    "iter 11 final R@5=0.595 (Flask 0.6462 / FastAPI 0.3870 / Requests 0.7526)",
    "fix(hooks): Windows TCP loopback fallback for AF_UNIX-less CPython",
    "decomposing bm25-memory.py into 11 sub-modules with 82 unit tests",
]
SAMPLE_QUERIES = [
    "BM25 recall improvement",
    "한국어 검색 개선",
    "Windows fallback hook",
]

def site_g1_docs(text):
    """Original tokenize from benchmarks/eval/g1_docs_bm25_eval.py:78"""
    tokens = re.findall(r'\d+[-–]\d+|\d+\.\d+|\w+', text.lower())
    return [t for t in tokens if t]

def site_g1_longterm(text):
    """Original nested tokenize from g1_longterm_baseline_eval.py:267"""
    return re.findall(r'\b\w+\b', text.lower())

KO_PARTICLES = re.compile(r'(와|과|이|가|은|는|을|를|의|에서|으로|에게|부터|까지|처럼|같이|보다|이나|며|에|로|도|만|나|고)$')
def site_g2_paraphrase(text):
    """Original tokenize from g2_docs_paraphrase_eval.py:325"""
    raw = re.findall(r'\d+[-–]\d+|\d+\.\d+|\w+', text.lower())
    result = []
    for tok in raw:
        cleaned = KO_PARTICLES.sub('', tok)
        if cleaned and cleaned != tok:
            result.append(cleaned)
        result.append(tok)
    return list(dict.fromkeys(result))

def site_bm25_retriever(text):
    """Original from src/retrieval/bm25_retriever.py:16 — identifier-only"""
    raw = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', text.lower())
    return [t for t in raw if len(t) > 1]

def compare(name, fn, drop_stopwords=False):
    """Compare site fn vs canonical."""
    diffs = 0
    additions = 0  # canonical produces more tokens (e.g. stem)
    losses = 0     # canonical produces fewer tokens
    for text in SAMPLE_CORPUS + SAMPLE_QUERIES:
        site_tokens = set(fn(text))
        canon_tokens = set(canonical_tokenize(text, drop_stopwords=drop_stopwords))
        if site_tokens != canon_tokens:
            diffs += 1
            additions += len(canon_tokens - site_tokens)
            losses += len(site_tokens - canon_tokens)
    print(f"  {name}: {diffs}/{len(SAMPLE_CORPUS)+len(SAMPLE_QUERIES)} samples differ | canonical_adds={additions}, canonical_loses={losses}")

print("=== PR-1 baseline: site vs canonical tokenize delta ===\n")
print("[g1_docs_bm25_eval.py:78 vs canonical]")
compare("g1_docs", site_g1_docs)
print("\n[g1_longterm_baseline_eval.py:267 vs canonical]")
compare("g1_longterm", site_g1_longterm)
print("\n[g2_docs_paraphrase_eval.py:325 vs canonical]")
compare("g2_paraphrase", site_g2_paraphrase)
print("\n[bm25_retriever.py:16 vs canonical (identifier post-filter)]")
def canonical_id_filtered(text):
    # canonical + identifier post-filter (keep tokens matching identifier shape, len>1)
    return [t for t in canonical_tokenize(text, drop_stopwords=False) if re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_]*', t) and len(t) > 1]
diffs = 0
for text in SAMPLE_CORPUS:
    site = set(site_bm25_retriever(text))
    canon = set(canonical_id_filtered(text))
    if site != canon:
        diffs += 1
        miss = site - canon; add = canon - site
        if miss or add:
            print(f"    sample: site_only={list(miss)[:5]}, canonical_only={list(add)[:5]}")
print(f"  bm25_retriever: {diffs}/{len(SAMPLE_CORPUS)} samples differ from canonical+id-filter")

print("\n=== Baseline complete ===")
