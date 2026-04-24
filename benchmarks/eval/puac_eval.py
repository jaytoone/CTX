"""
puac_eval.py — Tier 2 "Tangible MERIDIAN" evaluation harness.

Measures PUAC (Per-prompt Utility & Attribution Composite) for CTX memory.

  PUAC(p) = 0.5 · CL(p) + 0.3 · AR(p) - 0.2 · PRR(p)

  CL  (Causal Lift)              = judge(full) - judge(empty)
  AR  (Attribution Rate)         = referenced_items / injected_items (substring/semantic)
  PRR (Post-Rationalization)     = 1 if (AR >= 0.50 AND CL <= 0.05) else 0
                                    (per-prompt binary; averaged to a rate)
  NHR (Noise Harm Rate, report)  = judge(noise) < judge(empty)   — not in PUAC, for audit
  OAR (Over-Anchoring, report)   = judge(gold) > judge(full)      — not in PUAC, for audit

Implementation notes:
  * 4-condition runner: FULL / EMPTY / GOLD-ONLY / NOISE-ONLY. EMPTY and FULL
    are mandatory; GOLD/NOISE are optional (require ground-truth labels).
  * LLM judge: pairwise (Claude temp=0) returning [0,1] quality score.
    CrowdRAG-25 (SIGIR 2025) shows LLM-pairwise tracks human-pairwise at r≥0.85.
  * AR reuses utility-rate.py substring+semantic match. This file packages the
    same algorithm so the harness can score responses independent of the hook.
  * PRR approximation: Wallat et al. ICTIR 2025 requires mid-generation doc
    removal which Claude API doesn't support. We use the CL-AR dissociation
    test: high AR with near-zero CL = post-rationalization.

Reuses:
  * downstream_llm_eval.get_llm_client / call_llm (MiniMax + Anthropic)
  * utility-rate match algorithm (inlined as _attribution_match)

Usage:
  python3 benchmarks/eval/puac_eval.py --prompts sample_prompts.json --out results.json
  python3 benchmarks/eval/puac_eval.py --smoke   # N=3 built-in smoke test
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "benchmarks" / "eval"))

# Reuse the existing LLM client from downstream_llm_eval (MiniMax + Anthropic)
from downstream_llm_eval import get_llm_client, call_llm   # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# Data structures
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class InjectionItem:
    """A single memory item that CTX (or any retriever) injected into context."""
    block: str             # "g1" | "g2_docs" | "g2_prefetch" | ...
    subject: str           # human-readable 1-line description
    tokens: List[str] = field(default_factory=list)   # distinctive match tokens
    date: Optional[str] = None   # ISO date if applicable (age-band tracking)


@dataclass
class Prompt:
    """One prompt to evaluate. `injected` is what CTX actually surfaced.
    `gold` (optional) = hand-curated "ideal" subset for GOLD condition.
    `noise` (optional) = deliberately wrong items for NOISE condition."""
    prompt_id: str
    prompt_text: str
    injected: List[InjectionItem]
    gold: Optional[List[InjectionItem]] = None
    noise: Optional[List[InjectionItem]] = None


@dataclass
class ConditionResult:
    condition: str                 # "FULL" | "EMPTY" | "GOLD" | "NOISE"
    response: str
    judge_score: float             # [0,1] quality
    n_injected: int                # how many items were in context for this condition
    n_referenced: int              # of those, how many were referenced (AR numerator)


@dataclass
class PUACResult:
    prompt_id: str
    prompt_text: str
    conditions: Dict[str, ConditionResult]   # keyed by condition name
    CL: float
    AR: float
    PRR: int                       # binary per-prompt (0 or 1)
    NHR: int                       # binary (noise worse than empty?)
    OAR: int                       # binary (gold better than full?)
    PUAC: float
    latency_sec: float


# ══════════════════════════════════════════════════════════════════════════
# Attribution — AR computation (mirrors utility-rate.py)
# ══════════════════════════════════════════════════════════════════════════

def _attribution_match(response: str, items: List[InjectionItem]) -> Tuple[int, int]:
    """Substring match: count items whose tokens appear in response.
    Returns (n_referenced, n_injected). Token min-length 4 matches utility-rate.py."""
    if not items:
        return 0, 0
    response_l = response.lower()
    n_ref = 0
    for it in items:
        tokens = it.tokens or []
        # Also derive tokens from subject if none provided
        if not tokens and it.subject:
            tokens = [t for t in re.findall(r"\w+", it.subject.lower()) if len(t) >= 4]
        hit = any(len(t) >= 4 and t.lower() in response_l for t in tokens)
        if hit:
            n_ref += 1
    return n_ref, len(items)


# ══════════════════════════════════════════════════════════════════════════
# LLM judge — pairwise quality score [0,1]
# ══════════════════════════════════════════════════════════════════════════

JUDGE_SYSTEM = (
    "You are an impartial rater evaluating the quality of an AI response to a "
    "coding/engineering prompt. Rate purely on how well the response answers "
    "the prompt — ignore style, emojis, and politeness. Use the full [0.00, 1.00] "
    "range. Output EXACTLY one floating-point number between 0.00 and 1.00 on "
    "the first line. No prose, no explanation."
)

JUDGE_PROMPT_TMPL = """Prompt:
---
{prompt}
---

