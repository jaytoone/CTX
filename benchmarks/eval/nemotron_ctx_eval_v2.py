#!/usr/bin/env python3
"""
Nemotron-Cascade-2 CTX Downstream LLM Evaluation v2
G1 (cross-session recall, fixed) + G2 (CTX-specific hard scenarios — ceiling removed)

v2 changes:
- G2 redesigned: CTX codebase-specific architectural knowledge required
  (exact thresholds, class/method names, design decisions that are NOT guessable)
- g1_08 keyword updated to avoid reverse-scoring ambiguity
"""

import json
import requests
import datetime

NEMOTRON_URL   = "http://localhost:8010/v1/chat/completions"
NEMOTRON_MODEL = "nemotron-cascade-2"

# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(system, user, max_tokens=600):
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
# G1 — same as v1 with g1_08 keyword fix
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
        "memory": "keyword R@3 score is 0.724 after BM25 routing optimization on 29 documents.",
        "question": "What is the current keyword R@3 score after BM25 routing optimization?",
        "keywords": ["0.724"],
    },
    {
        "id": "g1_03",
        "memory": "The eval benchmark has exactly 87 queries: 29 heading_exact, 29 heading_paraphrase, 29 keyword.",
        "question": "How many total queries are in the CTX benchmark and what types?",
        "keywords": ["87"],
    },
    {
        "id": "g1_04",
        "memory": "SSH alias for NIPA server is 'nipa'. Nemotron runs on port 8010, Qwen on port 8000.",
        "question": "What port does the Nemotron model server run on in NIPA?",
        "keywords": ["8010"],
    },
    {
        "id": "g1_05",
        "memory": "CTX stands for Contextual Trigger eXtraction. It is a rule-based retrieval system with no LLM calls.",
        "question": "What does CTX stand for and what kind of system is it?",
        "keywords": ["contextual trigger", "rule-based", "no llm", "without llm"],
    },
    {
        "id": "g1_06",
        "memory": "MiniMax M2.5 G1 result: WITH CTX=1.000, WITHOUT CTX=0.219, delta=+0.781.",
        "question": "What was the MiniMax G1 delta score?",
        "keywords": ["0.781", "+0.781"],
    },
    {
        "id": "g1_07",
        "memory": "BM25Okapi with IDF performs worse on small domain-specific corpora (29 docs) because domain keywords appear in many docs, reducing IDF scores. Use TF-only BM25 instead.",
        "question": "Why does BM25Okapi perform poorly on the CTX 29-doc corpus?",
        "keywords": ["idf", "domain", "29", "tf-only", "tf only"],
    },
    {
        "id": "g1_08",
        "memory": "Over-anchoring phenomenon: when CTX shows current wrong implementation, LLM creativity is suppressed. Observed in 20% of Fix/Replace instruction scenarios.",
        "question": "What percentage of Fix/Replace scenarios show over-anchoring in CTX downstream eval?",
        "keywords": ["20%", "20 percent"],
    },
]

SYSTEM_WITH_MEMORY = """You are a helpful assistant with access to persistent memory from previous sessions.
Use the memory context to answer questions accurately and concisely.

MEMORY CONTEXT:
{memory}"""

SYSTEM_NO_MEMORY = "You are a helpful assistant. Answer concisely."

def score_g1(answer: str, keywords: list) -> float:
    ans_lower = answer.lower()
    return 1.0 if any(kw.lower() in ans_lower for kw in keywords) else 0.0

def run_g1():
    print("\n=== G1: Cross-session Recall (v2) ===")
    results = []
    with_scores, without_scores = [], []

    for sc in G1_SCENARIOS:
        q = sc["question"]
        sys_with = SYSTEM_WITH_MEMORY.format(memory=sc["memory"])
        ans_with    = call_llm(sys_with, q, max_tokens=200)
        ans_without = call_llm(SYSTEM_NO_MEMORY, q, max_tokens=200)
        s_with    = score_g1(ans_with,    sc["keywords"])
        s_without = score_g1(ans_without, sc["keywords"])

        with_scores.append(s_with)
        without_scores.append(s_without)
        results.append({
            "id": sc["id"],
            "score_with": s_with, "score_without": s_without,
            "ans_with": ans_with[:100], "ans_without": ans_without[:100],
        })
        print(f"  {sc['id']}: WITH={s_with:.2f}  WITHOUT={s_without:.2f}")

    g1_with    = sum(with_scores)    / len(with_scores)
    g1_without = sum(without_scores) / len(without_scores)
    g1_delta   = g1_with - g1_without
    print(f"\n  G1 WITH={g1_with:.3f}  WITHOUT={g1_without:.3f}  Δ={g1_delta:+.3f}")
    return {"scenarios": results, "g1_with": g1_with, "g1_without": g1_without, "g1_delta": g1_delta}

