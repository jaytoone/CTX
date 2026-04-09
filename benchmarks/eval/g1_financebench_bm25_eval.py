#!/usr/bin/env python3
"""
FinanceBench — BM25 vs PageIndex comparison
============================================
Tests BM25 retrieval on the FinanceBench benchmark where PageIndex claims 98.7% accuracy.

Run:
  cd /home/jayone/Project/CTX
  source ~/.claude/env/shared.env
  python3 benchmarks/eval/g1_financebench_bm25_eval.py 2>&1
"""

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not found. pip install anthropic")
    sys.exit(1)

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    print("ERROR: rank_bm25 not found. pip install rank-bm25")
    sys.exit(1)

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ──────────────────────────────────────────────────────────────────────────────
# Step 1: Load FinanceBench dataset
# ──────────────────────────────────────────────────────────────────────────────

FALLBACK_QA = [
    {
        "question": "What was 3M's total net revenue for fiscal year 2022?",
        "answer": "$35.4 billion",
        "evidence": "3M Company reported total net revenue of $35.4 billion for fiscal year 2022, compared to $35.4 billion in 2021. The company's net sales declined slightly driven by currency headwinds and divestitures.",
        "doc_name": "3M_2022_10K",
    },
    {
        "question": "What was Apple's net income in fiscal year 2022?",
        "answer": "$99.8 billion",
        "evidence": "Apple Inc. reported net income of $99.8 billion for fiscal year 2022, up from $94.7 billion in fiscal year 2021. Earnings per diluted share were $6.11, compared to $5.61 in 2021.",
        "doc_name": "AAPL_2022_10K",
    },
    {
        "question": "What was Microsoft's cloud revenue in fiscal year 2022?",
        "answer": "$91.2 billion",
        "evidence": "Microsoft reported total revenue of $198.3 billion in fiscal year 2022. Intelligent Cloud segment revenue was $75.3 billion. Commercial cloud revenue grew 32% year-over-year to $91.2 billion.",
        "doc_name": "MSFT_2022_10K",
    },
    {
        "question": "What was Amazon's operating income in 2022?",
        "answer": "$12.2 billion",
        "evidence": "Amazon reported operating income of $12.2 billion for 2022, compared to $24.9 billion in 2021. The decrease was primarily driven by increased fulfillment and transportation costs, as well as investments in AWS and other businesses.",
        "doc_name": "AMZN_2022_10K",
    },
    {
        "question": "What was Tesla's total revenue for fiscal year 2022?",
        "answer": "$81.5 billion",
        "evidence": "Tesla, Inc. reported total revenues of $81.5 billion for fiscal year 2022, representing an increase of 51% from $53.8 billion in fiscal year 2021. Automotive revenues were $71.5 billion, up 51% year-over-year.",
        "doc_name": "TSLA_2022_10K",
    },
    {
        "question": "What was Alphabet's advertising revenue for 2022?",
        "answer": "$224.5 billion",
        "evidence": "Alphabet Inc. reported total revenues of $282.8 billion for fiscal year 2022. Google Services revenues were $253.5 billion. Google advertising revenues totaled $224.5 billion, a decrease of 1% year-over-year.",
        "doc_name": "GOOGL_2022_10K",
    },
    {
        "question": "What dividend did Johnson & Johnson pay per share in 2022?",
        "answer": "$4.52 per share",
        "evidence": "Johnson & Johnson paid dividends of $4.52 per share in 2022, compared to $4.24 per share in 2021. The company has increased its dividend for 60 consecutive years, making it a Dividend King.",
        "doc_name": "JNJ_2022_10K",
    },
    {
        "question": "What was JPMorgan Chase's net income in 2022?",
        "answer": "$37.7 billion",
        "evidence": "JPMorgan Chase & Co. reported net income of $37.7 billion in 2022, compared to $48.3 billion in 2021. Net revenue was $128.7 billion. Return on common equity was 13% for the year.",
        "doc_name": "JPM_2022_10K",
    },
    {
        "question": "What was Walmart's total revenue for fiscal year 2023?",
        "answer": "$611.3 billion",
        "evidence": "Walmart Inc. reported net revenues of $611.3 billion for fiscal year 2023, which ended January 31, 2023. This represented an increase of approximately 6.7% from $572.8 billion in fiscal year 2022.",
        "doc_name": "WMT_FY2023_10K",
    },
    {
        "question": "What was ExxonMobil's capital expenditures in 2022?",
        "answer": "$21.0 billion",
        "evidence": "ExxonMobil Corporation reported capital and exploration expenditures of $21.0 billion in 2022, compared to $16.6 billion in 2021. The increase reflects higher spending on the Permian Basin and Guyana operations as oil demand recovered.",
        "doc_name": "XOM_2022_10K",
    },
    {
        "question": "What was Berkshire Hathaway's operating earnings in 2022?",
        "answer": "$28.7 billion",
        "evidence": "Berkshire Hathaway reported operating earnings of $28.7 billion in 2022, compared to $27.5 billion in 2021. Warren Buffett emphasized that operating earnings are more meaningful than net earnings, which include investment gains and losses.",
        "doc_name": "BRK_2022_10K",
    },
    {
        "question": "What was Pfizer's revenue from COVID-19 products in 2022?",
        "answer": "$56.7 billion",
        "evidence": "Pfizer Inc. reported total revenues of $100.3 billion in 2022. COVID-19 product revenues were $56.7 billion, including $37.8 billion from Comirnaty (vaccine) and $18.9 billion from Paxlovid (antiviral treatment).",
        "doc_name": "PFE_2022_10K",
    },
    {
        "question": "What was Chevron's return on capital employed in 2022?",
        "answer": "21%",
        "evidence": "Chevron Corporation reported return on capital employed (ROCE) of 21% for fiscal year 2022, compared to 10% in 2021. The improvement was driven by higher crude oil and natural gas prices, with Brent crude averaging approximately $99 per barrel.",
        "doc_name": "CVX_2022_10K",
    },
    {
        "question": "What was Visa's net income for fiscal year 2022?",
        "answer": "$14.9 billion",
        "evidence": "Visa Inc. reported net income of $14.9 billion for fiscal year 2022, which ended September 30, 2022. This represented an increase from $12.3 billion in fiscal year 2021. Net revenues grew 22% to $29.3 billion.",
        "doc_name": "V_FY2022_10K",
    },
    {
        "question": "What was Netflix's total streaming revenue in 2022?",
        "answer": "$31.6 billion",
        "evidence": "Netflix, Inc. reported total revenues of $31.6 billion in 2022, compared to $29.7 billion in 2021. The company ended 2022 with 231 million paid memberships worldwide, a slight decrease from 221.8 million at the start of the year due to password sharing crackdowns.",
        "doc_name": "NFLX_2022_10K",
    },
    {
        "question": "What was Bank of America's net interest income in 2022?",
        "answer": "$52.4 billion",
        "evidence": "Bank of America Corporation reported net interest income of $52.4 billion in 2022, a significant increase from $42.9 billion in 2021, driven by higher interest rates. Total revenue was $94.9 billion for the year.",
        "doc_name": "BAC_2022_10K",
    },
    {
        "question": "What was Nike's revenue for fiscal year 2022?",
        "answer": "$46.7 billion",
        "evidence": "NIKE, Inc. reported revenues of $46.7 billion for fiscal year 2022, which ended May 31, 2022. This represented a 5% increase from $44.5 billion in fiscal year 2021. Direct-to-consumer revenues grew 14% to $18.7 billion.",
        "doc_name": "NKE_FY2022_10K",
    },
    {
        "question": "What was Coca-Cola's organic revenue growth in 2022?",
        "answer": "11%",
        "evidence": "The Coca-Cola Company reported organic revenue (non-GAAP) growth of 11% in 2022. Net revenues grew 11% to $43.0 billion. Price/mix contributed 9 percentage points to organic revenue growth while concentrate sales contributed 2 percentage points.",
        "doc_name": "KO_2022_10K",
    },
    {
        "question": "What was Intel's data center and AI group revenue in 2022?",
        "answer": "$19.0 billion",
        "evidence": "Intel Corporation reported Data Center and AI (DCAI) segment revenue of $19.0 billion in 2022, a decrease of 16% from $22.7 billion in 2021. The decline was attributed to reduced enterprise and government spending and competitive pressure in the server CPU market.",
        "doc_name": "INTC_2022_10K",
    },
    {
        "question": "What was Goldman Sachs's net revenues in 2022?",
        "answer": "$47.4 billion",
        "evidence": "The Goldman Sachs Group, Inc. reported net revenues of $47.4 billion in 2022, compared to $59.3 billion in 2021. Global Banking & Markets revenues were $30.3 billion. Net earnings were $11.3 billion, or $30.06 per diluted share.",
        "doc_name": "GS_2022_10K",
    },
]


