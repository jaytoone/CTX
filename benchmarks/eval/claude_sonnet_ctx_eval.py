#!/usr/bin/env python3
"""
CTX G1/G2 v4 Downstream Eval — Claude Sonnet 4.6 (claude CLI)

nemotron_ctx_eval_v4.py와 동일한 시나리오/스코어링 로직.
claude CLI subprocess 호출 → 격리된 독립 context로 평가.

G1: 세션 기억 재현 (8 scenarios)
G2: CTX-specific 지식 v4 (6 scenarios — h03/h04 재보정)

비교 기준:
  Nemotron-Cascade-2 (v4): G1 Δ=+1.000, G2 Δ=+1.000
  MiniMax M2.5       (v2): G1 Δ=+1.000, G2 Δ=+0.375
  Claude Sonnet 4.6  (v4): TBD ← THIS RUN
"""

import json
import os
import subprocess
import datetime

TIMEOUT = 120  # seconds per claude CLI call

# ── G1 시나리오 ─────────────────────────────────────────────────
G1_SCENARIOS = [
    {"id": "g1_01", "memory": "User prefers dark mode in all UIs. Set dark_mode=True by default.",
     "question": "What is my UI preference?", "keywords": ["dark mode", "dark_mode"]},
    {"id": "g1_02", "memory": "keyword R@3 score is 0.724 after BM25 routing optimization on 29 documents.",
     "question": "What is the current keyword R@3 score after BM25 routing optimization?", "keywords": ["0.724"]},
    {"id": "g1_03", "memory": "The eval benchmark has exactly 87 queries: 29 heading_exact, 29 heading_paraphrase, 29 keyword.",
     "question": "How many total queries are in the CTX benchmark?", "keywords": ["87"]},
    {"id": "g1_04", "memory": "SSH alias for NIPA server is 'nipa'. Nemotron runs on port 8010, Qwen on port 8000.",
     "question": "What port does the Nemotron model server run on in NIPA?", "keywords": ["8010"]},
    {"id": "g1_05", "memory": "CTX stands for Contextual Trigger eXtraction. It is a rule-based retrieval system with no LLM calls.",
     "question": "What does CTX stand for?", "keywords": ["contextual trigger extraction"]},
    {"id": "g1_06", "memory": "MiniMax M2.5 G1 result: WITH CTX=1.000, WITHOUT CTX=0.219, delta=+0.781.",
     "question": "What was the MiniMax G1 WITHOUT CTX score?", "keywords": ["0.219"]},
    {"id": "g1_07", "memory": "The CTX project uses rank_bm25 version 0.2.2. It was chosen over sklearn TfidfVectorizer because IDF hurts small domain-specific corpora.",
     "question": "What exact version of rank_bm25 does CTX use?", "keywords": ["0.2.2"]},
    {"id": "g1_08", "memory": "Over-anchoring phenomenon: when CTX shows current wrong implementation, LLM creativity is suppressed. Observed in 20% of Fix/Replace instruction scenarios.",
     "question": "What percentage of Fix/Replace scenarios show over-anchoring?", "keywords": ["20%", "20 percent"]},
]

# ── G2 v4 코드 스니펫 ────────────────────────────────────────────
CTX_BM25_BLEND_CODE = """\
# benchmarks/eval/doc_retrieval_eval_v2.py — rank_ctx_doc() BM25 blend logic
def rank_ctx_doc(query, docs, bm25_index=None):
    scores = {}
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

CTX_ROUTING_CODE = """\
# benchmarks/eval/doc_retrieval_eval_v2.py — query_type routing
def evaluate_ctx_doc(queries, docs, bm25_idx):
    results = []
    for q in queries:
        if q.query_type == 'keyword':
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

