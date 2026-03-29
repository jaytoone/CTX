#!/usr/bin/env python3
"""
CTX Unified G2 v4 Multi-Model Downstream Eval

모든 모델에 동일한 G2 v4 벤치마크로 평가 — FAT-2(G2 버전 불일치) 해결.

지원 모델:
  minimax    — MINIMAX_API_KEY / MINIMAX_BASE_URL (Anthropic-compat)
  nemotron   — NIPA localhost:8010 (OpenAI-compat vLLM)
  sonnet     — 내장 (self-eval: CTX 코드 직접 읽어 답변)

사용법:
  python unified_g2v4_eval.py --model minimax
  python unified_g2v4_eval.py --model nemotron
  python unified_g2v4_eval.py --model sonnet --self-eval
"""

import argparse
import datetime
import json
import os
import sys

# ── G2 v4 코드 스니펫 (claude_sonnet_ctx_eval.py와 동일) ─────────────
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
    {
        "id": "g2_h01",
        "instruction": "In CTX's rank_ctx_doc(), what exact numeric threshold determines whether BM25 augmentation uses `current + norm * 0.2` vs `max(current, norm * 0.9)`?",
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.6", ">= 0.6"],
        "halluc_keywords": ["0.5 threshold", "0.7 threshold", "threshold of 0.5", "threshold of 0.7"],
    },
    {
        "id": "g2_h02",
        "instruction": "In CTX's benchmark routing for 'keyword' query_type, which exact class from rank_bm25 is imported and used? Write the exact import statement.",
        "context": CTX_ROUTING_CODE,
        "check_keywords": ["bm25l", "BM25L as TFOnlyBM25", "from rank_bm25 import BM25L"],
        "halluc_keywords": ["bm25plus is used", "uses bm25plus", "import BM25Okapi", "import BM25Plus"],
    },
    {
        "id": "g2_h03_v4",
        "instruction": "In CTX's _detect_semantic_concepts, when has_explicit_marker=True and exactly 3 semantic keywords are matched, what exact confidence value is computed? Show the formula step by step.",
        "context": CTX_CONFIDENCE_FORMULA,
        "check_keywords": ["0.79"],
        "halluc_keywords": ["0.82", "0.76 confidence", "0.80 confidence", "returns 0.85", "0.85 confidence"],
    },
    {
        "id": "g2_h04_v4",
        "instruction": "What is the 6th and final regex pattern string in CTX's _CONCEPT_EXTRACT_PATTERNS list (index 5)? Write the exact raw pattern string.",
        "context": CTX_CONCEPT_PATTERNS,
        "check_keywords": ["deals?", r"deals?\s"],
        "halluc_keywords": ["related\\s+to", "everything\\s+about", "handles?\\s", "responsible\\s+for", "related to", "everything about"],
    },
    {
        "id": "g2_h05",
        "instruction": "In CTX's _implicit_retrieve(), what is the maximum BFS traversal depth? Does the function include or exclude the starting query_file from the returned results?",
        "context": CTX_IMPORT_GRAPH,
        "check_keywords": ["depth 2", "depth > 2", "exclud"],
        "halluc_keywords": ["depth 3", "maximum depth of 3", "depth 5", "includes the query file"],
    },
    {
        "id": "g2_h06",
        "instruction": "In CTX's BM25 blend (current < 0.6 branch), what exact multiplier is applied to norm? What problem does this upper-bound prevent?",
        "context": CTX_BM25_BLEND_CODE,
        "check_keywords": ["0.9", "norm * 0.9"],
        "halluc_keywords": ["multiplier of 0.5", "multiplier of 0.8", "norm * 0.5", "norm * 0.8"],
    },
]

SYSTEM_WITH_CTX = """You are an expert Python developer reviewing a specific codebase.
Answer based ONLY on the provided code. Be precise about exact values and names.

CODE CONTEXT:
{context}"""

SYSTEM_WITHOUT_CTX = "You are an expert Python developer. Answer based on your general knowledge."


# ── 스코어링 ──────────────────────────────────────────────────────────
def score_g2(answer: str, check_kw: list, halluc_kw: list):
    a = answer.lower()
    fra = 1.0 if any(kw.lower() in a for kw in check_kw) else 0.0
    halluc = any(kw.lower() in a for kw in halluc_kw)
    hr = 1.0 if halluc else 0.0
    combined = fra * (1 - hr)
    return {"fra": fra, "hr": hr, "combined": combined}


# ── 모델 호출 ─────────────────────────────────────────────────────────
def call_minimax(instruction: str, context: str | None, env: dict) -> str:
    try:
        import anthropic
    except ImportError:
        return "[ERROR: anthropic package not installed]"
    api_key = env.get("MINIMAX_API_KEY") or os.environ.get("MINIMAX_API_KEY", "")
    base_url = env.get("MINIMAX_BASE_URL") or os.environ.get("MINIMAX_BASE_URL", "")
    model = env.get("MINIMAX_MODEL") or os.environ.get("MINIMAX_MODEL", "MiniMax-Text-01")
    if not api_key:
        return "[ERROR: MINIMAX_API_KEY not set]"
    client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
    sys_msg = SYSTEM_WITH_CTX.format(context=context) if context else SYSTEM_WITHOUT_CTX
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            system=sys_msg,
            messages=[{"role": "user", "content": instruction}],
        )
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return "[EMPTY]"
    except Exception as e:
        return f"[ERROR:{e}]"