Response to rate:
---
{response}
---

Output one number only (0.00–1.00):"""


def llm_judge(client, prompt_text: str, response: str, model: str = "",
              judge_model: str = "") -> float:
    """LLM judge in pairwise-compatible absolute scale [0,1].
    temperature=0 (by client default), returns single float.

    Reasoning models (MiniMax M2.5) need ~4K tokens for the ThinkingBlock.
    At ≤2K the judge often produces partial/truncated answers (empirically 0.20
    at 2K vs 0.80 at 4K on same input). For fast/cheap eval, pass a
    non-reasoning model via `judge_model` (e.g. Claude Haiku)."""
    out = call_llm(client, JUDGE_SYSTEM,
                   JUDGE_PROMPT_TMPL.format(prompt=prompt_text, response=response),
                   model=(judge_model or model), max_tokens=4096)
    # Guard against bracketed error tokens ([NO-TEXT-BLOCK], [LLM-ERROR], [NO-CLIENT])
    if out.startswith("["):
        return 0.0
    # Scan every line — last numeric line wins (final answer after reasoning)
    last_val: Optional[float] = None
    for line in out.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.search(r"-?\d*\.?\d+", s)
        if m:
            try:
                v = float(m.group(0))
                last_val = max(0.0, min(1.0, v))
            except ValueError:
                pass
    return last_val if last_val is not None else 0.0


# ══════════════════════════════════════════════════════════════════════════
# Context builders — one per condition
# ══════════════════════════════════════════════════════════════════════════

def _context_block(items: List[InjectionItem]) -> str:
    """Render items as the same kind of block CTX's hooks emit."""
    if not items:
        return ""
    by_block: Dict[str, List[str]] = {}
    for it in items:
        by_block.setdefault(it.block or "memory", []).append(f"  > {it.subject}")
    parts = []
    for block, lines in by_block.items():
        header = {
            "g1":          "[RECENT DECISIONS]",
            "g2_docs":     "[G2-DOCS]",
            "g2_prefetch": "[G2-PREFETCH]",
        }.get(block, f"[{block.upper()}]")
        parts.append(header + "\n" + "\n".join(lines))
    return "\n\n".join(parts)


def build_user_msg(prompt_text: str, ctx_items: List[InjectionItem]) -> str:
    ctx = _context_block(ctx_items)
    if ctx:
        return f"{ctx}\n\n---\n\n{prompt_text}"
    return prompt_text


# ══════════════════════════════════════════════════════════════════════════
# Single-prompt evaluation (4 conditions)
# ══════════════════════════════════════════════════════════════════════════

