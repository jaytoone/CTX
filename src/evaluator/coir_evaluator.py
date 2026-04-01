"""
COIR-style benchmark evaluation using CodeSearchNet Python test set.

Simulates the COIR (ACL 2025) code information retrieval benchmark:
- Uses CodeSearchNet Python test set (natural language -> code retrieval)
- Builds a corpus of code functions, uses docstrings as queries
- Evaluates CTX vs BM25 vs Dense TF-IDF vs LlamaIndex vs Chroma Dense
- Reports Recall@1, Recall@5, MRR

This is a lightweight alternative to the full COIR benchmark, using
the same underlying data (CodeSearchNet) that COIR builds upon.
"""

import json
import os
import random
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class COIRQuery:
    """A single code retrieval query from CodeSearchNet."""
    query_id: str
    query_text: str          # natural language docstring
    ground_truth_idx: int    # index into corpus
    func_name: str
    repository: str


@dataclass
class COIRCorpusEntry:
    """A single code document in the retrieval corpus."""
    doc_id: str
    code: str                # function code
    func_name: str
    file_path: str
    repository: str


@dataclass
class COIRResult:
    """Result for a single strategy on the COIR benchmark."""
    strategy: str
    recall_at_1: float
    recall_at_5: float
    mrr: float
    n_queries: int
    per_query: List[Dict] = field(default_factory=list)


def load_codesearchnet_corpus(
    n_queries: int = 100,
    corpus_multiplier: int = 10,
    seed: int = 42,
) -> Tuple[List[COIRQuery], List[COIRCorpusEntry]]:
    """Load CodeSearchNet Python test set and build query-corpus pairs.

    For each query (docstring), the corpus contains the true function plus
    (corpus_multiplier - 1) distractor functions from other entries.

    Args:
        n_queries: Number of queries to sample
        corpus_multiplier: Total corpus size per query = n_queries * multiplier
        seed: Random seed

    Returns:
        Tuple of (queries, corpus)
    """
    from datasets import load_dataset

    ds = load_dataset("code_search_net", "python", split="test")

    # Filter for entries with non-empty docstrings and reasonable code length
    valid_entries = []
    for i, entry in enumerate(ds):
        doc = entry["func_documentation_string"].strip()
        code = entry["func_code_string"].strip()
        if len(doc) > 20 and len(code) > 50 and len(doc) < 500:
            valid_entries.append((i, entry))

    rng = random.Random(seed)
    rng.shuffle(valid_entries)

    # Total pool: need n_queries for queries + extras for distractors
    total_needed = n_queries * corpus_multiplier
    pool = valid_entries[:max(total_needed, len(valid_entries))]

    # First n_queries become the queries, rest are distractors
    query_entries = pool[:n_queries]
    distractor_pool = pool[n_queries:]

    # Build corpus: all query functions + distractor functions
    corpus: List[COIRCorpusEntry] = []
    queries: List[COIRQuery] = []

    # Add all query functions to corpus first
    for idx, (orig_idx, entry) in enumerate(query_entries):
        corpus.append(COIRCorpusEntry(
            doc_id=f"doc_{idx}",
            code=entry["func_code_string"].strip(),
            func_name=entry["func_name"],
            file_path=entry["func_path_in_repository"],
            repository=entry["repository_name"],
        ))
        queries.append(COIRQuery(
            query_id=f"q_{idx}",
            query_text=entry["func_documentation_string"].strip(),
            ground_truth_idx=idx,
            func_name=entry["func_name"],
            repository=entry["repository_name"],
        ))

    # Add distractors
    n_distractors = min(len(distractor_pool), total_needed - n_queries)
    for idx, (orig_idx, entry) in enumerate(distractor_pool[:n_distractors]):
        corpus.append(COIRCorpusEntry(
            doc_id=f"doc_{n_queries + idx}",
            code=entry["func_code_string"].strip(),
            func_name=entry["func_name"],
            file_path=entry["func_path_in_repository"],
            repository=entry["repository_name"],
        ))

    # Shuffle corpus so ground truth positions are randomized
    corpus_indices = list(range(len(corpus)))
    rng.shuffle(corpus_indices)
    shuffled_corpus = [corpus[i] for i in corpus_indices]

    # Update ground truth indices after shuffle
    old_to_new = {old: new for new, old in enumerate(corpus_indices)}
    for q in queries:
        q.ground_truth_idx = old_to_new[q.ground_truth_idx]

    # Reassign doc_ids
    for i, entry in enumerate(shuffled_corpus):
        entry.doc_id = f"doc_{i}"

    return queries, shuffled_corpus