# ---------------------------------------------------------------------------
# G2 v2 — CTX-specific hard scenarios (ceiling removed)
# ---------------------------------------------------------------------------

# Exact code excerpts that contain the "secret" answers
CTX_BM25_BLEND_CODE = """
# benchmarks/eval/doc_retrieval_eval_v2.py — rank_ctx_doc() BM25 blend logic
def rank_ctx_doc(query: DocQuery, docs: List[DocFile], bm25_index=None) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {}
    for doc in docs:
        # Stage 1: heading match
        current = heading_match_score(query.text, doc.headings)

        # Stage 2: BM25 augmentation
        if bm25_index is not None:
            tokens = query.text.lower().split()
            raw = bm25_index.get_scores(tokens)
            max_raw = raw.max() if len(raw) > 0 else 1.0
            norm = float(raw[docs.index(doc)]) / (max_raw + 1e-9)

            if current >= 0.6:
                current = current + norm * 0.2
            else:
                current = max(current, norm * 0.9)

        scores[doc.rel_path] = current
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
"""

CTX_ROUTING_CODE = """
# benchmarks/eval/doc_retrieval_eval_v2.py — query_type routing
def evaluate_ctx_doc(queries, docs, bm25_idx):
    results = []
    for q in queries:
        if q.query_type == 'keyword':
            # TF-only BM25 direct routing (NOT BM25Okapi)
            from rank_bm25 import BM25L as TFOnlyBM25
            tf_bm25 = TFOnlyBM25([d.content.lower().split() for d in docs])
            ranked = sorted(
                enumerate(tf_bm25.get_scores(q.text.lower().split())),
                key=lambda x: x[1], reverse=True
            )
            results.append([docs[i].rel_path for i, _ in ranked[:5]])
        else:
            ranked = rank_ctx_doc(q, docs, bm25_index=bm25_idx)
            results.append([r[0] for r in ranked[:5]])
    return results
"""

CTX_EXCLUDED_DIRS = """
# src/retrieval/adaptive_trigger.py — excluded directories frozenset
_EXCLUDED_DIRS = frozenset({
    'venv', '.venv', 'env', '.env',
    'node_modules', '__pycache__', '.git', '.svn', '.hg',
    'build', 'dist', 'site-packages', '.local',
    '.tox', '.mypy_cache', '.pytest_cache', '.ruff_cache',
    'htmlcov', '.eggs', 'buck-out', '_build',
})
"""

CTX_SYMBOL_INDEX = """
# src/retrieval/adaptive_trigger.py — symbol indexing (lines 80-130)
    def _index_symbols(self, rel_path: str, content: str) -> None:
        # Extract function and class definitions
        for m in re.finditer(r'^(?:def|class)\s+(\w+)', content, re.MULTILINE):
            name = m.group(1)
            self.symbol_index.setdefault(name, []).append(rel_path)

    def _index_concepts(self, rel_path: str, content: str) -> None:
        # Extract docstring concepts
        for m in re.finditer(r'\"\"\"(.*?)\"\"\"', content, re.DOTALL):
            words = re.findall(r'\b[a-z][a-z_]{3,}\b', m.group(1).lower())
            for w in words:
                if w not in _NON_SYMBOLS:
                    self.concept_index.setdefault(w, []).append(rel_path)

# _NON_SYMBOLS frozenset (30 common verbs/conjunctions excluded)
_NON_SYMBOLS = frozenset({
    'that', 'this', 'with', 'from', 'into', 'have', 'been', 'will',
    'also', 'when', 'then', 'each', 'than', 'they', 'their', 'there',
    'other', 'some', 'which', 'would', 'could', 'should', 'return',
    'value', 'first', 'second', 'third', 'using', 'based', 'given',
})
"""