CTX_CONFIDENCE_FORMULA = """\
# src/trigger/trigger_classifier.py — _detect_semantic_concepts confidence calculation
    def _detect_semantic_concepts(self, prompt_lower):
        matched_keywords = [kw for kw in SEMANTIC_KEYWORDS if kw in prompt_lower]
        if matched_keywords:
            concept = None
            for pat in self._CONCEPT_EXTRACT_PATTERNS:
                m = pat.search(prompt_lower)
                if m:
                    candidate = m.group(1)
                    if len(candidate) > 2 and candidate not in self._COMMON_WORDS:
                        concept = candidate
                        break
            if concept is None:
                concept = max(matched_keywords, key=len)

            has_explicit_marker = any(kw in prompt_lower for kw in ("related to", "all code", "everything about"))
            if has_explicit_marker:
                confidence = min(0.85, 0.70 + len(matched_keywords) * 0.03)
            else:
                confidence = min(0.85, 0.50 + len(matched_keywords) * 0.10)
"""

CTX_CONCEPT_PATTERNS = """\
# src/trigger/trigger_classifier.py — _CONCEPT_EXTRACT_PATTERNS list
    _CONCEPT_EXTRACT_PATTERNS = [
        re.compile(r'related\\s+to\\s+([a-z_][a-z0-9_]*)', re.IGNORECASE),
        re.compile(r'everything\\s+about\\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'about\\s+([a-z_][a-z0-9_]{2,})', re.IGNORECASE),
        re.compile(r'handles?\\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'responsible\\s+for\\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
        re.compile(r'deals?\\s+with\\s+([a-z_][a-z0-9_]+)', re.IGNORECASE),
    ]
"""

