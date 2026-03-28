#!/usr/bin/env python3
"""
Nemotron-Cascade-2 CTX Downstream LLM Evaluation v3
Scoring precision fixes from v2 analysis:
- h02: hallucination keyword narrowed ("bm25plus is used" not just "bm25plus")
- h03: hallucination keyword narrowed ("benchmarks' is included" not just "benchmarks")
- h04: hallucination keyword narrowed ("minimum length is 3" not "3 character")
- h05: hallucination keyword narrowed ("starting file is included" not "includes the starting")
- h06: hallucination keyword added ("0.5" — model says wrong multiplier)
- g1_07: replaced with more discriminating scenario
"""

import json
import requests
import datetime

NEMOTRON_URL   = "http://localhost:8010/v1/chat/completions"
NEMOTRON_MODEL = "nemotron-cascade-2"

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
    return "[NULL-CONTENT]" if content is None else content.strip()

# ---------------------------------------------------------------------------
# G1 — g1_07 replaced with CTX-specific scenario
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
        "question": "How many total queries are in the CTX benchmark?",
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
        "question": "What does CTX stand for?",
        "keywords": ["contextual trigger extraction"],
    },
    {
        "id": "g1_06",
        "memory": "MiniMax M2.5 G1 result: WITH CTX=1.000, WITHOUT CTX=0.219, delta=+0.781.",
        "question": "What was the MiniMax G1 WITHOUT CTX score?",
        "keywords": ["0.219"],
    },
    {
        "id": "g1_07",
        "memory": "The CTX project uses rank_bm25 version 0.2.2. It was chosen over sklearn TfidfVectorizer because IDF hurts small domain-specific corpora.",
        "question": "What exact version of rank_bm25 does CTX use?",
        "keywords": ["0.2.2"],
    },
    {
        "id": "g1_08",
        "memory": "Over-anchoring phenomenon: when CTX shows current wrong implementation, LLM creativity is suppressed. Observed in 20% of Fix/Replace instruction scenarios.",
        "question": "What percentage of Fix/Replace scenarios show over-anchoring?",
        "keywords": ["20%", "20 percent"],
    },
]

SYSTEM_WITH_MEMORY = """You are a helpful assistant with access to persistent memory.
Answer concisely using the memory context.

MEMORY:
{memory}"""

SYSTEM_NO_MEMORY = "You are a helpful assistant. Answer concisely."

def score_g1(answer, keywords):
    ans_lower = answer.lower()
    return 1.0 if any(kw.lower() in ans_lower for kw in keywords) else 0.0

def run_g1():
    print("\n=== G1: Cross-session Recall (v3) ===")
    results, with_scores, without_scores = [], [], []
    for sc in G1_SCENARIOS:
        q = sc["question"]
        ans_w  = call_llm(SYSTEM_WITH_MEMORY.format(memory=sc["memory"]), q, 150)
        ans_wo = call_llm(SYSTEM_NO_MEMORY, q, 150)
        s_w, s_wo = score_g1(ans_w, sc["keywords"]), score_g1(ans_wo, sc["keywords"])
        with_scores.append(s_w); without_scores.append(s_wo)
        results.append({"id": sc["id"], "score_with": s_w, "score_without": s_wo,
                        "ans_with": ans_w[:100], "ans_without": ans_wo[:100]})
        print(f"  {sc['id']}: WITH={s_w:.2f}  WITHOUT={s_wo:.2f}")
    g1_w  = sum(with_scores)    / len(with_scores)
    g1_wo = sum(without_scores) / len(without_scores)
    g1_d  = g1_w - g1_wo
    print(f"\n  G1 WITH={g1_w:.3f}  WITHOUT={g1_wo:.3f}  Δ={g1_d:+.3f}")
    return {"scenarios": results, "g1_with": g1_w, "g1_without": g1_wo, "g1_delta": g1_d}

# ---------------------------------------------------------------------------
# G2 v3 — precision-fixed scoring
# ---------------------------------------------------------------------------

CTX_BM25_BLEND_CODE = """
# benchmarks/eval/doc_retrieval_eval_v2.py — rank_ctx_doc() BM25 blend logic
def rank_ctx_doc(query: DocQuery, docs: List[DocFile], bm25_index=None) -> List[Tuple[str, float]]:
    scores: Dict[str, float] = {}
    for doc in docs:
        current = heading_match_score(query.text, doc.headings)
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
# Note: 'benchmarks' is NOT in this frozenset.
# doc_retrieval_eval_v2.py has its own _EXCLUDED_DIRS that DOES include 'benchmarks'.
"""