def load_financebench(n: int = 20) -> List[Dict[str, Any]]:
    """Try to load FinanceBench from HuggingFace; fall back to synthetic data."""
    print("Attempting to load FinanceBench from HuggingFace...")
    try:
        from datasets import load_dataset
        ds = load_dataset("PatronusAI/financebench", split="train", trust_remote_code=True)
        print(f"Loaded {len(ds)} items from HuggingFace FinanceBench")

        qa_pairs = []
        for item in ds:
            if len(qa_pairs) >= n:
                break

            # evidence is a dict: {'evidence_text': ..., 'doc_name': ..., 'page_num': ...}
            evidence = ""
            ev = item.get("evidence", None)
            if isinstance(ev, dict):
                evidence = ev.get("evidence_text", "")
            elif isinstance(ev, list):
                parts = []
                for e in ev:
                    if isinstance(e, dict):
                        parts.append(e.get("evidence_text", str(e)))
                    else:
                        parts.append(str(e))
                evidence = " ".join(parts)
            elif ev:
                evidence = str(ev)

            # Fallback: top-level evidence_text key
            if not evidence:
                evidence = str(item.get("evidence_text", ""))

            if not evidence:
                continue

            qa_pairs.append({
                "question": item.get("question", ""),
                "answer": str(item.get("answer", "")),
                "evidence": evidence,
                "doc_name": item.get("doc_name", item.get("company", "unknown")),
            })

        if qa_pairs:
            print(f"Using {len(qa_pairs)} QA pairs from HuggingFace")
            return qa_pairs
        else:
            print("No valid QA pairs extracted — falling back to synthetic data")
    except Exception as e:
        print(f"HuggingFace load failed: {e}")
        print("Falling back to synthetic FinanceBench-style QA pairs")

    pairs = FALLBACK_QA[:n]
    print(f"Using {len(pairs)} synthetic FinanceBench-style QA pairs")
    return pairs