CTX_IMPORT_GRAPH = """
# src/retrieval/adaptive_trigger.py — import graph building
    def _build_import_graph(self, rel_path: str, content: str) -> None:
        # Extract import statements to build adjacency
        for m in re.finditer(r'^(?:from|import)\s+([\w.]+)', content, re.MULTILINE):
            module = m.group(1).split('.')[0]
            target = self.module_to_file.get(module)
            if target:
                self.import_graph.setdefault(rel_path, []).append(target)

    def _implicit_retrieve(self, query_file: str, k: int) -> List[str]:
        # BFS from query_file up to depth 2
        visited, queue = set(), [(query_file, 0)]
        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > 2:
                continue
            visited.add(node)
            for neighbor in self.import_graph.get(node, []):
                queue.append((neighbor, depth + 1))
        return list(visited - {query_file})[:k]
"""

G2_SCENARIOS_HARD = [
    {
        "id": "g2_h01",
        "instruction": (
            "In CTX's doc_retrieval_eval_v2.py, what exact numeric threshold is used "
            "to decide whether to add BM25 score as `current + norm * 0.2` vs "
            "`max(current, norm * 0.9)`?"
        ),
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.6", "0.6 threshold", ">= 0.6"],
        "hallucination_keywords": ["0.5", "0.7", "0.8", "0.4"],
    },
    {
        "id": "g2_h02",
        "instruction": (
            "In CTX's benchmark, when query_type is 'keyword', which BM25 variant "
            "is used for direct routing — BM25Okapi, BM25L, or BM25Plus? "
            "Why was this chosen over BM25Okapi?"
        ),
        "context": CTX_ROUTING_CODE,
        "check_keywords": ["bm25l", "tf-only", "tf only", "bm25okapi"],
        "hallucination_keywords": ["bm25plus", "sparse", "lucene"],
    },
    {
        "id": "g2_h03",
        "instruction": (
            "List exactly which directory names are in CTX's _EXCLUDED_DIRS frozenset "
            "in adaptive_trigger.py. Are 'benchmarks' and '.mypy_cache' included?"
        ),
        "context": CTX_EXCLUDED_DIRS,
        "check_keywords": [".mypy_cache", "mypy_cache"],
        "hallucination_keywords": ["benchmarks"],
    },
    {
        "id": "g2_h04",
        "instruction": (
            "In CTX's _index_concepts(), what is the minimum word length requirement "
            "for a word to be added to the concept_index? Show the regex pattern used."
        ),
        "context": CTX_SYMBOL_INDEX,
        "check_keywords": ["4", "3,}", "[a-z][a-z_]{3,}", "four", "minimum"],
        "hallucination_keywords": ["3 character", "two-letter", "5 characters", "minimum length of 5"],
    },
    {
        "id": "g2_h05",
        "instruction": (
            "In CTX's _implicit_retrieve(), what is the maximum BFS depth when traversing "
            "the import graph? And does it include or exclude the starting file from results?"
        ),
        "context": CTX_IMPORT_GRAPH,
        "check_keywords": ["depth 2", "depth > 2", "2", "exclud"],
        "hallucination_keywords": ["depth 3", "depth 5", "includes the starting"],
    },
    {
        "id": "g2_h06",
        "instruction": (
            "In CTX's BM25 blend formula for heading queries (current < 0.6 branch), "
            "what multiplier is applied to the normalized BM25 score, and why is an "
            "upper bound needed?"
        ),
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.9", "norm * 0.9", "false positive", "upper bound", "cap"],
        "hallucination_keywords": ["0.8 multiplier", "1.0 multiplier", "cosine"],
    },
]

SYSTEM_WITH_CTX = """You are an expert Python developer reviewing a specific codebase.
Answer based ONLY on the provided code context. Be precise about exact values and names.

CODE CONTEXT:
{context}"""

SYSTEM_NO_CTX = (
    "You are an expert Python developer. "
    "Answer based on your general knowledge. Be precise about exact values."
)

def score_g2(answer: str, check_kw: list, halluc_kw: list):
    ans_lower = answer.lower()
    fra = 1.0 if any(kw.lower() in ans_lower for kw in check_kw) else 0.0
    hr  = 1.0 if any(kw.lower() in ans_lower for kw in halluc_kw) else 0.0
    combined = fra * (1.0 - hr)
    return fra, hr, combined