RESPONSE_SYSTEM = (
    "You are a helpful software engineer. Answer the user's prompt directly and "
    "concisely. If context is provided above the prompt, incorporate it when "
    "relevant. Be specific."
)


def run_prompt(
    client,
    p: Prompt,
    conditions: List[str] = ("FULL", "EMPTY"),
    model: str = "",
    judge_model: str = "",
    response_max_tokens: int = 384,
) -> PUACResult:
    """Run a single prompt through each requested condition + compute PUAC."""
    t0 = time.time()
    cond_items: Dict[str, List[InjectionItem]] = {
        "FULL":  p.injected,
        "EMPTY": [],
        "GOLD":  p.gold or [],
        "NOISE": p.noise or [],
    }
    results: Dict[str, ConditionResult] = {}
    for cond in conditions:
        items = cond_items[cond]
        user_msg = build_user_msg(p.prompt_text, items)
        resp = call_llm(client, RESPONSE_SYSTEM, user_msg,
                        model=model, max_tokens=response_max_tokens)
        score = llm_judge(client, p.prompt_text, resp,
                          model=model, judge_model=judge_model)
        n_ref, n_inj = _attribution_match(resp, items)
        results[cond] = ConditionResult(
            condition=cond, response=resp, judge_score=score,
            n_injected=n_inj, n_referenced=n_ref,
        )

    # Metric derivations (only if required conditions present)
    CL = 0.0
    if "FULL" in results and "EMPTY" in results:
        CL = results["FULL"].judge_score - results["EMPTY"].judge_score

    AR = 0.0
    if "FULL" in results and results["FULL"].n_injected > 0:
        AR = results["FULL"].n_referenced / results["FULL"].n_injected

    # PRR binary — high attribution but no causal lift
    PRR = 1 if (AR >= 0.50 and CL <= 0.05) else 0

    NHR = 0
    if "NOISE" in results and "EMPTY" in results:
        NHR = 1 if results["NOISE"].judge_score < results["EMPTY"].judge_score else 0

    OAR = 0
    if "GOLD" in results and "FULL" in results:
        OAR = 1 if results["GOLD"].judge_score > results["FULL"].judge_score + 0.05 else 0

    # Final PUAC composite
    PUAC = 0.5 * CL + 0.3 * AR - 0.2 * PRR

    return PUACResult(
        prompt_id=p.prompt_id,
        prompt_text=p.prompt_text,
        conditions=results,
        CL=round(CL, 4),
        AR=round(AR, 4),
        PRR=PRR,
        NHR=NHR,
        OAR=OAR,
        PUAC=round(PUAC, 4),
        latency_sec=round(time.time() - t0, 2),
    )


# ══════════════════════════════════════════════════════════════════════════
# Batch aggregation
# ══════════════════════════════════════════════════════════════════════════