def call_nemotron(instruction: str, context: str | None, nipa_port: int = 8010) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return "[ERROR: openai package not installed]"
    client = OpenAI(api_key="EMPTY", base_url=f"http://localhost:{nipa_port}/v1")
    sys_msg = SYSTEM_WITH_CTX.format(context=context) if context else SYSTEM_WITHOUT_CTX
    try:
        resp = client.chat.completions.create(
            model="nvidia/Llama-3.1-Nemotron-Ultra-253B-v1",
            messages=[
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": instruction},
            ],
            max_tokens=512,
            temperature=0.0,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        return resp.choices[0].message.content or "[EMPTY]"
    except Exception as e:
        return f"[ERROR:{e}]"


def call_self_eval(instruction: str, context: str | None) -> str:
    """Self-eval: Claude Sonnet 4.6 answers directly (run inside Claude Code session)."""
    # This function is called manually — output printed for user to fill in
    prompt = f"[SELF-EVAL MODE]\n"
    if context:
        prompt += f"CODE CONTEXT:\n{context}\n\n"
    prompt += f"INSTRUCTION: {instruction}\nAnswer:"
    print(prompt)
    print(">>> Please provide answer (self-eval mode — fill in manually): ", end="")
    return "[SELF-EVAL: run interactively]"


# ── 실행 ──────────────────────────────────────────────────────────────
def run_eval(model: str, nipa_port: int = 8010) -> dict:
    """Run G2 v4 with and without context for the specified model."""
    # Load env
    env = {}
    env_path = os.path.expanduser("~/.claude/env/shared.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    line = line[7:]
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    v = v.strip('"').strip("'")
                    env[k.strip()] = v

    results = []
    for scenario in G2_SCENARIOS_V4:
        sid = scenario["id"]
        inst = scenario["instruction"]
        ctx = scenario["context"]
        check = scenario["check_keywords"]
        halluc = scenario["halluc_keywords"]

        print(f"[{sid}] Running WITH context...", flush=True)
        if model == "minimax":
            ans_with = call_minimax(inst, ctx, env)
        elif model == "nemotron":
            ans_with = call_nemotron(inst, ctx, nipa_port)
        else:
            ans_with = "[SELF-EVAL]"

        print(f"[{sid}] Running WITHOUT context...", flush=True)
        if model == "minimax":
            ans_without = call_minimax(inst, None, env)
        elif model == "nemotron":
            ans_without = call_nemotron(inst, None, nipa_port)
        else:
            ans_without = "[SELF-EVAL]"

        s_with = score_g2(ans_with, check, halluc)
        s_without = score_g2(ans_without, check, halluc)

        results.append({
            "id": sid,
            "with_score": s_with["combined"],
            "without_score": s_without["combined"],
            "with_fra": s_with["fra"],
            "without_fra": s_without["fra"],
            "with_hr": s_with["hr"],
            "without_hr": s_without["hr"],
            "with_answer": ans_with[:200],
            "without_answer": ans_without[:200],
        })
        print(f"  WITH={s_with['combined']:.3f} (FRA={s_with['fra']}, HR={s_with['hr']})  "
              f"WITHOUT={s_without['combined']:.3f}")

    n = len(results)
    with_mean = sum(r["with_score"] for r in results) / n
    without_mean = sum(r["without_score"] for r in results) / n
    delta = with_mean - without_mean

    summary = {
        "model": model,
        "benchmark_version": "G2_v4",
        "timestamp": datetime.datetime.now().isoformat(),
        "n_scenarios": n,
        "with_mean": round(with_mean, 4),
        "without_mean": round(without_mean, 4),
        "delta": round(delta, 4),
        "scenarios": results,
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["minimax", "nemotron", "sonnet"], default="minimax")
    parser.add_argument("--nipa-port", type=int, default=8010)
    parser.add_argument("--output", help="Output JSON path (default: auto)")
    args = parser.parse_args()

    print(f"=== CTX Unified G2 v4 Eval — {args.model} ===")
    result = run_eval(args.model, args.nipa_port)

    print(f"\n=== SUMMARY ===")
    print(f"Model: {result['model']} | Benchmark: {result['benchmark_version']}")
    print(f"WITH CTX:    {result['with_mean']:.4f}")
    print(f"WITHOUT CTX: {result['without_mean']:.4f}")
    print(f"Delta:       {result['delta']:+.4f}")

    out = args.output or f"/home/jayone/Project/CTX/benchmarks/results/g2v4_{args.model}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