CTX_SYMBOL_INDEX = r"""
# src/retrieval/adaptive_trigger.py — concept indexing with regex
    def _index_concepts(self, rel_path: str, content: str) -> None:
        for m in re.finditer(r'\"\"\"(.*?)\"\"\"', content, re.DOTALL):
            words = re.findall(r'[a-z][a-z_]{3,}', m.group(1).lower())
            for w in words:
                if w not in _NON_SYMBOLS:
                    self.concept_index.setdefault(w, []).append(rel_path)

# The regex r'[a-z][a-z_]{3,}' means:
# - First char: one lowercase letter [a-z]
# - Remaining: 3 or more lowercase letters/underscores [a-z_]{3,}
# Minimum total length = 1 + 3 = 4 characters
"""

CTX_IMPORT_GRAPH = r"""
# src/retrieval/adaptive_trigger.py — _implicit_retrieve() BFS
    def _implicit_retrieve(self, query_file: str, k: int) -> List[str]:
        visited, queue = set(), [(query_file, 0)]
        while queue:
            node, depth = queue.pop(0)
            if node in visited or depth > 2:
                continue
            visited.add(node)
            for neighbor in self.import_graph.get(node, []):
                queue.append((neighbor, depth + 1))
        # Return visited files EXCLUDING the starting query_file
        return list(visited - {query_file})[:k]
"""

G2_SCENARIOS_V3 = [
    {
        "id": "g2_h01",
        "instruction": (
            "In CTX's doc_retrieval_eval_v2.py rank_ctx_doc(), what exact numeric threshold "
            "determines whether BM25 augmentation uses `current + norm * 0.2` vs "
            "`max(current, norm * 0.9)`?"
        ),
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.6", ">= 0.6"],
        "hallucination_keywords": ["0.5 threshold", "0.7 threshold", "0.8 threshold", "0.4 threshold",
                                    "threshold of 0.5", "threshold of 0.7", "threshold of 0.8"],
    },
    {
        "id": "g2_h02",
        "instruction": (
            "In CTX's benchmark routing for 'keyword' query_type, which exact class from rank_bm25 "
            "is imported and used? Write the exact import statement."
        ),
        "context": CTX_ROUTING_CODE,
        "check_keywords": ["bm25l", "BM25L as TFOnlyBM25", "from rank_bm25 import BM25L"],
        "hallucination_keywords": [
            "bm25plus is used", "uses bm25plus", "bm25okapi is used", "uses bm25okapi",
            "import BM25Okapi", "import BM25Plus",
        ],
    },
    {
        "id": "g2_h03",
        "instruction": (
            "In adaptive_trigger.py's _EXCLUDED_DIRS, is 'benchmarks' included or excluded? "
            "Is '.mypy_cache' included or excluded? Answer for adaptive_trigger.py specifically."
        ),
        "context": CTX_EXCLUDED_DIRS,
        "check_keywords": [".mypy_cache", "mypy_cache"],
        "hallucination_keywords": [
            "'benchmarks' is included", "benchmarks is included", "benchmarks': True",
            "benchmarks is in the frozenset", "benchmarks is present",
        ],
    },
    {
        "id": "g2_h04",
        "instruction": (
            "What is the minimum total character length for a word to pass CTX's "
            "_index_concepts() regex filter? Show the regex and explain the math."
        ),
        "context": CTX_SYMBOL_INDEX,
        "check_keywords": ["4", "1 + 3", "minimum total length", "four characters", "4 characters"],
        "hallucination_keywords": [
            "minimum length is 3", "minimum of 3", "at least 3 char", "3-character minimum",
            "minimum length of 3", "minimum 3 char",
        ],
    },
    {
        "id": "g2_h05",
        "instruction": (
            "In CTX's _implicit_retrieve(), what is the maximum BFS traversal depth? "
            "Does the function include or exclude the starting query_file from the returned results?"
        ),
        "context": CTX_IMPORT_GRAPH,
        "check_keywords": ["depth 2", "depth > 2", "exclud", "exclude"],
        "hallucination_keywords": [
            "depth 3", "maximum depth of 3", "depth limit of 3",
            "depth 5", "starting file is included in result",
            "includes the query file in the return",
        ],
    },
    {
        "id": "g2_h06",
        "instruction": (
            "In CTX's BM25 blend (current < 0.6 branch), what exact multiplier is applied "
            "to norm? What problem does this upper-bound prevent?"
        ),
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.9", "norm * 0.9", "false positive", "upper bound"],
        "hallucination_keywords": [
            "multiplier of 0.5", "multiplier of 0.8", "multiplier of 1.0",
            "0.5 multiplier", "0.8 multiplier", "norm * 0.5", "norm * 0.8",
        ],
    },
]