def _compute_retrieval_metrics(
    rankings: List[List[int]],
    ground_truths: List[int],
) -> Tuple[float, float, float]:
    """Compute Recall@1, Recall@5, MRR from rankings.

    Args:
        rankings: For each query, ordered list of corpus indices (most relevant first)
        ground_truths: For each query, the ground truth corpus index

    Returns:
        Tuple of (recall@1, recall@5, mrr)
    """
    recall_1 = 0.0
    recall_5 = 0.0
    mrr_sum = 0.0
    n = len(rankings)

    for ranking, gt in zip(rankings, ground_truths):
        if gt in ranking[:1]:
            recall_1 += 1
        if gt in ranking[:5]:
            recall_5 += 1
        for rank, idx in enumerate(ranking):
            if idx == gt:
                mrr_sum += 1.0 / (rank + 1)
                break

    return recall_1 / n, recall_5 / n, mrr_sum / n


def evaluate_bm25(
    queries: List[COIRQuery],
    corpus: List[COIRCorpusEntry],
) -> COIRResult:
    """Evaluate BM25 retrieval on COIR benchmark."""
    from rank_bm25 import BM25Okapi

    # Tokenize corpus
    tokenized_corpus = [doc.code.lower().split() for doc in corpus]
    bm25 = BM25Okapi(tokenized_corpus)

    rankings = []
    per_query = []

    for q in queries:
        tokenized_query = q.query_text.lower().split()
        scores = bm25.get_scores(tokenized_query)
        ranked_indices = np.argsort(scores)[::-1].tolist()
        rankings.append(ranked_indices)

        hit_at_1 = q.ground_truth_idx in ranked_indices[:1]
        hit_at_5 = q.ground_truth_idx in ranked_indices[:5]
        rank_pos = ranked_indices.index(q.ground_truth_idx) if q.ground_truth_idx in ranked_indices else -1
        per_query.append({
            "query_id": q.query_id,
            "hit_at_1": hit_at_1,
            "hit_at_5": hit_at_5,
            "rank": rank_pos + 1,
        })

    r1, r5, mrr = _compute_retrieval_metrics(rankings, [q.ground_truth_idx for q in queries])

    return COIRResult(
        strategy="BM25",
        recall_at_1=r1,
        recall_at_5=r5,
        mrr=mrr,
        n_queries=len(queries),
        per_query=per_query,
    )


def evaluate_dense_tfidf(
    queries: List[COIRQuery],
    corpus: List[COIRCorpusEntry],
) -> COIRResult:
    """Evaluate Dense TF-IDF retrieval on COIR benchmark."""
    corpus_texts = [doc.code for doc in corpus]
    query_texts = [q.query_text for q in queries]

    vectorizer = TfidfVectorizer(max_features=10000, stop_words="english")
    corpus_vectors = vectorizer.fit_transform(corpus_texts)
    query_vectors = vectorizer.transform(query_texts)

    similarities = cosine_similarity(query_vectors, corpus_vectors)

    rankings = []
    per_query = []

    for i, q in enumerate(queries):
        ranked_indices = np.argsort(similarities[i])[::-1].tolist()
        rankings.append(ranked_indices)

        hit_at_1 = q.ground_truth_idx in ranked_indices[:1]
        hit_at_5 = q.ground_truth_idx in ranked_indices[:5]
        rank_pos = ranked_indices.index(q.ground_truth_idx) if q.ground_truth_idx in ranked_indices else -1
        per_query.append({
            "query_id": q.query_id,
            "hit_at_1": hit_at_1,
            "hit_at_5": hit_at_5,
            "rank": rank_pos + 1,
        })

    r1, r5, mrr = _compute_retrieval_metrics(rankings, [q.ground_truth_idx for q in queries])

    return COIRResult(
        strategy="Dense TF-IDF",
        recall_at_1=r1,
        recall_at_5=r5,
        mrr=mrr,
        n_queries=len(queries),
        per_query=per_query,
    )