def run_g2():
    print("\n=== G2: CTX-specific Hard Scenarios (v2) ===")
    results = []
    fra_w_list, hr_w_list, comb_w_list = [], [], []
    fra_wo_list, hr_wo_list, comb_wo_list = [], [], []

    for sc in G2_SCENARIOS_HARD:
        sys_with = SYSTEM_WITH_CTX.format(context=sc["context"])
        ans_with    = call_llm(sys_with,     sc["instruction"])
        ans_without = call_llm(SYSTEM_NO_CTX, sc["instruction"])

        fra_w, hr_w, comb_w   = score_g2(ans_with,    sc["check_keywords"], sc["hallucination_keywords"])
        fra_wo, hr_wo, comb_wo = score_g2(ans_without, sc["check_keywords"], sc["hallucination_keywords"])

        fra_w_list.append(fra_w);   hr_w_list.append(hr_w);   comb_w_list.append(comb_w)
        fra_wo_list.append(fra_wo); hr_wo_list.append(hr_wo); comb_wo_list.append(comb_wo)

        results.append({
            "id": sc["id"],
            "score_with":    {"fra": fra_w,  "hr": hr_w,  "combined": comb_w},
            "score_without": {"fra": fra_wo, "hr": hr_wo, "combined": comb_wo},
            "ans_with":    ans_with[:200],
            "ans_without": ans_without[:200],
        })
        print(f"  {sc['id']}: WITH FRA={fra_w:.2f} HR={hr_w:.2f} comb={comb_w:.2f}  |  WITHOUT FRA={fra_wo:.2f} HR={hr_wo:.2f} comb={comb_wo:.2f}")

    n = len(G2_SCENARIOS_HARD)
    g2_with    = sum(comb_w_list)  / n
    g2_without = sum(comb_wo_list) / n
    g2_delta   = g2_with - g2_without
    avg_hr_w   = sum(hr_w_list)    / n
    avg_hr_wo  = sum(hr_wo_list)   / n

    print(f"\n  G2 WITH    = {g2_with:.3f}  (HR={avg_hr_w:.3f})")
    print(f"  G2 WITHOUT = {g2_without:.3f}  (HR={avg_hr_wo:.3f})")
    print(f"  G2 Delta   = {g2_delta:+.3f}  (v1 baseline: +0.000 ceiling / MiniMax: +0.375)")

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
    print("Nemotron-Cascade-2 CTX Downstream Eval v2 (hard G2)")
    print(f"Endpoint: {NEMOTRON_URL}")
    print("=" * 60)

    g1 = run_g1()
    g2 = run_g2()

    overall_with    = (g1["g1_with"]    + g2["g2_with"])    / 2
    overall_without = (g1["g1_without"] + g2["g2_without"]) / 2
    overall_delta   = overall_with - overall_without

    print("\n" + "=" * 60)
    print("v2 RESULTS vs BASELINES")
    print("=" * 60)
    print(f"  G1  WITH={g1['g1_with']:.3f}  WITHOUT={g1['g1_without']:.3f}  Δ={g1['g1_delta']:+.3f}")
    print(f"  G2  WITH={g2['g2_with']:.3f}  WITHOUT={g2['g2_without']:.3f}  Δ={g2['g2_delta']:+.3f}")
    print(f"  ALL WITH={overall_with:.3f}  WITHOUT={overall_without:.3f}  Δ={overall_delta:+.3f}")

    print("\nComparison:")
    print(f"  MiniMax G1 Δ=+0.781  |  Nemotron v1 Δ=+0.625  |  Nemotron v2 Δ={g1['g1_delta']:+.3f}")
    print(f"  MiniMax G2 Δ=+0.375  |  Nemotron v1 Δ=+0.000  |  Nemotron v2 Δ={g2['g2_delta']:+.3f}")

    output = {
        "model": NEMOTRON_MODEL,
        "version": "v2",
        "timestamp": datetime.datetime.now().isoformat(),
        "g1": g1,
        "g2": g2,
        "overall": {"with": overall_with, "without": overall_without, "delta": overall_delta},
    }

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/home/work/nemotron_ctx_v2_results_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] {out_path}")
    return output

if __name__ == "__main__":
    main()