SYSTEM_WITH_CTX = """You are an expert Python developer reviewing a specific codebase.
Answer based ONLY on the provided code. Be precise about exact values and names.

CODE CONTEXT:
{context}"""

SYSTEM_NO_CTX = "You are an expert Python developer. Answer based on general knowledge. Be precise."

def score_g2(answer, check_kw, halluc_kw):
    ans_lower = answer.lower()
    fra = 1.0 if any(kw.lower() in ans_lower for kw in check_kw) else 0.0
    hr  = 1.0 if any(kw.lower() in ans_lower for kw in halluc_kw) else 0.0
    return fra, hr, fra * (1.0 - hr)

def run_g2():
    print("\n=== G2: CTX-specific Hard Scenarios (v3) ===")
    results = []
    comb_w_list, comb_wo_list = [], []
    hr_w_list, hr_wo_list = [], []

    for sc in G2_SCENARIOS_V3:
        ans_w  = call_llm(SYSTEM_WITH_CTX.format(context=sc["context"]), sc["instruction"])
        ans_wo = call_llm(SYSTEM_NO_CTX, sc["instruction"])
        fra_w,  hr_w,  comb_w  = score_g2(ans_w,  sc["check_keywords"], sc["hallucination_keywords"])
        fra_wo, hr_wo, comb_wo = score_g2(ans_wo, sc["check_keywords"], sc["hallucination_keywords"])
        comb_w_list.append(comb_w); comb_wo_list.append(comb_wo)
        hr_w_list.append(hr_w);    hr_wo_list.append(hr_wo)
        results.append({
            "id": sc["id"],
            "score_with":    {"fra": fra_w,  "hr": hr_w,  "combined": comb_w},
            "score_without": {"fra": fra_wo, "hr": hr_wo, "combined": comb_wo},
            "ans_with":    ans_w[:200],
            "ans_without": ans_wo[:200],
        })
        print(f"  {sc['id']}: WITH FRA={fra_w:.0f} HR={hr_w:.0f} comb={comb_w:.2f}  |  WITHOUT FRA={fra_wo:.0f} HR={hr_wo:.0f} comb={comb_wo:.2f}")

    n = len(G2_SCENARIOS_V3)
    g2_w  = sum(comb_w_list)  / n
    g2_wo = sum(comb_wo_list) / n
    g2_d  = g2_w - g2_wo
    avg_hr_w  = sum(hr_w_list)  / n
    avg_hr_wo = sum(hr_wo_list) / n
    print(f"\n  G2 WITH={g2_w:.3f} (HR={avg_hr_w:.3f})  WITHOUT={g2_wo:.3f} (HR={avg_hr_wo:.3f})  Δ={g2_d:+.3f}")
    print(f"  (v2 baseline: +0.167 combined / +0.333 FRA-only / MiniMax: +0.375)")
    return {"scenarios": results, "g2_with": g2_w, "g2_without": g2_wo, "g2_delta": g2_d,
            "hr_with": avg_hr_w, "hr_without": avg_hr_wo}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Nemotron-Cascade-2 CTX Downstream Eval v3 (precision fixes)")
    print(f"Endpoint: {NEMOTRON_URL}")
    print("=" * 60)

    g1 = run_g1()
    g2 = run_g2()

    overall_w  = (g1["g1_with"]    + g2["g2_with"])    / 2
    overall_wo = (g1["g1_without"] + g2["g2_without"]) / 2
    overall_d  = overall_w - overall_wo

    print("\n" + "=" * 60)
    print("FINAL COMPARISON (v3 vs baselines)")
    print("=" * 60)
    print(f"{'Metric':<28} {'v3':>8} {'v2':>8} {'MiniMax':>8}")
    print("-" * 56)
    v2 = {"G1 Δ": 0.875, "G2 Δ": 0.167, "Overall Δ": 0.521}
    mx = {"G1 Δ": 0.781, "G2 Δ": 0.375, "Overall Δ": 0.578}
    v3 = {"G1 Δ": g1["g1_delta"], "G2 Δ": g2["g2_delta"], "Overall Δ": overall_d}
    for k in v2:
        print(f"  {k:<26} {v3[k]:>+8.3f} {v2[k]:>+8.3f} {mx[k]:>+8.3f}")

    output = {
        "model": NEMOTRON_MODEL,
        "version": "v3",
        "timestamp": datetime.datetime.now().isoformat(),
        "g1": g1,
        "g2": g2,
        "overall": {"with": overall_w, "without": overall_wo, "delta": overall_d},
        "baselines": {"minimax": {"g1_delta": 0.781, "g2_delta": 0.375, "overall_delta": 0.578}},
    }
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = f"/home/work/nemotron_ctx_v3_results_{ts}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] {out_path}")
    return output

if __name__ == "__main__":
    main()