# ──────────────────────────────────────────────────────────────────────────────
# Step 2: BM25 retrieval
# ──────────────────────────────────────────────────────────────────────────────

def tokenize(text: str) -> List[str]:
    """Financial-aware tokenizer: preserve numbers, dollar amounts, percentages."""
    tokens = re.findall(r'\$[\d,]+|\d+[-\u2013]\d+|\d+\.\d+|\d+%?|\w+', text.lower())
    return [t for t in tokens if t]


def extract_financial_core(question: str) -> str:
    """Remove instruction boilerplate from FinanceBench-style questions."""
    # FinanceBench prepends long instruction blocks before the actual question.
    # Pattern: "Give a response to the question ... [actual question]?"
    # Strategy: strip everything up to the last sentence that contains the real query.

    boilerplate_patterns = [
        # "Give a response to the question by relying on details ... [actual q]"
        r'^give\s+a\s+response\s+to\s+the\s+question\b.*?(?=\bwhat\b|\bwhen\b|\bhow\b|\bwhich\b|\bwho\b|\bwhere\b|\bwhy\b|\bis\b|\bdid\b|\bdoes\b)',
        # "by relying on details in the financial statements"
        r'by relying on details.*?(?=\bwhat\b|\bwhen\b|\bhow\b|\bwhich\b|\bwho\b|\bwhere\b|\bwhy\b|\bis\b|\bdid\b|\bdoes\b)',
        # "based on details found in"
        r'based on details found in.*?(?=\bwhat\b|\bwhen\b|\bhow\b|\bwhich\b|\bwho\b|\bwhere\b|\bwhy\b|\bis\b|\bdid\b|\bdoes\b)',
        # "using the financial statements"
        r'using the financial statements?\b[^.]*?\.?\s*',
        # "from the following report/filing/document"
        r'from the following (?:report|filing|document)[^.]*?\.?\s*',
    ]

    cleaned = question
    for pat in boilerplate_patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE | re.DOTALL)

    cleaned = cleaned.strip().lstrip('?. ')
    # If cleaning left very little, return original
    return cleaned if len(cleaned) > 10 else question