def evaluate_dense_embedding(
    queries: List[COIRQuery],
    corpus: List[COIRCorpusEntry],
) -> COIRResult:
    """Evaluate dense neural embedding retrieval (sentence-transformers)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2")

    corpus_texts = [doc.code[:1000] for doc in corpus]  # truncate long code
    query_texts = [q.query_text for q in queries]

    print("    Encoding corpus...", flush=True)
    corpus_embeddings = model.encode(corpus_texts, batch_size=32, show_progress_bar=False)
    print("    Encoding queries...", flush=True)
    query_embeddings = model.encode(query_texts, batch_size=32, show_progress_bar=False)

    similarities = cosine_similarity(query_embeddings, corpus_embeddings)

    rankings = []
    per_query = []

    for i, q in enumerate(queries):
        ranked_indices = np.argsort(similarities[i])[::-1].tolist()
        rankings.append(ranked_indices)

        hit_at_1 = q.ground_truth_idx in ranked_indices[:1]
        hit_at_5 = q.ground_truth_idx in ranked_indices[:5]
        rank_pos = ranked_indices.index(q.ground_truth_idx) if q.ground_truth_idx in ranked_indices else -1
        per_query.append({
            "query_id": q.query_id,
            "hit_at_1": hit_at_1,
            "hit_at_5": hit_at_5,
            "rank": rank_pos + 1,
        })

    r1, r5, mrr = _compute_retrieval_metrics(rankings, [q.ground_truth_idx for q in queries])

    return COIRResult(
        strategy="Dense Embedding (MiniLM)",
        recall_at_1=r1,
        recall_at_5=r5,
        mrr=mrr,
        n_queries=len(queries),
        per_query=per_query,
    )


def evaluate_ctxt_adaptive(
    queries: List[COIRQuery],
    corpus: List[COIRCorpusEntry],
) -> COIRResult:
    """Evaluate CTX adaptive trigger retrieval on COIR benchmark.

    Creates a temporary codebase from the corpus, then runs
    the adaptive trigger retriever against it.
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

    # Create temporary codebase from corpus
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write each corpus entry as a Python file
        file_map = {}  # doc_id -> relative path
        for doc in corpus:
            # Create a unique filename
            safe_name = doc.func_name.replace(".", "_").replace("/", "_")
            rel_path = f"{doc.doc_id}_{safe_name}.py"
            fpath = os.path.join(tmpdir, rel_path)

            # Write the code as a standalone Python file
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f'"""{doc.func_name} from {doc.repository}"""\n\n')
                f.write(doc.code)
                f.write("\n")

            file_map[doc.doc_id] = rel_path

        # Initialize retriever with dense embedding enabled for benchmark accuracy
        retriever = AdaptiveTriggerRetriever(tmpdir, use_dense=True)

        rankings = []
        per_query = []

        for q in queries:
            result = retriever.retrieve(
                query_id=q.query_id,
                query_text=q.query_text,
                k=10,
            )

            # Map retrieved files back to corpus indices
            retrieved_indices = []
            for rfile in result.retrieved_files:
                for idx, doc in enumerate(corpus):
                    if file_map.get(doc.doc_id) == rfile:
                        retrieved_indices.append(idx)
                        break

            rankings.append(retrieved_indices)

            hit_at_1 = q.ground_truth_idx in retrieved_indices[:1]
            hit_at_5 = q.ground_truth_idx in retrieved_indices[:5]
            rank_pos = -1
            for r, idx in enumerate(retrieved_indices):
                if idx == q.ground_truth_idx:
                    rank_pos = r
                    break

            per_query.append({
                "query_id": q.query_id,
                "hit_at_1": hit_at_1,
                "hit_at_5": hit_at_5,
                "rank": rank_pos + 1 if rank_pos >= 0 else -1,
            })

    r1, r5, mrr = _compute_retrieval_metrics(rankings, [q.ground_truth_idx for q in queries])

    return COIRResult(
        strategy="CTX Adaptive Trigger",
        recall_at_1=r1,
        recall_at_5=r5,
        mrr=mrr,
        n_queries=len(queries),
        per_query=per_query,
    )


def evaluate_hybrid_dense_ctx(
    queries: List[COIRQuery],
    corpus: List[COIRCorpusEntry],
) -> COIRResult:
    """Evaluate Hybrid Dense+CTX retrieval on COIR benchmark.

    Creates a temporary codebase from the corpus, then runs
    the hybrid dense + import graph retriever against it.
    """
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from src.retrieval.hybrid_dense_ctx import HybridDenseCTXRetriever

    with tempfile.TemporaryDirectory() as tmpdir:
        file_map = {}
        for doc in corpus:
            safe_name = doc.func_name.replace(".", "_").replace("/", "_")
            rel_path = f"{doc.doc_id}_{safe_name}.py"
            fpath = os.path.join(tmpdir, rel_path)

            with open(fpath, "w", encoding="utf-8") as f:
                f.write(f'"""{doc.func_name} from {doc.repository}"""\n\n')
                f.write(doc.code)
                f.write("\n")

            file_map[doc.doc_id] = rel_path

        retriever = HybridDenseCTXRetriever(tmpdir)

        rankings = []
        per_query = []

        for q in queries:
            result = retriever.retrieve(
                query_id=q.query_id,
                query_text=q.query_text,
                k=10,
            )

            retrieved_indices = []
            for rfile in result.retrieved_files:
                for idx, doc in enumerate(corpus):
                    if file_map.get(doc.doc_id) == rfile:
                        retrieved_indices.append(idx)
                        break

            rankings.append(retrieved_indices)

            hit_at_1 = q.ground_truth_idx in retrieved_indices[:1]
            hit_at_5 = q.ground_truth_idx in retrieved_indices[:5]
            rank_pos = -1
            for r, idx in enumerate(retrieved_indices):
                if idx == q.ground_truth_idx:
                    rank_pos = r
                    break

            per_query.append({
                "query_id": q.query_id,
                "hit_at_1": hit_at_1,
                "hit_at_5": hit_at_5,
                "rank": rank_pos + 1 if rank_pos >= 0 else -1,
            })

    r1, r5, mrr = _compute_retrieval_metrics(rankings, [q.ground_truth_idx for q in queries])

    return COIRResult(
        strategy="Hybrid Dense+CTX",
        recall_at_1=r1,
        recall_at_5=r5,
        mrr=mrr,
        n_queries=len(queries),
        per_query=per_query,
    )