def aggregate(results: List[PUACResult]) -> Dict:
    if not results:
        return {"n": 0}
    n = len(results)
    def mean(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0.0
    return {
        "n": n,
        "mean_CL": mean([r.CL for r in results]),
        "mean_AR": mean([r.AR for r in results]),
        "PRR_rate": round(sum(r.PRR for r in results) / n, 4),
        "NHR_rate": round(sum(r.NHR for r in results) / n, 4),
        "OAR_rate": round(sum(r.OAR for r in results) / n, 4),
        "mean_PUAC": mean([r.PUAC for r in results]),
        "total_latency_sec": round(sum(r.latency_sec for r in results), 2),
    }


# ══════════════════════════════════════════════════════════════════════════
# I/O helpers + smoke set
# ══════════════════════════════════════════════════════════════════════════

def load_prompts(path: Path) -> List[Prompt]:
    data = json.loads(path.read_text())
    prompts: List[Prompt] = []
    for d in data:
        def mk_items(key):
            return [InjectionItem(**it) for it in (d.get(key) or [])]
        prompts.append(Prompt(
            prompt_id=d["prompt_id"],
            prompt_text=d["prompt_text"],
            injected=mk_items("injected"),
            gold=mk_items("gold") or None,
            noise=mk_items("noise") or None,
        ))
    return prompts


def smoke_prompts() -> List[Prompt]:
    """3 minimal prompts to verify the pipeline end-to-end without external data."""
    return [
        Prompt(
            prompt_id="smoke-1",
            prompt_text="In one line: why did CTX replace TF-IDF with BM25?",
            injected=[
                InjectionItem(block="g1", subject="BM25 replacement: TF-IDF underperformed on small corpora due to IDF degradation",
                              tokens=["bm25", "tf-idf", "idf"], date="2026-03-27"),
                InjectionItem(block="g2_docs", subject="doc_retrieval_eval_v2.py shows Recall@3 0.379→0.655",
                              tokens=["doc_retrieval_eval_v2", "recall"]),
            ],
        ),
        Prompt(
            prompt_id="smoke-2",
            prompt_text="In one line: what does vec-daemon do?",
            injected=[
                InjectionItem(block="g2_docs", subject="vec-daemon serves multilingual-e5-small embeddings over Unix socket",
                              tokens=["vec-daemon", "multilingual", "e5-small"]),
            ],
        ),
        Prompt(
            prompt_id="smoke-3",
            prompt_text="In one line: what is PUAC?",
            injected=[
                InjectionItem(block="g1", subject="PUAC = 0.5·CL + 0.3·AR - 0.2·PRR — per-prompt utility composite",
                              tokens=["puac", "utility", "composite"]),
            ],
        ),
    ]


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="PUAC evaluation harness (Tier 2)")
    ap.add_argument("--prompts", type=Path, help="JSON file with prompts")
    ap.add_argument("--out", type=Path, default=Path("benchmarks/results/puac_eval.json"))
    ap.add_argument("--smoke", action="store_true", help="run built-in 3-prompt smoke test")
    ap.add_argument("--conditions", default="FULL,EMPTY",
                    help="comma-separated subset of FULL,EMPTY,GOLD,NOISE")
    ap.add_argument("--model", default="", help="response model (override MINIMAX_MODEL / default Claude)")
    ap.add_argument("--judge-model", default="", help="judge model (defaults to --model). Use a non-reasoning model (e.g. claude-haiku-4-5) for faster judging.")
    ap.add_argument("--max-prompts", type=int, default=0, help="cap N (0 = all)")
    args = ap.parse_args()

    prompts: List[Prompt]
    if args.smoke:
        prompts = smoke_prompts()
    elif args.prompts:
        prompts = load_prompts(args.prompts)
    else:
        ap.error("either --smoke or --prompts required")

    if args.max_prompts:
        prompts = prompts[: args.max_prompts]

    conditions = [c.strip().upper() for c in args.conditions.split(",") if c.strip()]
    client = get_llm_client()
    if client is None:
        print("[ERROR] No LLM client (set MINIMAX_API_KEY+URL or ANTHROPIC_API_KEY)", file=sys.stderr)
        sys.exit(2)

    print(f"[PUAC] running {len(prompts)} prompts × {len(conditions)} conditions "
          f"= {len(prompts)*len(conditions)*2} LLM calls (response+judge)")

    results: List[PUACResult] = []
    for i, p in enumerate(prompts, 1):
        print(f"  [{i}/{len(prompts)}] {p.prompt_id}", flush=True)
        r = run_prompt(client, p, conditions=conditions,
                       model=args.model, judge_model=args.judge_model)
        results.append(r)
        print(f"    CL={r.CL:+.3f}  AR={r.AR:.3f}  PRR={r.PRR}  PUAC={r.PUAC:+.3f}  ({r.latency_sec:.1f}s)")

    agg = aggregate(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": int(time.time()),
        "n": len(results),
        "conditions": conditions,
        "aggregate": agg,
        "per_prompt": [asdict(r) for r in results],
    }
    args.out.write_text(json.dumps(payload, indent=2))
    print(f"\n[PUAC] wrote {args.out}")
    print(f"  aggregate: {json.dumps(agg)}")


if __name__ == "__main__":
    main()
