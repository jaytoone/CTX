#!/usr/bin/env python3
"""
Nemotron-Cascade-2 CTX Downstream LLM Evaluation
G1 (Cross-session recall) + G2 (Instruction-grounded coding)
Compares against MiniMax M2.5 baseline results.
"""

import json
import requests
import datetime
import os

NEMOTRON_URL   = "http://localhost:8010/v1/chat/completions"
NEMOTRON_MODEL = "nemotron-cascade-2"

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(system, user, max_tokens=512):
    payload = {
        "model": NEMOTRON_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.0,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    resp = requests.post(NEMOTRON_URL, json=payload, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    if content is None:
        return "[NULL-CONTENT]"
    return content.strip()

# ---------------------------------------------------------------------------
# G1 — Cross-session recall (persistent_memory injection)
# ---------------------------------------------------------------------------

G1_SCENARIOS = [
    {
        "id": "g1_01",
        "memory": "User prefers dark mode in all UIs. Set dark_mode=True by default.",
        "question": "What is my UI preference?",
        "keywords": ["dark mode", "dark_mode"],
    },
    {
        "id": "g1_02",
        "memory": "Project CTX uses rank_bm25 library v0.2.2 for keyword retrieval.",
        "question": "Which library does CTX use for keyword retrieval?",
        "keywords": ["rank_bm25", "bm25"],
    },
    {
        "id": "g1_03",
        "memory": "The eval benchmark has 87 queries: 29 heading_exact, 29 heading_paraphrase, 29 keyword.",
        "question": "How many queries are in the CTX benchmark?",
        "keywords": ["87"],
    },
    {
        "id": "g1_04",
        "memory": "keyword R@3 score is 0.724 after BM25 routing optimization.",
        "question": "What is the current keyword R@3 score?",
        "keywords": ["0.724"],
    },
    {
        "id": "g1_05",
        "memory": "CTX stands for Contextual Trigger eXtraction. It is a rule-based retrieval system with no LLM calls.",
        "question": "What does CTX stand for and what kind of system is it?",
        "keywords": ["contextual trigger", "rule-based", "no llm", "without llm"],
    },
    {
        "id": "g1_06",
        "memory": "SSH alias for NIPA server is 'nipa'. Nemotron runs on port 8010, Qwen on port 8000.",
        "question": "What port does Nemotron run on in the NIPA server?",
        "keywords": ["8010"],
    },
    {
        "id": "g1_07",
        "memory": "MiniMax M2.5 G1 result: WITH CTX=1.000, WITHOUT CTX=0.219, delta=+0.781.",
        "question": "What was MiniMax G1 delta score?",
        "keywords": ["0.781", "+0.781"],
    },
    {
        "id": "g1_08",
        "memory": "Over-anchoring occurs when context shows current wrong implementation, suppressing LLM creativity. Frequency: ~20%.",
        "question": "What is over-anchoring and how often does it occur?",
        "keywords": ["over-anchoring", "over anchoring", "20%", "creativity"],
    },
]

SYSTEM_WITH_MEMORY = """You are a helpful assistant with access to persistent memory from previous sessions.
Use the memory context to answer questions accurately.

MEMORY CONTEXT:
{memory}"""

SYSTEM_NO_MEMORY = "You are a helpful assistant."

def score_g1(answer: str, keywords: list) -> float:
    ans_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in ans_lower)
    return 1.0 if hits >= 1 else 0.0

def run_g1():
    print("\n=== G1: Cross-session Recall ===")
    results = []
    with_scores, without_scores = [], []

    for sc in G1_SCENARIOS:
        q = sc["question"]
        # WITH context
        sys_with = SYSTEM_WITH_MEMORY.format(memory=sc["memory"])
        ans_with = call_llm(sys_with, q)
        s_with = score_g1(ans_with, sc["keywords"])

        # WITHOUT context
        ans_without = call_llm(SYSTEM_NO_MEMORY, q)
        s_without = score_g1(ans_without, sc["keywords"])

        with_scores.append(s_with)
        without_scores.append(s_without)

        results.append({
            "id": sc["id"],
            "question": q,
            "score_with": s_with,
            "score_without": s_without,
            "answer_with": ans_with[:120],
            "answer_without": ans_without[:120],
        })
        print(f"  {sc['id']}: WITH={s_with:.2f}  WITHOUT={s_without:.2f}")

    g1_with = sum(with_scores) / len(with_scores)
    g1_without = sum(without_scores) / len(without_scores)
    g1_delta = g1_with - g1_without

    print(f"\n  G1 WITH    = {g1_with:.3f}")
    print(f"  G1 WITHOUT = {g1_without:.3f}")
    print(f"  G1 Delta   = {g1_delta:+.3f}  (MiniMax baseline: +0.781)")

    return {"scenarios": results, "g1_with": g1_with, "g1_without": g1_without, "g1_delta": g1_delta}

# ---------------------------------------------------------------------------
# G2 — Instruction-grounded coding (file context injection)
# ---------------------------------------------------------------------------

CTX_ADAPTIVE_TRIGGER_SNIPPET = """
# src/retrieval/adaptive_trigger.py (lines 1-60)
from rank_bm25 import BM25Okapi, BM25L
import re, os

class AdaptiveTriggerRetriever:
    def __init__(self, docs_dir: str):
        self.docs_dir = docs_dir
        self.documents = []
        self.doc_titles = []
        self.bm25 = None
        self._load_documents()

    def _load_documents(self):
        for fname in sorted(os.listdir(self.docs_dir)):
            if fname.endswith('.md'):
                path = os.path.join(self.docs_dir, fname)
                with open(path) as f:
                    content = f.read()
                self.documents.append(content)
                title = fname.replace('.md','').replace('_',' ')
                self.doc_titles.append(title)
        corpus = [doc.lower().split() for doc in self.documents]
        self.bm25 = BM25Okapi(corpus)

    def retrieve(self, query: str, query_type: str = 'keyword', top_k: int = 3):
        if query_type == 'keyword':
            return self._bm25_retrieve(query, top_k)
        return self._ctx_retrieve(query, top_k)

    def _bm25_retrieve(self, query: str, top_k: int):
        tokens = query.lower().split()
        scores = self.bm25.get_scores(tokens)
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [(self.doc_titles[i], scores[i]) for i in top_idx]
"""

CTX_DOC_EVAL_SNIPPET = """
# benchmarks/eval/doc_retrieval_eval_v2.py (lines 1-50)
from rank_bm25 import BM25Okapi
import json

QUERY_TYPES = ['heading_exact', 'heading_paraphrase', 'keyword']

def rank_ctx_doc(query, docs, bm25_index=None):
    scores = {}
    for doc in docs:
        score = heading_match_score(query.text, doc.title)
        if bm25_index and score < 0.6:
            bm25_score = bm25_index.get_scores(query.text.lower().split())
            norm = bm25_score / (bm25_score.max() + 1e-9)
            score = max(score, norm * 0.9)
        scores[doc.id] = score
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

def run_benchmark(queries, docs):
    results = []
    for q in queries:
        ranked = rank_ctx_doc(q, docs)
        results.append({
            'query_id': q.id,
            'ranked': [r[0] for r in ranked[:5]],
            'query_type': q.query_type,
        })
    return results
"""

G2_SCENARIOS = [
    {
        "id": "g2_01",
        "instruction": "Add a method `get_document_count()` to AdaptiveTriggerRetriever that returns the total number of loaded documents.",
        "context": CTX_ADAPTIVE_TRIGGER_SNIPPET,
        "check_keywords": ["def get_document_count", "return len(self.documents)", "len(self.documents)"],
        "hallucination_keywords": ["elasticsearch", "faiss", "pinecone", "weaviate"],
    },
    {
        "id": "g2_02",
        "instruction": "Modify the `retrieve` method in AdaptiveTriggerRetriever to also accept a `threshold` parameter (default 0.0) and filter results below the threshold.",
        "context": CTX_ADAPTIVE_TRIGGER_SNIPPET,
        "check_keywords": ["threshold", "def retrieve", "if", "score"],
        "hallucination_keywords": ["elasticsearch", "solr", "lucene"],
    },
    {
        "id": "g2_03",
        "instruction": "Write a function `compute_r_at_k(results, ground_truth, k)` that computes Recall@K for benchmark results.",
        "context": CTX_DOC_EVAL_SNIPPET,
        "check_keywords": ["def compute_r_at_k", "recall", "return"],
        "hallucination_keywords": ["precision_at_k", "sklearn.metrics", "trec_eval"],
    },
    {
        "id": "g2_04",
        "instruction": "Add error handling to `run_benchmark` so that if a query fails, it logs the error and continues instead of crashing.",
        "context": CTX_DOC_EVAL_SNIPPET,
        "check_keywords": ["try", "except", "continue", "error"],
        "hallucination_keywords": ["kafka", "celery", "rabbitmq"],
    },
    {
        "id": "g2_05",
        "instruction": "How do I add a new document type 'code' (in addition to 'md') to AdaptiveTriggerRetriever's _load_documents method?",
        "context": CTX_ADAPTIVE_TRIGGER_SNIPPET,
        "check_keywords": [".py", "endswith", "code", ".py'"],
        "hallucination_keywords": ["elasticsearch", "mongodb", "s3"],
    },
    {
        "id": "g2_06",
        "instruction": "Write unit tests for the `_bm25_retrieve` method of AdaptiveTriggerRetriever using pytest.",
        "context": CTX_ADAPTIVE_TRIGGER_SNIPPET,
        "check_keywords": ["def test_", "pytest", "assert", "bm25_retrieve"],
        "hallucination_keywords": ["unittest.mock.patch('elasticsearch')", "cassandra"],
    },
]

SYSTEM_WITH_CTX = """You are an expert Python developer. Use the provided code context to answer accurately.

CODE CONTEXT:
{context}

Instructions: Write clean, concise Python code. Reference actual class/method names from the context."""

SYSTEM_NO_CTX = "You are an expert Python developer. Write clean, concise Python code."

def score_g2(answer: str, check_kw: list, halluc_kw: list):
    ans_lower = answer.lower()
    fra = 1.0 if any(kw.lower() in ans_lower for kw in check_kw) else 0.0
    hr  = 1.0 if any(kw.lower() in ans_lower for kw in halluc_kw) else 0.0
    combined = fra * (1.0 - hr)
    return fra, hr, combined

def run_g2():
    print("\n=== G2: Instruction-grounded Coding ===")
    results = []
    fra_with_list, hr_with_list, comb_with_list = [], [], []
    fra_without_list, hr_without_list, comb_without_list = [], [], []

    for sc in G2_SCENARIOS:
        inst = sc["instruction"]
        # WITH context
        sys_with = SYSTEM_WITH_CTX.format(context=sc["context"])
        ans_with = call_llm(sys_with, inst, max_tokens=512)
        fra_w, hr_w, comb_w = score_g2(ans_with, sc["check_keywords"], sc["hallucination_keywords"])

        # WITHOUT context
        ans_without = call_llm(SYSTEM_NO_CTX, inst, max_tokens=512)
        fra_wo, hr_wo, comb_wo = score_g2(ans_without, sc["check_keywords"], sc["hallucination_keywords"])

        fra_with_list.append(fra_w)
        hr_with_list.append(hr_w)
        comb_with_list.append(comb_w)
        fra_without_list.append(fra_wo)
        hr_without_list.append(hr_wo)
        comb_without_list.append(comb_wo)

        results.append({
            "id": sc["id"],
            "score_with":    {"fra": fra_w,  "hr": hr_w,  "combined": comb_w},
            "score_without": {"fra": fra_wo, "hr": hr_wo, "combined": comb_wo},
            "answer_with":    ans_with[:150],
            "answer_without": ans_without[:150],
        })
        print(f"  {sc['id']}: WITH FRA={fra_w:.2f} HR={hr_w:.2f}  |  WITHOUT FRA={fra_wo:.2f} HR={hr_wo:.2f}")

    n = len(G2_SCENARIOS)
    g2_with    = sum(comb_with_list) / n
    g2_without = sum(comb_without_list) / n
    g2_delta   = g2_with - g2_without
    avg_hr_w   = sum(hr_with_list) / n
    avg_hr_wo  = sum(hr_without_list) / n

    print(f"\n  G2 WITH    = {g2_with:.3f}  (HR={avg_hr_w:.3f})")
    print(f"  G2 WITHOUT = {g2_without:.3f}  (HR={avg_hr_wo:.3f})")
    print(f"  G2 Delta   = {g2_delta:+.3f}  (MiniMax baseline: +0.375 synthetic / +0.200 real)")

    return {
        "scenarios": results,
        "g2_with": g2_with, "g2_without": g2_without, "g2_delta": g2_delta,
        "hr_with": avg_hr_w, "hr_without": avg_hr_wo,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Nemotron-Cascade-2 CTX Downstream LLM Evaluation")
    print(f"Endpoint: {NEMOTRON_URL}")
    print("=" * 60)

    # Connectivity check
    try:
        r = requests.get("http://localhost:8010/v1/models", timeout=10)
        models = r.json().get("data", [])
        print(f"Models available: {[m['id'] for m in models]}")
    except Exception as e:
        print(f"[WARN] /v1/models check failed: {e}")

    g1 = run_g1()
    g2 = run_g2()

    overall_with    = (g1["g1_with"]    + g2["g2_with"])    / 2
    overall_without = (g1["g1_without"] + g2["g2_without"]) / 2
    overall_delta   = overall_with - overall_without

    print("\n" + "=" * 60)
    print("COMPARISON TABLE: Nemotron vs MiniMax M2.5")
    print("=" * 60)
    print(f"{'Metric':<30} {'Nemotron':>10} {'MiniMax':>10} {'Diff':>10}")
    print("-" * 60)

    minimax = {"G1 Delta": 0.781, "G2 Synthetic Delta": 0.375, "Overall Delta": 0.578}
    nemotron_vals = {
        "G1 Delta":           g1["g1_delta"],
        "G2 Synthetic Delta": g2["g2_delta"],
        "Overall Delta":      overall_delta,
    }
    for key in minimax:
        nem = nemotron_vals[key]
        mx  = minimax[key]
        diff = nem - mx
        print(f"  {key:<28} {nem:>+10.3f} {mx:>+10.3f} {diff:>+10.3f}")

    print("\nDetailed:")
    print(f"  G1  WITH={g1['g1_with']:.3f}  WITHOUT={g1['g1_without']:.3f}  Δ={g1['g1_delta']:+.3f}")
    print(f"  G2  WITH={g2['g2_with']:.3f}  WITHOUT={g2['g2_without']:.3f}  Δ={g2['g2_delta']:+.3f}")
    print(f"  ALL WITH={overall_with:.3f}  WITHOUT={overall_without:.3f}  Δ={overall_delta:+.3f}")

    output = {
        "model": NEMOTRON_MODEL,
        "timestamp": datetime.datetime.now().isoformat(),
        "g1": g1,
        "g2": g2,
        "overall": {
            "with": overall_with,
            "without": overall_without,
            "delta": overall_delta,
        },
        "minimax_comparison": {
            "g1_delta_diff":   g1["g1_delta"]    - 0.781,
            "g2_delta_diff":   g2["g2_delta"]    - 0.375,
            "overall_diff":    overall_delta     - 0.578,
        },
    }

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/home/work/nemotron_ctx_results_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] {out_path}")

    return output

if __name__ == "__main__":
    main()