CTX_IMPORT_GRAPH = r"""\
# src/retrieval/adaptive_trigger.py — _implicit_retrieve() BFS
    def _implicit_retrieve(self, query_file, k):
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

G2_SCENARIOS_V4 = [
    {"id": "g2_h01",
     "instruction": "In CTX's rank_ctx_doc(), what exact numeric threshold determines whether BM25 augmentation uses `current + norm * 0.2` vs `max(current, norm * 0.9)`?",
     "context": CTX_BM25_BLEND_CODE,
     "check_keywords": ["0.6", ">= 0.6"],
     "halluc_keywords": ["0.5 threshold", "0.7 threshold", "threshold of 0.5", "threshold of 0.7"]},
    {"id": "g2_h02",
     "instruction": "In CTX's benchmark routing for 'keyword' query_type, which exact class from rank_bm25 is imported and used? Write the exact import statement.",
     "context": CTX_ROUTING_CODE,
     "check_keywords": ["bm25l", "BM25L as TFOnlyBM25", "from rank_bm25 import BM25L"],
     "halluc_keywords": ["bm25plus is used", "uses bm25plus", "import BM25Okapi", "import BM25Plus"]},
    {"id": "g2_h03_v4",
     "instruction": "In CTX's _detect_semantic_concepts, when has_explicit_marker=True and exactly 3 semantic keywords are matched, what exact confidence value is computed? Show the formula step by step.",
     "context": CTX_CONFIDENCE_FORMULA,
     "check_keywords": ["0.79"],
     "halluc_keywords": ["0.82", "0.76 confidence", "0.80 confidence", "returns 0.85", "0.85 confidence"]},
    {"id": "g2_h04_v4",
     "instruction": "What is the 6th and final regex pattern string in CTX's _CONCEPT_EXTRACT_PATTERNS list (index 5)? Write the exact raw pattern string.",
     "context": CTX_CONCEPT_PATTERNS,
     "check_keywords": ["deals?", r"deals?\s"],
     "halluc_keywords": ["related\\s+to", "everything\\s+about", "handles?\\s", "responsible\\s+for", "related to", "everything about"]},
    {"id": "g2_h05",
     "instruction": "In CTX's _implicit_retrieve(), what is the maximum BFS traversal depth? Does the function include or exclude the starting query_file from the returned results?",
     "context": CTX_IMPORT_GRAPH,
     "check_keywords": ["depth 2", "depth > 2", "exclud"],
     "halluc_keywords": ["depth 3", "maximum depth of 3", "depth 5", "includes the query file"]},
    {"id": "g2_h06",
     "instruction": "In CTX's BM25 blend (current < 0.6 branch), what exact multiplier is applied to norm? What problem does this upper-bound prevent?",
     "context": CTX_BM25_BLEND_CODE,
     "check_keywords": ["0.9", "norm * 0.9"],
     "halluc_keywords": ["multiplier of 0.5", "multiplier of 0.8", "norm * 0.5", "norm * 0.8"]},
]


# ── LLM 호출 ────────────────────────────────────────────────────
def call_claude(prompt: str) -> str:
    """Run claude CLI from /tmp so CTX hook finds no Python files → clean context."""
    try:
        r = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=TIMEOUT,
            cwd="/tmp",  # no Python files → ctx_real_loader returns empty
        )
        # claude -p outputs to stdout; errors/hooks may appear in stderr
        out = r.stdout.strip()
        if not out:
            # fallback: parse stderr (some versions output there on timeout)
            err = r.stderr.strip()
            # strip hook output lines (start with '>' or '[GraphPrompt')
            lines = [l for l in err.splitlines()
                     if not l.startswith(">") and not l.startswith("[GraphPrompt")]
            out = "\n".join(lines).strip()
        return out if out else "[EMPTY]"
    except subprocess.TimeoutExpired:
        return "[TIMEOUT]"
    except Exception as e:
        return f"[ERROR:{e}]"


# ── 스코어링 ─────────────────────────────────────────────────────
def score_g1(answer: str, keywords: list) -> float:
    a = answer.lower()
    return 1.0 if any(kw.lower() in a for kw in keywords) else 0.0


def score_g2(answer: str, check_kw: list, halluc_kw: list):
    a = answer.lower()
    fra = 1.0 if any(kw.lower() in a for kw in check_kw) else 0.0
    hr  = 1.0 if any(kw.lower() in a for kw in halluc_kw) else 0.0
    return fra, hr, fra * (1.0 - hr)


# ── G1 실행 ──────────────────────────────────────────────────────
def run_g1() -> dict:
    print("\n=== G1: Cross-session Recall (8 scenarios) ===")
    results = []
    wi_scores, wo_scores = [], []

    for sc in G1_SCENARIOS:
        q = sc["question"]

        with_prompt = (
            f"You are a helpful assistant with access to persistent memory.\n"
            f"Answer concisely using the memory context.\n\n"
            f"MEMORY:\n{sc['memory']}\n\n"
            f"Question: {q}\nAnswer:"
        )
        wo_prompt = f"You are a helpful assistant. Answer concisely.\nQuestion: {q}\nAnswer:"

        print(f"  {sc['id']}... ", end="", flush=True)
        ans_w  = call_claude(with_prompt)
        ans_wo = call_claude(wo_prompt)

        sw  = score_g1(ans_w,  sc["keywords"])
        swo = score_g1(ans_wo, sc["keywords"])
        wi_scores.append(sw); wo_scores.append(swo)

        print(f"WITH={sw:.0f} WITHOUT={swo:.0f}")
        results.append({"id": sc["id"], "with": sw, "without": swo,
                        "ans_with": ans_w[:100], "ans_without": ans_wo[:100]})

    wi = sum(wi_scores) / len(wi_scores)
    wo = sum(wo_scores) / len(wo_scores)
    d  = wi - wo
    print(f"\n  G1 WITH={wi:.3f}  WITHOUT={wo:.3f}  Δ={d:+.3f}")
    return {"scenarios": results, "g1_with": wi, "g1_without": wo, "g1_delta": d}


# ── G2 실행 ──────────────────────────────────────────────────────
def run_g2() -> dict:
    print("\n=== G2: CTX-specific Knowledge v4 (6 scenarios) ===")
    results = []
    cw_list, cwo_list = [], []

    for sc in G2_SCENARIOS_V4:
        with_prompt = (
            f"You are an expert Python developer reviewing a specific codebase.\n"
            f"Answer based ONLY on the provided code. Be precise about exact values.\n\n"
            f"CODE CONTEXT:\n{sc['context']}\n\n"
            f"Question: {sc['instruction']}\nAnswer:"
        )
        wo_prompt = (
            f"You are an expert Python developer. Answer based on general knowledge.\n"
            f"Question: {sc['instruction']}\nAnswer:"
        )

        print(f"  {sc['id']}... ", end="", flush=True)
        ans_w  = call_claude(with_prompt)
        ans_wo = call_claude(wo_prompt)

        fra_w,  hr_w,  comb_w  = score_g2(ans_w,  sc["check_keywords"], sc["halluc_keywords"])
        fra_wo, hr_wo, comb_wo = score_g2(ans_wo, sc["check_keywords"], sc["halluc_keywords"])
        cw_list.append(comb_w); cwo_list.append(comb_wo)

        print(f"WITH FRA={fra_w:.0f} HR={hr_w:.0f} comb={comb_w:.2f} | WITHOUT FRA={fra_wo:.0f} HR={hr_wo:.0f} comb={comb_wo:.2f}")
        results.append({"id": sc["id"],
                        "with":    {"fra": fra_w,  "hr": hr_w,  "combined": comb_w},
                        "without": {"fra": fra_wo, "hr": hr_wo, "combined": comb_wo},
                        "ans_with": ans_w[:200], "ans_without": ans_wo[:200]})

    n = len(G2_SCENARIOS_V4)
    g2_w  = sum(cw_list)  / n
    g2_wo = sum(cwo_list) / n
    d     = g2_w - g2_wo
    print(f"\n  G2 WITH={g2_w:.3f}  WITHOUT={g2_wo:.3f}  Δ={d:+.3f}")
    return {"scenarios": results, "g2_with": g2_w, "g2_without": g2_wo, "g2_delta": d}


# ── Main ─────────────────────────────────────────────────────────
def main():
    print("=" * 65)
    print("CTX G1/G2 v4 Eval — Claude Sonnet 4.6 (claude CLI)")
    print(f"Timeout per call: {TIMEOUT}s")
    print("=" * 65)

    g1 = run_g1()
    g2 = run_g2()

    overall_w  = (g1["g1_with"]    + g2["g2_with"])    / 2
    overall_wo = (g1["g1_without"] + g2["g2_without"]) / 2
    overall_d  = overall_w - overall_wo

    print(f"\n{'='*65}")
    print("FINAL RESULTS — Claude Sonnet 4.6")
    print(f"{'='*65}")
    print(f"  G1  WITH={g1['g1_with']:.3f}  WITHOUT={g1['g1_without']:.3f}  Δ={g1['g1_delta']:+.3f}")
    print(f"  G2  WITH={g2['g2_with']:.3f}  WITHOUT={g2['g2_without']:.3f}  Δ={g2['g2_delta']:+.3f}")
    print(f"  Overall  WITH={overall_w:.3f}  WITHOUT={overall_wo:.3f}  Δ={overall_d:+.3f}")
    print(f"\n  Cross-model comparison:")
    print(f"    Nemotron-Cascade-2 (v4): G1 Δ=+1.000  G2 Δ=+1.000")
    print(f"    MiniMax M2.5       (v2): G1 Δ=+1.000  G2 Δ=+0.375")
    print(f"    Claude Sonnet 4.6  (v4): G1 Δ={g1['g1_delta']:+.3f}  G2 Δ={g2['g2_delta']:+.3f}  ← TODAY")

    soya_g1 = "PASS" if g1["g1_delta"] >= 1.0 else "FAIL"
    soya_g2 = "PASS" if g2["g2_delta"] >= 0.8 else "FAIL"
    print(f"\n  SOYA G1 (Δ≥1.000): {soya_g1}")
    print(f"  SOYA G2 (Δ≥0.800): {soya_g2}")

    out = {
        "model": "claude-sonnet-4-6",
        "benchmark": "G1-G2-v4",
        "timestamp": datetime.datetime.now().isoformat(),
        "g1": g1, "g2": g2,
        "overall_with": round(overall_w, 3),
        "overall_without": round(overall_wo, 3),
        "overall_delta": round(overall_d, 3),
        "soya_g1": soya_g1, "soya_g2": soya_g2,
    }

    out_path = os.path.join(os.path.dirname(__file__), "../results/sonnet_ctx_g1g2_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\n[SAVED] {out_path}")
    return out


if __name__ == "__main__":
    r = main()
    print(json.dumps({"g1_delta": r["g1"]["g1_delta"], "g2_delta": r["g2"]["g2_delta"],
                      "soya_g1": r["soya_g1"], "soya_g2": r["soya_g2"]}))