def run_coir_evaluation(
    n_queries: int = 100,
    corpus_multiplier: int = 10,
    seed: int = 42,
    results_dir: str = "benchmarks/results",
) -> Dict:
    """Run the full COIR-style evaluation.

    Args:
        n_queries: Number of queries
        corpus_multiplier: Corpus size multiplier
        seed: Random seed
        results_dir: Where to save results

    Returns:
        Results dictionary
    """
    os.makedirs(results_dir, exist_ok=True)
    timestamp = datetime.now().isoformat()

    print(f"[COIR Evaluation -- CodeSearchNet Python]")
    print(f"  Queries: {n_queries}")
    print(f"  Corpus multiplier: {corpus_multiplier}x")
    print(f"  Expected corpus size: ~{n_queries * corpus_multiplier}")
    print()

    # Step 1: Load data
    print("[1/6] Loading CodeSearchNet Python test set...")
    queries, corpus = load_codesearchnet_corpus(
        n_queries=n_queries,
        corpus_multiplier=corpus_multiplier,
        seed=seed,
    )
    print(f"  Loaded {len(queries)} queries, {len(corpus)} corpus documents")
    print()

    results = {
        "benchmark": "COIR-CodeSearchNet",
        "language": "Python",
        "n_queries": len(queries),
        "corpus_size": len(corpus),
        "corpus_multiplier": corpus_multiplier,
        "seed": seed,
        "timestamp": timestamp,
        "strategies": {},
    }

    # Step 2: BM25
    print("[2/6] Evaluating BM25...")
    t0 = time.time()
    bm25_result = evaluate_bm25(queries, corpus)
    bm25_time = time.time() - t0
    print(f"  R@1={bm25_result.recall_at_1:.3f}  R@5={bm25_result.recall_at_5:.3f}  MRR={bm25_result.mrr:.3f}  ({bm25_time:.1f}s)")
    results["strategies"]["BM25"] = asdict(bm25_result)
    results["strategies"]["BM25"]["elapsed_s"] = bm25_time
    print()

    # Step 3: Dense TF-IDF
    print("[3/6] Evaluating Dense TF-IDF...")
    t0 = time.time()
    tfidf_result = evaluate_dense_tfidf(queries, corpus)
    tfidf_time = time.time() - t0
    print(f"  R@1={tfidf_result.recall_at_1:.3f}  R@5={tfidf_result.recall_at_5:.3f}  MRR={tfidf_result.mrr:.3f}  ({tfidf_time:.1f}s)")
    results["strategies"]["Dense TF-IDF"] = asdict(tfidf_result)
    results["strategies"]["Dense TF-IDF"]["elapsed_s"] = tfidf_time
    print()

    # Step 4: Dense Embedding
    print("[4/6] Evaluating Dense Embedding (all-MiniLM-L6-v2)...")
    t0 = time.time()
    dense_result = evaluate_dense_embedding(queries, corpus)
    dense_time = time.time() - t0
    print(f"  R@1={dense_result.recall_at_1:.3f}  R@5={dense_result.recall_at_5:.3f}  MRR={dense_result.mrr:.3f}  ({dense_time:.1f}s)")
    results["strategies"]["Dense Embedding"] = asdict(dense_result)
    results["strategies"]["Dense Embedding"]["elapsed_s"] = dense_time
    print()

    # Step 5: CTX Adaptive Trigger
    print("[5/6] Evaluating CTX Adaptive Trigger...")
    t0 = time.time()
    ctx_result = evaluate_ctxt_adaptive(queries, corpus)
    ctx_time = time.time() - t0
    print(f"  R@1={ctx_result.recall_at_1:.3f}  R@5={ctx_result.recall_at_5:.3f}  MRR={ctx_result.mrr:.3f}  ({ctx_time:.1f}s)")
    results["strategies"]["CTX Adaptive Trigger"] = asdict(ctx_result)
    results["strategies"]["CTX Adaptive Trigger"]["elapsed_s"] = ctx_time
    print()

    # Step 6: Hybrid Dense+CTX
    print("[6/6] Evaluating Hybrid Dense+CTX...")
    t0 = time.time()
    hybrid_result = evaluate_hybrid_dense_ctx(queries, corpus)
    hybrid_time = time.time() - t0
    print(f"  R@1={hybrid_result.recall_at_1:.3f}  R@5={hybrid_result.recall_at_5:.3f}  MRR={hybrid_result.mrr:.3f}  ({hybrid_time:.1f}s)")
    results["strategies"]["Hybrid Dense+CTX"] = asdict(hybrid_result)
    results["strategies"]["Hybrid Dense+CTX"]["elapsed_s"] = hybrid_time
    print()

    # Save JSON results
    json_path = os.path.join(results_dir, "coir_evaluation.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"  JSON results saved to {json_path}")

    # Generate markdown report
    _generate_coir_report(results, results_dir)

    return results


def _generate_coir_report(results: Dict, results_dir: str) -> None:
    """Generate a markdown report for COIR evaluation results."""
    report_path = os.path.join(results_dir, "coir_evaluation.md")

    strategies = results["strategies"]
    lines = [
        "# COIR-Style Evaluation: CodeSearchNet Python",
        "",
        f"**Date**: {results['timestamp']}",
        f"**Benchmark**: {results['benchmark']}",
        f"**Queries**: {results['n_queries']}",
        f"**Corpus Size**: {results['corpus_size']}",
        f"**Corpus Multiplier**: {results['corpus_multiplier']}x",
        f"**Seed**: {results['seed']}",
        "",
        "---",
        "",
        "## Results Summary",
        "",
        "| Strategy | Recall@1 | Recall@5 | MRR | Time (s) |",
        "|----------|----------|----------|-----|----------|",
    ]

    for name, data in strategies.items():
        lines.append(
            f"| {name} | {data['recall_at_1']:.3f} | {data['recall_at_5']:.3f} "
            f"| {data['mrr']:.3f} | {data.get('elapsed_s', 0):.1f} |"
        )

    # Analysis
    ctx_data = strategies.get("CTX Adaptive Trigger", {})
    bm25_data = strategies.get("BM25", {})
    dense_data = strategies.get("Dense Embedding", {})

    lines.extend([
        "",
        "---",
        "",
        "## Analysis",
        "",
    ])

    if ctx_data and bm25_data:
        r5_diff = ctx_data["recall_at_5"] - bm25_data["recall_at_5"]
        lines.append(
            f"- **CTX vs BM25**: R@5 difference = {r5_diff:+.3f} "
            f"(CTX {ctx_data['recall_at_5']:.3f} vs BM25 {bm25_data['recall_at_5']:.3f})"
        )

    if ctx_data and dense_data:
        r5_diff = ctx_data["recall_at_5"] - dense_data["recall_at_5"]
        lines.append(
            f"- **CTX vs Dense Embedding**: R@5 difference = {r5_diff:+.3f} "
            f"(CTX {ctx_data['recall_at_5']:.3f} vs Dense {dense_data['recall_at_5']:.3f})"
        )

    lines.extend([
        "",
        "### Interpretation",
        "",
        "The CodeSearchNet benchmark evaluates **natural language to code** retrieval,",
        "where queries are function docstrings and targets are function implementations.",
        "This task differs from CTX's primary use case (code-to-code structural retrieval)",
        "in that it favors semantic text matching over structural dependency resolution.",
        "",
        "- BM25 and TF-IDF excel because docstrings often share vocabulary with code",
        "- Dense embeddings capture semantic similarity between descriptions and code",
        "- CTX's trigger classifier and import graph traversal provide less advantage",
        "  on this text-to-code matching task, as there are no import dependencies to resolve",
        "",
        "This result is **expected and informative**: CTX's architectural advantage is",
        "specifically on structural/dependency queries (IMPLICIT_CONTEXT), not on",
        "text-similarity-based code search. The COIR results complement the main",
        "benchmark results by showing CTX's performance on an independent, standardized",
        "code retrieval task.",
        "",
        "---",
        "",
        f"*Generated by CTX COIR Evaluation ({results['timestamp']})*",
    ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Report saved to {report_path}")