def expand_financial_query(question: str) -> str:
    """Append synonym expansions for common financial terms."""
    synonyms = {
        'revenue': 'revenue sales net turnover',
        'income': 'income earnings profit net',
        'operating': 'operating operations EBIT',
        'earnings per share': 'EPS diluted basic',
        'ebitda': 'ebitda earnings depreciation amortization',
        'capital expenditure': 'capex capital expenditures investing',
        'net income': 'net income profit earnings',
        'gross profit': 'gross profit margin',
        'return on equity': 'ROE equity return',
        'return on capital': 'ROCE capital return',
        'cash flow': 'cash flow operations CFO',
        'long-term debt': 'long term debt liabilities',
    }
    expanded = question
    q_lower = question.lower()
    for term, syns in synonyms.items():
        if term in q_lower:
            expanded += ' ' + syns
    return expanded


def build_bm25_index(corpus: List[str]) -> BM25Okapi:
    tokenized = [tokenize(c) for c in corpus]
    return BM25Okapi(tokenized)


def retrieve(question: str, bm25: BM25Okapi, corpus: List[str], k: int = 3) -> List[Tuple[int, str]]:
    scores = bm25.get_scores(tokenize(question))
    top_k = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return [(i, corpus[i]) for i in top_k]


def retrieve_clean(question: str, bm25: BM25Okapi, corpus: List[str], k: int = 3) -> List[Tuple[int, str]]:
    """BM25 retrieval with boilerplate removal + synonym expansion."""
    q_clean = extract_financial_core(question)
    q_expanded = expand_financial_query(q_clean)
    scores = bm25.get_scores(tokenize(q_expanded))
    top_k = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
    return [(i, corpus[i]) for i in top_k]


# ──────────────────────────────────────────────────────────────────────────────
# TF-IDF retrieval with financial stop-words
# ──────────────────────────────────────────────────────────────────────────────

FINANCIAL_STOPWORDS = [
    'give', 'response', 'relying', 'details', 'shown', 'following',
    'based', 'information', 'provided', 'statement', 'statements',
    'please', 'answer', 'using', 'the', 'a', 'an', 'in', 'of', 'to',
    'and', 'or', 'for', 'on', 'at', 'by', 'with', 'from', 'is', 'are',
    'was', 'were', 'be', 'been', 'has', 'have', 'had', 'do', 'does',
    'did', 'will', 'would', 'could', 'should', 'may', 'might', 'that',
    'this', 'these', 'those', 'its', 'it', 'which', 'what', 'when',
    'how', 'who', 'where', 'why', 'their', 'report', 'filing', 'document',
    'financial', 'question', 'reliance',
]


def build_tfidf_index(corpus: List[str]):
    """Return fitted TF-IDF vectorizer + matrix."""
    if not SKLEARN_AVAILABLE:
        return None, None
    vec = TfidfVectorizer(
        stop_words=FINANCIAL_STOPWORDS,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=1,
    )
    matrix = vec.fit_transform(corpus)
    return vec, matrix


def retrieve_tfidf(question: str, vec, matrix, corpus: List[str], k: int = 3) -> List[Tuple[int, str]]:
    """TF-IDF retrieval with financial stop-word filtering + cleaned query."""
    if vec is None or matrix is None:
        return []
    q_clean = extract_financial_core(question)
    q_vec = vec.transform([q_clean])
    sims = cosine_similarity(q_vec, matrix)[0]
    top_k = sorted(range(len(sims)), key=lambda i: -sims[i])[:k]
    return [(i, corpus[i]) for i in top_k]


# ──────────────────────────────────────────────────────────────────────────────
# Step 3: LLM answering
# ──────────────────────────────────────────────────────────────────────────────

def get_llm_client() -> Optional[anthropic.Anthropic]:
    key = os.environ.get("MINIMAX_API_KEY", "")
    url = os.environ.get("MINIMAX_BASE_URL", "")
    if key and url:
        return anthropic.Anthropic(api_key=key, base_url=url)
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return anthropic.Anthropic(api_key=key)
    return None


def call_llm(client: anthropic.Anthropic, context: str, question: str) -> str:
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    user = (
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        f"Answer briefly with the specific number or value:"
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=128,
            system="You are a financial analyst. Answer factual questions based ONLY on the provided context. Be concise — one sentence or less.",
            messages=[{"role": "user", "content": user}],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "text" and hasattr(block, "text"):
                return block.text.strip()
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text.strip()
        return "[EMPTY]"
    except Exception as e:
        return f"[LLM-ERROR: {e}]"


def extract_keywords(answer: str) -> List[str]:
    """Extract numbers, dollar amounts, percentages, and significant words."""
    tokens = re.findall(r'\$[\d,\.]+|\d+\.?\d*%?|\w{4,}', answer.lower())
    # Filter common stop words
    stops = {"that", "this", "with", "from", "were", "have", "been", "their",
              "which", "year", "fiscal", "total", "compared", "billion", "million"}
    return [t for t in tokens if t not in stops]


def score_response(response: str, answer: str, keywords: List[str]) -> bool:
    resp_lower = response.lower()
    # Check any keyword match
    for kw in keywords:
        if kw in resp_lower:
            return True
    # Also check if the full answer string appears
    if answer.lower()[:20] in resp_lower:
        return True
    return False


def correct_evidence_rank(question_idx: int, retrieved_indices: List[int]) -> int:
    """Return 1-based rank of correct evidence (question_idx), or 0 if not in top-k."""
    for rank, idx in enumerate(retrieved_indices, 1):
        if idx == question_idx:
            return rank
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def run_variant(
    variant_name: str,
    qa_pairs: List[Dict[str, Any]],
    corpus: List[str],
    bm25: BM25Okapi,
    tfidf_vec,
    tfidf_matrix,
    client,
    llm_available: bool,
    model_name: str,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Run one retrieval variant over all QA pairs. Returns hit list + details."""
    n = len(qa_pairs)
    retrieval_hits = []
    answer_correct = []
    details = []
    failed_cases = []

    if verbose:
        print(f"\n{'='*60}")
        print(f"Variant: {variant_name}")
        print(f"{'='*60}\n")

    for i, qa in enumerate(qa_pairs):
        question = qa["question"]
        answer = qa["answer"]
        doc_name = qa.get("doc_name", "?")
        keywords = extract_keywords(answer)

        # Choose retrieval method by variant
        if variant_name == "BM25-raw":
            retrieved = retrieve(question, bm25, corpus, k=3)
        elif variant_name == "BM25-clean":
            retrieved = retrieve_clean(question, bm25, corpus, k=3)
        elif variant_name == "TF-IDF-filtered":
            retrieved = retrieve_tfidf(question, tfidf_vec, tfidf_matrix, corpus, k=3)
        else:
            retrieved = retrieve(question, bm25, corpus, k=3)

        retrieved_indices = [idx for idx, _ in retrieved]

        # Retrieval hit: is the correct evidence (index i) in top-3?
        correct_rank = correct_evidence_rank(i, retrieved_indices)
        hit = correct_rank > 0
        retrieval_hits.append(hit)

        if verbose:
            short_q = question[:55] + "..." if len(question) > 55 else question
            rank_str = f"rank {correct_rank}" if hit else "not in top-3"
            print(f"[{i+1:02d}] {short_q}")
            print(f"       retrieval: {'HIT' if hit else 'MISS'} ({rank_str})")

        # LLM answering (only for BM25-raw to avoid repeated API calls; others use retrieval-only)
        if llm_available and variant_name == "BM25-raw":
            context = "\n\n---\n\n".join(text for _, text in retrieved)
            t_llm = time.time()
            llm_answer = call_llm(client, context, question)
            llm_ms = (time.time() - t_llm) * 1000
            if llm_answer.startswith("[LLM-ERROR"):
                llm_correct = False
                if verbose:
                    print(f"       llm: [ERROR] {llm_answer[:80]}")
            else:
                llm_correct = score_response(llm_answer, answer, keywords)
                verdict = "CORRECT" if llm_correct else "WRONG"
                if verbose:
                    print(f"       llm ({llm_ms:.0f}ms): [{verdict}] {llm_answer[:100]}")
        else:
            llm_correct = hit
            llm_answer = "[retrieval-only]"

        answer_correct.append(llm_correct)

        if verbose and retrieved:
            top_text = retrieved[0][1][:100].replace('\n', ' ')
            print(f"       top-1 passage: {top_text}...")
            print()

        detail = {
            "idx": i,
            "question": question,
            "answer": answer,
            "doc_name": doc_name,
            "keywords": keywords,
            "retrieval_hit": hit,
            "correct_rank": correct_rank,
            "retrieved_indices": retrieved_indices,
            "llm_answer": llm_answer,
            "llm_correct": llm_correct,
        }
        details.append(detail)

        if not hit:
            failed_cases.append(detail)

    return {
        "variant": variant_name,
        "n": n,
        "retrieval_hits": retrieval_hits,
        "answer_correct": answer_correct,
        "details": details,
        "failed_cases": failed_cases,
    }


def print_failure_analysis(failed_cases: List[Dict], corpus: List[str], n_show: int = 3) -> None:
    """Print up to n_show failure examples with keyword overlap diagnosis."""
    cases = failed_cases[:n_show]
    print(f"\nFailure analysis ({len(cases)} of {len(failed_cases)} shown):")
    print("=" * 60)
    for fc in cases:
        q = fc["question"]
        # Show cleaned version alongside raw
        q_clean = extract_financial_core(q)
        print(f"\n[{fc['idx']+1:02d}] RAW  : {q[:100]}")
        print(f"       CLEAN: {q_clean[:100]}")
        print(f"  Expected answer : {fc['answer']}")
        print(f"  Retrieved ranks : {fc['retrieved_indices']} (correct={fc['idx']})")

        q_tokens = set(tokenize(q))
        q_clean_tokens = set(tokenize(q_clean))
        ev_tokens = set(tokenize(corpus[fc["idx"]]))
        raw_overlap = q_tokens & ev_tokens
        clean_overlap = q_clean_tokens & ev_tokens

        top_idx = fc["retrieved_indices"][0] if fc["retrieved_indices"] else -1
        if top_idx >= 0:
            top_ev_tokens = set(tokenize(corpus[top_idx]))
            top_overlap_raw = q_tokens & top_ev_tokens
            print(f"  Overlap (raw q vs correct evidence)   : {len(raw_overlap)} — {sorted(raw_overlap)[:8]}")
            print(f"  Overlap (clean q vs correct evidence) : {len(clean_overlap)} — {sorted(clean_overlap)[:8]}")
            print(f"  Overlap (raw q vs retrieved top-1)    : {len(top_overlap_raw)} — {sorted(top_overlap_raw)[:8]}")
            if len(raw_overlap) < len(top_overlap_raw):
                print("  Diagnosis: boilerplate tokens pull wrong evidence to top-1")
            elif len(clean_overlap) < len(raw_overlap):
                print("  Diagnosis: cleaning helped but evidence still not retrieved — semantic mismatch")
            else:
                print("  Diagnosis: similar overlap even after cleaning — structural/vocabulary gap")


def main():
    results_dir = Path("/home/jayone/Project/CTX/benchmarks/results")
    results_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("FinanceBench — BM25 Retrieval Improvement")
    print("=" * 60)

    # Load dataset
    qa_pairs = load_financebench(n=20)
    n = len(qa_pairs)

    # Detect data source
    first_q = qa_pairs[0]["question"] if qa_pairs else ""
    if "Give a response" in first_q or "relying on details" in first_q:
        data_source = "HuggingFace (real FinanceBench)"
    else:
        data_source = "synthetic (fallback)"
    print(f"\nData source: {data_source}")
    print(f"Loaded {n} QA pairs\n")

    corpus = [item["evidence"] for item in qa_pairs]

    # Build indices
    print(f"Building BM25 index ({n} passages)...")
    bm25 = build_bm25_index(corpus)

    tfidf_vec, tfidf_matrix = None, None
    if SKLEARN_AVAILABLE:
        print("Building TF-IDF index...")
        tfidf_vec, tfidf_matrix = build_tfidf_index(corpus)
    else:
        print("WARNING: sklearn not available — skipping TF-IDF variant")

    # Check LLM
    client = get_llm_client()
    llm_available = client is not None
    model_name = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    if llm_available:
        base_url = os.environ.get("MINIMAX_BASE_URL", "anthropic")
        print(f"LLM: {model_name} via {base_url[:40]}...")
    else:
        print("No LLM configured — retrieval-only mode\n")

    # ── Run all variants ───────────────────────────────────────────────────────
    variants_to_run = ["BM25-raw", "BM25-clean"]
    if SKLEARN_AVAILABLE:
        variants_to_run.append("TF-IDF-filtered")

    variant_results = {}
    for vname in variants_to_run:
        # Only verbose for BM25-raw to avoid flooding output
        res = run_variant(
            variant_name=vname,
            qa_pairs=qa_pairs,
            corpus=corpus,
            bm25=bm25,
            tfidf_vec=tfidf_vec,
            tfidf_matrix=tfidf_matrix,
            client=client,
            llm_available=llm_available,
            model_name=model_name,
            verbose=(vname == "BM25-raw"),
        )
        variant_results[vname] = res

    # ── Comparison table ───────────────────────────────────────────────────────
    pageindex_claimed = 0.987

    print("\n")
    print("FinanceBench — BM25 Retrieval Improvement")
    print("=" * 54)
    print(f"{'Method':<22}  {'Retrieval@3':>12}  {'Delta vs raw':>12}")
    print("-" * 54)

    raw_hits = sum(variant_results["BM25-raw"]["retrieval_hits"])
    raw_acc = raw_hits / n

    for vname in variants_to_run:
        res = variant_results[vname]
        hits = sum(res["retrieval_hits"])
        acc = hits / n
        delta = acc - raw_acc
        delta_str = f"{delta:+.1%}" if vname != "BM25-raw" else "baseline"
        print(f"{vname:<22}  {hits:>4}/{n:<4} = {acc:>5.1%}  {delta_str:>12}")

    print(f"{'PageIndex (claimed)':<22}  {'N/A':>12}  {'98.7%':>12}")
    print("-" * 54)

    # Best variant
    best_vname = max(variants_to_run, key=lambda v: sum(variant_results[v]["retrieval_hits"]))
    best_hits = sum(variant_results[best_vname]["retrieval_hits"])
    best_acc = best_hits / n
    print(f"\nBest variant: {best_vname}  Retrieval@3 = {best_hits}/{n} = {best_acc:.1%}")
    gap = pageindex_claimed - best_acc
    print(f"Gap vs PageIndex (98.7%): {gap:+.1%}")

    # ── Failure analysis for best variant ────────────────────────────────────
    failed = variant_results[best_vname]["failed_cases"]
    if failed:
        print_failure_analysis(failed, corpus, n_show=3)
    else:
        print(f"\n{best_vname}: no retrieval failures — perfect retrieval@3!")

    # ── Per-question table ─────────────────────────────────────────────────────
    print("\nPer-question results (all variants):")
    header = f"{'#':>2}  {'Question (abbrev)':<40}"
    for vname in variants_to_run:
        header += f"  {vname[:12]:>12}"
    print(header)
    print("-" * (44 + 14 * len(variants_to_run)))
    for i, qa in enumerate(qa_pairs):
        q = qa["question"]
        short_q = (q[:37] + "...") if len(q) > 40 else q.ljust(40)
        row = f"{i+1:>2}  {short_q}"
        for vname in variants_to_run:
            hit = variant_results[vname]["retrieval_hits"][i]
            row += f"  {'HIT':>12}" if hit else f"  {'MISS':>12}"
        print(row)

    # ── Save results ───────────────────────────────────────────────────────────
    output = {
        "benchmark": "FinanceBench",
        "data_source": data_source,
        "n": n,
        "pageindex_claimed": pageindex_claimed,
        "variants": {
            vname: {
                "retrieval_hits": sum(variant_results[vname]["retrieval_hits"]),
                "retrieval_at_3": sum(variant_results[vname]["retrieval_hits"]) / n,
                "delta_vs_raw": (sum(variant_results[vname]["retrieval_hits"]) / n) - raw_acc,
            }
            for vname in variants_to_run
        },
        "best_variant": best_vname,
        "details": variant_results["BM25-raw"]["details"],
    }

    out_file = results_dir / "financebench_bm25_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_file}")


if __name__ == "__main__":
    main()
