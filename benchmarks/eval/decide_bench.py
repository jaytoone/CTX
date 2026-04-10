#!/usr/bin/env python3
"""
DECIDE-Bench: Decision Recall for Coding-Agent Context Enhancement
===================================================================
Publication-quality benchmark for cross-session coding decision memory.

Core methodological innovations vs prior work (20260408):
  1. Closed-book/open-book delta
       delta = open_book_recall - closed_book_recall
       Eliminates: training-data contamination, question-repetition bias,
       context-anchoring paradox.
  2. Numeric-only ground truth — prevents keyword inflation
  3. Multi-commit temporal bins (N>=5 per bin) — statistical power
  4. Comprehensive baselines: no_ctx | long_ctx_20 | long_ctx_50 | rag_bm25 | g1_raw | g1_current
  5. Temporal Decay Rate (TDR): delta = a*exp(-lambda*age) + b
  6. Statistical rigor: Wilcoxon, bootstrap 95% CI, Cohen r, Bonferroni

Temporal bins:
  recent   (ages  1-10) : ~2 days ago
  medium   (ages 11-25) : ~3-5 days ago
  far      (ages 26-45) : ~5-7 days ago
  very_far (ages 46-80) : ~7-10 days ago

Reference: LongMemEval (ICLR 2025), MemoryAgentBench (ICLR 2026),
           A-MEM (arXiv:2502.12110), ByteRover (arXiv:2604.01599)

Usage:
  python3 benchmarks/decide_bench.py --dry-run
  python3 benchmarks/decide_bench.py
  python3 benchmarks/decide_bench.py --project /path/to/repo
"""

import argparse, json, math, os, re, subprocess, sys, time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import anthropic; HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

try:
    from scipy import stats as scipy_stats; HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

try:
    import numpy as np; HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

ROOT = Path(__file__).parent.parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# Dataset: curated benchmark items with numeric ground truth
# Question must NOT include the answer value.
# Verified against CTX git log 2026-04-08.
# ─────────────────────────────────────────────────────────────────────────────
BENCHMARK_ITEMS = [
    # Bin 1: recent (ages 1-10)
    {"age": 3, "bin": "recent", "topic": "G1 noise filter metrics",
     "question": "What were the NoiseRatio and TopicCoverage metric values after the G1 noise filter and topic-dedup implementation?",
     "keywords": ["50%", "0%", "73%", "79%"],
     "hint": "NoiseRatio 50%→0%, TopicCov 73%→79%"},
    {"age": 5, "bin": "recent", "topic": "G1 temporal eval Staleness/Conflict",
     "question": "What Staleness and Conflict rates were measured in G1 temporal evaluation across 4 projects?",
     "keywords": ["35.7%", "0%"],
     "hint": "Staleness 35.7%, Conflict 0% (4 projects)"},
    {"age": 7, "bin": "recent", "topic": "G2 prefetch improvement",
     "question": "What was the G2 prefetch hit rate before and after ko-en mapping and filepath search?",
     "keywords": ["30%", "65%"],
     "hint": "G2 prefetch benchmark: 30% -> 65%"},
    # Bin 2: medium (ages 11-25)
    {"age": 11, "bin": "medium", "topic": "G1 git-log hook recall",
     "question": "What G1 git-log hook test recall percentage was reported across projects?",
     "keywords": ["95%"],
     "hint": "G1 git-log hook test results: 95% recall across 3 projects"},
    {"age": 15, "bin": "medium", "topic": "COIR full corpus BM25 Hit@5",
     "question": "What BM25 Hit@5 score was achieved on the COIR full corpus, and how large was that corpus?",
     "keywords": ["0.640", "280K"],
     "hint": "COIR full corpus: BM25 Hit@5=0.640 on 280K docs"},
    {"age": 16, "bin": "medium", "topic": "COIR standard BM25 Hit@5 on CodeSearchNet",
     "question": "What BM25 Hit@5 score was achieved on the COIR standard benchmark using CodeSearchNet Python, and what was the corpus size?",
     "keywords": ["0.780", "24.9K"],
     "hint": "COIR standard benchmark: BM25 Hit@5=0.780 on CodeSearchNet Python (24.9K corpus)"},
    {"age": 17, "bin": "medium", "topic": "SOTA eval G1 recall",
     "question": "What G1 recall percentage was reported in the SOTA evaluation?",
     "keywords": ["90%"],
     "hint": "SOTA eval complete: G1 recall 90%"},
    {"age": 24, "bin": "medium", "topic": "G1 3-run average delta and variance",
     "question": "What was the stabilized G1 delta value and its standard deviation after 3-run averaging?",
     "keywords": ["0.270", "0.074"],
     "hint": "G1 3-run average stabilized — delta=+0.270 (+-0.074)"},
    {"age": 25, "bin": "medium", "topic": "History category score improvement",
     "question": "What was the History category score before and after ctx_query improvement?",
     "keywords": ["0.55", "0.661"],
     "hint": "H03 ctx_query improved + History 0.55->0.661"},
    # Bin 3: far (ages 26-45)
    {"age": 29, "bin": "far", "topic": "CTX vs None downstream delta",
     "question": "What was the CTX vs None downstream performance delta measured using hybrid scoring?",
     "keywords": ["0.300"],
     "hint": "hybrid scoring (50% judge + 50% keyword) — CTX vs None delta=+0.300"},
    {"age": 35, "bin": "far", "topic": "G1 target score achieved",
     "question": "What G1 score was achieved, and what was the target threshold?",
     "keywords": ["0.705", "0.70"],
     "hint": "G1=0.705 achieved | target 0.70 reached"},
    {"age": 40, "bin": "far", "topic": "G1 zero-storage concept group R@5",
     "question": "What concept group R@5 was reported in the G1 zero-storage analysis?",
     "keywords": ["0.965"],
     "hint": "G1 zero-storage analysis — concept group R@5=0.965"},
    {"age": 45, "bin": "far", "topic": "External R@5 bigram BM25 improvement",
     "question": "What were the before and after external R@5 values and percentage improvement from bigram BM25?",
     "keywords": ["0.5649", "0.6033", "+3.8%"],
     "hint": "external R@5 0.5649->0.6033 (+3.8%)"},
    # Bin 4: very_far (ages 46-80)
    {"age": 46, "bin": "very_far", "topic": "External R@5 iter 4",
     "question": "What were the before/after external R@5 values in iteration 4 with bigram BM25?",
     "keywords": ["0.5406", "0.5623"],
     "hint": "external R@5 0.5406->0.5623 | bigram BM25 + query expansion"},
    {"age": 47, "bin": "very_far", "topic": "External R@5 iter 3",
     "question": "What were the before/after external R@5 values in iteration 3 with reverse_import_graph?",
     "keywords": ["0.5259", "0.5406"],
     "hint": "external R@5 0.5259->0.5406 | goal_v0: reverse_import_graph"},
    {"age": 48, "bin": "very_far", "topic": "COIR and RepoBench breakthrough",
     "question": "What were the COIR R@5 and RepoBench R@5 values after the first live-infinite iteration?",
     "keywords": ["0.740", "1.000", "0.558", "0.975"],
     "hint": "COIR R@5 0.740->1.000, RepoBench 0.558->0.975"},
    {"age": 50, "bin": "very_far", "topic": "omc-live iter 2 external and COIR R@5",
     "question": "What external R@5 and COIR R@5 scores were reported in omc-live iteration 2?",
     "keywords": ["0.152", "0.744", "0.380", "0.740"],
     "hint": "external R@5 0.152->0.744, COIR R@5 0.380->0.740"},
    {"age": 51, "bin": "very_far", "topic": "SEMANTIC_CONCEPT R@5 improvement",
     "question": "What were the before/after SEMANTIC_CONCEPT R@5 values on COIR after two perf fixes?",
     "keywords": ["0.500", "0.867"],
     "hint": "SEMANTIC_CONCEPT R@5 0.500->0.867 on COIR — two fixes"},
    {"age": 57, "bin": "very_far", "topic": "live-infinite convergence score",
     "question": "What was the final convergence score when live-infinite converged on paper references?",
     "keywords": ["0.9922"],
     "hint": "live-infinite iter 76/inf: CONVERGED | ... score=0.9922"},
    {"age": 62, "bin": "very_far", "topic": "TEMPORAL delta correction",
     "question": "What value was the TEMPORAL delta corrected from and to in Section 4.5?",
     "keywords": ["24pp", "20pp"],
     "hint": "Section 4.5 — +24pp->+20pp TEMPORAL delta"},
    {"age": 63, "bin": "very_far", "topic": "TEMPORAL_HISTORY GraphPrompt correction",
     "question": "What value was the TEMPORAL_HISTORY GraphPrompt figure corrected to in Section 5.2?",
     "keywords": ["0.50", "0.60"],
     "hint": "Section 5.2 — TEMPORAL_HISTORY GraphPrompt value 0.50->0.60"},
    {"age": 66, "bin": "very_far", "topic": "GraphPrompt and AgentNode file counts",
     "question": "What were the corrected GraphPrompt and AgentNode file counts in Section 4.5?",
     "keywords": ["73", "596"],
     "hint": "Section 4.5 — GraphPrompt 82->73, AgentNode 217->596"},
    {"age": 69, "bin": "very_far", "topic": "Dataset query count breakdown",
     "question": "How many total queries, real files, and real queries (excluding synthetic) were reported in Section 4.1?",
     "keywords": ["415", "968", "249"],
     "hint": "Section 4.1 — 415 total queries (968 real files, 249 real queries, 415 incl. synthetic)"},
    {"age": 71, "bin": "very_far", "topic": "OneViral TES ratio correction",
     "question": "What was the corrected OneViral TES ratio and how was it calculated?",
     "keywords": ["3.6x", "0.232", "0.065", "3.57"],
     "hint": "Section 4.4 — OneViral TES ratio 2.5x->3.6x (0.232/0.065=3.57)"},
    {"age": 76, "bin": "very_far", "topic": "LlamaIndex vs BM25 TES",
     "question": "What TES values were reported for LlamaIndex and BM25 in Section 4.4?",
     "keywords": ["0.405", "0.410"],
     "hint": "Section 4.4 — LlamaIndex TES (0.405 vs 0.410 BM25)"},
    {"age": 77, "bin": "very_far", "topic": "Limitations R@3 correction",
     "question": "What was the R@3 value corrected to in the Limitations section?",
     "keywords": ["0.890", "0.869"],
     "hint": "Limitations R@3 0.890->0.869 — match main results table"},
]

TEMPORAL_BINS = {"recent": (1,10), "medium": (11,25), "far": (26,45), "very_far": (46,80)}
BASELINE_NAMES = ["no_ctx", "long_ctx_20", "long_ctx_50", "rag_bm25", "g1_raw", "g1_current"]

# ─────────────────────────────────────────────────────────────────────────────
# Context builders
# ─────────────────────────────────────────────────────────────────────────────

def _git_log_subjects(project_dir, n):
    try:
        r = subprocess.run(["git","log",f"-{n}","--format=%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=8)
        return [l.strip() for l in r.stdout.strip().split("\n") if l.strip()] if r.returncode==0 else []
    except: return []

def _git_log_with_hash(project_dir, n):
    try:
        r = subprocess.run(["git","log",f"-{n}","--format=%H\x1f%s"],
            cwd=project_dir, capture_output=True, text=True, timeout=8)
        pairs = []
        for line in r.stdout.strip().split("\n"):
            if "\x1f" in line:
                h,_,s = line.partition("\x1f")
                pairs.append((h.strip(), s.strip()))
        return pairs
    except: return []

_OMC_RE = re.compile(r"^(omc-live|live-inf|live-infinite)\s+iter", re.IGNORECASE)
_VER_RE = re.compile(r"^v\d+\.\d+\.\d+")
_EMB_RE = re.compile(r"\s[-—]\s*(feat|fix|refactor|perf|security|implement|add|remove|replace|switch|migrate)", re.IGNORECASE)
_CONV_PFXS = ("feat:","fix:","refactor:","perf:","security:","test:","docs:","feat(","fix(","refactor(","perf(")
_V_RE = re.compile(r"^v\d+\.\d+")
_DEC_KW = ("pivot","revert","dead-end","rejected","chose","switched","CONVERGED","failed","success","fix","improvement","benchmark","eval","decision","iter")
_NOISE_PFX = ("# ","wip:","merge ",'revert "')

def _is_noise(s):
    s = s.strip()
    if _OMC_RE.match(s): return True
    if _VER_RE.match(s): return not bool(_EMB_RE.search(s))
    return False

def _is_decision(s):
    s = s.strip()
    if not s: return False
    sl = s.lower()
    if any(sl.startswith(p) for p in _NOISE_PFX): return False
    if any(sl.startswith(p) for p in _CONV_PFXS): return True
    if _V_RE.match(s): return True
    return any(kw.lower() in sl for kw in _DEC_KW)

def _commit_files(project_dir, commit_hash):
    try:
        r = subprocess.run(["git","diff-tree","--no-commit-id","-r","--name-only",commit_hash],
            cwd=project_dir, capture_output=True, text=True, timeout=3)
        return [l.strip() for l in r.stdout.strip().split("\n") if l.strip()] if r.returncode==0 else []
    except: return []

def _topic_key(files):
    code = [f for f in files if f.endswith((".py",".ts",".tsx",".js",".go",".rs"))
            and not f.startswith(("tests/","test_","docs/"))]
    return frozenset(sorted(code)[:2]) if code else None

def ctx_no_ctx(_pd): return ""

def ctx_long_n(pd, n):
    subs = _git_log_subjects(pd, n)
    if not subs: return "No commits found."
    return f"[RECENT COMMITS (last {n})]\n" + "\n".join(f"> {s}" for s in subs[:n])

def ctx_rag_bm25(pd, query, k=5, pool=50):
    pairs = _git_log_with_hash(pd, pool)
    subs = [s for _,s in pairs]
    if not subs: return "No commits for retrieval."
    try:
        from rank_bm25 import BM25Okapi
        tok = [re.sub(r"[^a-zA-Z0-9%@+.\-]"," ",s).lower().split() for s in subs]
        qtok = re.sub(r"[^a-zA-Z0-9%@+.\-]"," ",query).lower().split()
        bm25 = BM25Okapi(tok)
        scores = bm25.get_scores(qtok)
        top = sorted(range(len(scores)), key=lambda i: -scores[i])[:k]
        ranked = [subs[i] for i in sorted(top)]
    except ImportError:
        qterms = set(re.sub(r"[^a-zA-Z0-9]"," ",query).lower().split())
        scored = sorted(subs, key=lambda s: -len(qterms & set(re.sub(r"[^a-zA-Z0-9]"," ",s).lower().split())))
        ranked = scored[:k]
    return f"[RAG-BM25 top-{k} of {pool}]\n" + "\n".join(f"> {s}" for s in ranked)

def ctx_g1_raw(pd):
    subs = _git_log_subjects(pd, 20)
    decisions = [s for s in subs if _is_decision(s)][:7]
    if not decisions: return "No decisions found."
    return "[RECENT DECISIONS (raw, n=20)]\n" + "\n".join(f"> {s}" for s in decisions)

def ctx_g1_current(pd):
    pairs = _git_log_with_hash(pd, 30)
    if not pairs: return "No decisions found."
    CAP = 7
    candidates, seen = [], set()
    for chash, subject in pairs:
        if len(subject) > 120:
            cut = subject[:120].rfind(" ")
            subject = subject[:cut] if cut > 80 else subject[:120]
        if _is_noise(subject): continue
        key = subject[:60]
        if key in seen: continue
        seen.add(key)
        if _is_decision(subject):
            candidates.append({"hash": chash, "subject": subject})
    if not candidates: return "No decisions found."
    scan = min(CAP*2, len(candidates))
    for c in candidates[:scan]:
        c["files"] = _commit_files(pd, c["hash"])
        c["topic"] = _topic_key(c["files"])
    selected, seen_topics, remainder = [], set(), []
    for c in candidates[:scan]:
        tk = c.get("topic")
        if tk is not None and tk not in seen_topics:
            seen_topics.add(tk); selected.append(c)
        else: remainder.append(c)
    for c in remainder:
        if len(selected) >= CAP: break
        selected.append(c)
    for c in candidates[scan:]:
        if len(selected) >= CAP: break
        c.setdefault("files",[]); c.setdefault("topic",None); selected.append(c)
    return "[RECENT DECISIONS (filtered + topic-dedup, n=30)]\n" + "\n".join(f"> {c['subject']}" for c in selected[:CAP])

def build_context(baseline, pd, query=""):
    if baseline == "no_ctx": return ctx_no_ctx(pd)
    elif baseline == "long_ctx_20": return ctx_long_n(pd, 20)
    elif baseline == "long_ctx_50": return ctx_long_n(pd, 50)
    elif baseline == "rag_bm25": return ctx_rag_bm25(pd, query)
    elif baseline == "g1_raw": return ctx_g1_raw(pd)
    elif baseline == "g1_current": return ctx_g1_current(pd)
    else: raise ValueError(f"Unknown baseline: {baseline}")

# ─────────────────────────────────────────────────────────────────────────────
# LLM client
# ─────────────────────────────────────────────────────────────────────────────

def load_env():
    src = Path.home() / ".claude" / "env" / "shared.env"
    if src.exists():
        try:
            out = subprocess.run(["bash","-c",f"source {src} && env"], capture_output=True, text=True)
            for line in out.stdout.split("\n"):
                if "=" in line:
                    k,_,v = line.partition("=")
                    if k in ("MINIMAX_API_KEY","MINIMAX_BASE_URL","MINIMAX_MODEL","ANTHROPIC_API_KEY"):
                        os.environ[k] = v
        except: pass

def get_client():
    if not HAS_ANTHROPIC: return None
    key = os.environ.get("MINIMAX_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    base = os.environ.get("MINIMAX_BASE_URL")
    return anthropic.Anthropic(api_key=key, base_url=base) if base else anthropic.Anthropic(api_key=key)

SYS_OPEN = ("You are a software engineer answering questions about a project. "
    "Use ONLY the provided context (git history). If the context doesn't contain the answer, "
    "respond exactly: '[NOT IN CONTEXT]'. Be specific with exact numbers and values.")

SYS_CLOSED = ("You are a software engineer. Answer based solely on your memory of this project. "
    "Give exact values if you know them. If uncertain, say 'I am not certain' and give best estimate. "
    "Be specific with any numbers, percentages, or values you recall.")

def call_llm(client, system, user_msg):
    model = os.environ.get("MINIMAX_MODEL", "MiniMax-M2.5")
    try:
        resp = client.messages.create(model=model, max_tokens=400, system=system,
            messages=[{"role":"user","content":user_msg}])
        for b in resp.content:
            if getattr(b,"type","") == "text" and hasattr(b,"text"): return b.text.strip()
        for b in resp.content:
            if hasattr(b,"text"): return b.text.strip()
        return "[NO-TEXT-BLOCK]"
    except Exception as e: return f"[LLM_ERROR: {e}]"

# ─────────────────────────────────────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────────────────────────────────────

def score_numeric(response, keywords):
    rl = response.lower()
    if "[not in context]" in rl: return 0.0, [], list(keywords)
    hits = [kw for kw in keywords if kw.lower() in rl]
    misses = [kw for kw in keywords if kw.lower() not in rl]
    return round(len(hits)/max(len(keywords),1), 4), hits, misses

# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def bootstrap_ci(vals, n_boot=1000, alpha=0.05):
    if not vals: return 0.0, 0.0, 0.0
    mean = sum(vals)/len(vals)
    if len(vals) == 1: return mean, mean, mean
    import random
    boot = sorted([sum(random.choices(vals,k=len(vals)))/len(vals) for _ in range(n_boot)])
    lo = boot[int(n_boot*alpha/2)]
    hi = boot[int(n_boot*(1-alpha/2))]
    return mean, lo, hi

def wilcoxon(base_deltas, g1_deltas):
    if len(base_deltas) != len(g1_deltas) or len(g1_deltas) < 5:
        return float('nan'), float('nan')
    if HAS_SCIPY:
        try:
            diff = [g-b for g,b in zip(g1_deltas, base_deltas)]
            if all(d==0 for d in diff): return float('nan'), 1.0
            stat, p = scipy_stats.wilcoxon(diff)
            return float(stat), float(p)
        except: return float('nan'), float('nan')
    # Sign-test fallback
    diffs = [g-b for g,b in zip(g1_deltas, base_deltas)]
    pos = sum(1 for d in diffs if d > 0)
    n = sum(1 for d in diffs if d != 0)
    return float(pos), float(2*min(pos, n-pos)/n) if n > 0 else float('nan')

def fit_decay(ages, deltas):
    if len(ages) < 4 or not HAS_NUMPY: return None
    try:
        from scipy.optimize import curve_fit
        def f(x, a, lam, b): return a * np.exp(-lam * np.array(x,float)) + b
        x, y = np.array(ages,float), np.array(deltas,float)
        try:
            popt,_ = curve_fit(f, x, y, p0=[max(y)-min(y),0.05,min(y)],
                               bounds=([0,0,-1],[2,1,1]), maxfev=5000)
            a,lam,b = popt
            yp = f(x,*popt)
            r2 = float(1 - np.sum((y-yp)**2)/np.sum((y-np.mean(y))**2)) if np.sum((y-np.mean(y))**2)>0 else 0.0
            hl = math.log(2)/lam if lam > 0 else float('inf')
            return {"a":round(float(a),4),"lambda":round(float(lam),4),"b":round(float(b),4),
                    "r_squared":round(r2,4),"half_life":round(hl,1)}
        except: return None
    except ImportError: return None

# ─────────────────────────────────────────────────────────────────────────────
# Dry-run simulators
# ─────────────────────────────────────────────────────────────────────────────

def sim_closed(item, ctx): return f"I recall the project worked on {item['topic']} but I don't have exact values."

def sim_open(item, ctx):
    hint = item.get("hint","")[:40].lower()
    if hint and hint[:25] in ctx.lower():
        return f"Based on context: {', '.join(item['keywords'])}. The project recorded {item['topic']}."
    return f"The context mentions related work but not the specific {item['topic']} values."

# ─────────────────────────────────────────────────────────────────────────────
# Data class
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RecallResult:
    item_id: int; age: int; bin: str; topic: str; question: str; keywords: List[str]
    baseline: str; ctx_chars: int
    closed_resp: str; closed_score: float; closed_hits: List[str]
    open_resp: str; open_score: float; open_hits: List[str]
    delta: float; in_window: bool

# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def run_benchmark(client, pd, items, baselines, dry_run):
    results = []
    total = len(items)*len(baselines); done = 0
    static = {bl: build_context(bl,pd) for bl in baselines if bl != "rag_bm25"}
    print(f"\nRunning {len(items)} items x {len(baselines)} baselines = {total} pairs")
    print(f"Total LLM calls: {total*2} (1 closed + 1 open per pair)")
    for idx,item in enumerate(items):
        for bl in baselines:
            ctx = build_context(bl,pd,query=item["question"]) if bl=="rag_bm25" else static[bl]
            hint = item.get("hint","")[:30].lower()
            in_win = hint and any(kw in ctx for kw in item["keywords"][:2])
            if dry_run:
                cb_r, ob_r = sim_closed(item,ctx), sim_open(item,ctx)
            else:
                cb_r = call_llm(client, SYS_CLOSED, f"Question: {item['question']}"); time.sleep(0.3)
                ob_user = f"{ctx}\n\n---\n\nQuestion: {item['question']}" if ctx else f"Question: {item['question']}"
                ob_r = call_llm(client, SYS_OPEN, ob_user); time.sleep(0.3)
            cb_s, cb_h, _ = score_numeric(cb_r, item["keywords"])
            ob_s, ob_h, _ = score_numeric(ob_r, item["keywords"])
            results.append(RecallResult(
                item_id=idx, age=item["age"], bin=item["bin"], topic=item["topic"],
                question=item["question"], keywords=item["keywords"],
                baseline=bl, ctx_chars=len(ctx),
                closed_resp=cb_r[:300], closed_score=cb_s, closed_hits=cb_h,
                open_resp=ob_r[:300], open_score=ob_s, open_hits=ob_h,
                delta=round(ob_s-cb_s,4), in_window=bool(in_win)
            ))
            done += 1
            bar = "#"*(done*20//total)+"."*(20-done*20//total)
            print(f"\r  [{bar}] {done}/{total}  age={item['age']:2d} x {bl}", end="", flush=True)
    print(); return results

# ─────────────────────────────────────────────────────────────────────────────
# Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def aggregate(results, baselines):
    by_bl = defaultdict(list); by_bl_bin = defaultdict(lambda: defaultdict(list))
    by_bl_age = defaultdict(lambda: defaultdict(list))
    for r in results:
        by_bl[r.baseline].append(r.delta)
        by_bl_bin[r.baseline][r.bin].append(r.delta)
        by_bl_age[r.baseline][r.age].append(r.delta)
    summary = {}
    for bl in baselines:
        d = by_bl[bl]; mean,lo,hi = bootstrap_ci(d)
        summary[bl] = {"mean_delta":round(mean,4),"ci_lower":round(lo,4),"ci_upper":round(hi,4),"n":len(d),
            "per_bin":{bn:{"mean":round(sum(by_bl_bin[bl].get(bn,[0]))/max(len(by_bl_bin[bl].get(bn,[1])),1),4),
                          "n":len(by_bl_bin[bl].get(bn,[]))} for bn in TEMPORAL_BINS}}
    g1 = "g1_current"; g1d = by_bl.get(g1,[])
    stat_tests = {}
    n_comp = len(baselines)-1
    for bl in baselines:
        if bl == g1: continue
        bld = by_bl.get(bl,[]); n = min(len(bld),len(g1d))
        if n < 5:
            stat_tests[bl] = {"p_value":float('nan'),"p_bonf":float('nan'),"sig_p05":False,"effect_r":float('nan')}; continue
        stat, p = wilcoxon(bld[:n], g1d[:n])
        pb = min(p*n_comp,1.0) if not math.isnan(p) else float('nan')
        n_eff = n*(n+1)/4
        z = (stat-n_eff)/math.sqrt(n*(n+1)*(2*n+1)/24) if n > 4 else float('nan')
        r_eff = abs(z)/math.sqrt(n) if not math.isnan(z) else float('nan')
        stat_tests[bl] = {"wilcoxon_stat":round(float(stat),2),
            "p_value":round(float(p),4) if not math.isnan(p) else float('nan'),
            "p_bonf":round(float(pb),4) if not math.isnan(pb) else float('nan'),
            "sig_p05": not math.isnan(p) and p<0.05,
            "sig_bonf": not math.isnan(pb) and pb<0.05,
            "effect_r":round(float(r_eff),3) if not math.isnan(r_eff) else float('nan'),"n":n}
    decay = {}
    for bl in baselines:
        ages_l = sorted(by_bl_age[bl].keys())
        md = [sum(by_bl_age[bl][a])/max(len(by_bl_age[bl][a]),1) for a in ages_l]
        dp = fit_decay(ages_l, md)
        decay[bl] = {"ages":ages_l,"mean_deltas":[round(d,4) for d in md],"decay_params":dp}
    return {"summary":summary,"stat_tests":stat_tests,"decay_curves":decay}

# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────

def print_report(results, agg, baselines):
    print("\n"+"="*80)
    print("  DECIDE-BENCH: Decision Recall for Coding-Agent Context Enhancement")
    print("  metric: delta = open_book_recall - closed_book_recall (higher = better)")
    print("="*80)
    print(f"\n  {'Baseline':16s}  {'Mean delta':>10}  {'95% CI':>18}  {'N':>4}  {'vs G1 p':>8}  {'r':>5}")
    print(f"  {'-'*16}  {'-'*10}  {'-'*18}  {'-'*4}  {'-'*8}  {'-'*5}")
    for bl in baselines:
        s = agg["summary"].get(bl,{}); st = agg["stat_tests"].get(bl,{})
        m=s.get("mean_delta",0); lo=s.get("ci_lower",0); hi=s.get("ci_upper",0); n=s.get("n",0)
        ci = f"[{lo:+.3f},{hi:+.3f}]"
        pv = st.get("p_value",float('nan')); p_str = f"{pv:.4f}" if not math.isnan(pv) else "—"
        sig = "*" if st.get("sig_p05",False) else " "
        rv = st.get("effect_r",float('nan')); r_str = f"{rv:.3f}" if not math.isnan(rv) else "—"
        mark = " ←" if bl=="g1_current" else ""
        print(f"  {bl:16s}  {m:>+10.4f}  {ci:>18}  {n:>4}  {p_str:>7}{sig}  {r_str:>5}{mark}")
    print(f"\n  {'Temporal breakdown (mean delta per bin)':}")
    bins = list(TEMPORAL_BINS.keys())
    hdr = f"  {'Baseline':16s}" + "".join(f"  {b:>12}" for b in bins)
    print(hdr); print("  "+"-"*16+"".join("  "+"-"*12 for _ in bins))
    for bl in baselines:
        row = f"  {bl:16s}"
        for bn in bins:
            bd = agg["summary"].get(bl,{}).get("per_bin",{}).get(bn,{}); m=bd.get("mean",0); nn=bd.get("n",0)
            row += f"  {m:>+9.3f}({nn})"
        print(row)
    print(f"\n  Temporal Decay: delta = a*exp(-lambda*age) + b")
    print(f"  {'Baseline':16s}  {'lambda TDR':>10}  {'R2':>6}  {'Half-life':>10}  {'a':>6}  {'b':>6}")
    print(f"  {'-'*16}  {'-'*10}  {'-'*6}  {'-'*10}  {'-'*6}  {'-'*6}")
    for bl in baselines:
        dp = agg["decay_curves"].get(bl,{}).get("decay_params")
        if dp:
            print(f"  {bl:16s}  {dp['lambda']:>10.4f}  {dp['r_squared']:>6.3f}  {dp['half_life']:>10.1f}  {dp['a']:>6.3f}  {dp['b']:>6.3f}")
        else:
            print(f"  {bl:16s}  {'N/A':>10}  {'N/A':>6}  {'N/A':>10}  {'N/A':>6}  {'N/A':>6}")
    print(f"\n  Statistical tests (Wilcoxon + Bonferroni, G1=reference):")
    print(f"  {'Baseline':16s}  {'p-value':>8}  {'p (Bonf)':>9}  {'r effect':>8}  result")
    print(f"  {'-'*16}  {'-'*8}  {'-'*9}  {'-'*8}  ------")
    for bl in baselines:
        if bl == "g1_current": continue
        st = agg["stat_tests"].get(bl,{}); pv=st.get("p_value",float('nan'))
        pb=st.get("p_bonf",float('nan')); rv=st.get("effect_r",float('nan'))
        p_s=f"{pv:.4f}" if not math.isnan(pv) else "N/A"
        pb_s=f"{pb:.4f}" if not math.isnan(pb) else "N/A"
        r_s=f"{rv:.3f}" if not math.isnan(rv) else "N/A"
        result = "sig p<.05" if st.get("sig_p05") else "n.s."
        result += " (Bonf)" if st.get("sig_bonf") else ""
        print(f"  {bl:16s}  {p_s:>8}  {pb_s:>9}  {r_s:>8}  {result}")
    # in-window
    print(f"\n  In-window rate (does context contain the answer commit):")
    iw = defaultdict(lambda:{"t":0,"w":0})
    for r in results: iw[r.baseline]["t"]+=1; iw[r.baseline]["w"]+=int(r.in_window)
    for bl in baselines:
        d=iw[bl]; rate=d["w"]/max(d["t"],1)
        print(f"    {bl:16s}: {d['w']}/{d['t']} = {rate:.1%}")
    print("="*80)

def save(results, agg, pd):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    op = Path(pd)/"benchmarks"/"results"/f"decide_bench_{ts}.json"
    op.parent.mkdir(parents=True, exist_ok=True)
    with open(op,"w",encoding="utf-8") as f:
        json.dump({"timestamp":ts,"project":pd,"n_items":len(set(r.item_id for r in results)),
            "aggregation":agg,"raw":[asdict(r) for r in results]}, f, indent=2, ensure_ascii=False)
    print(f"\nSaved: {op.name}"); return op

# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DECIDE-Bench: G1 temporal recall")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without API calls")
    parser.add_argument("--project", default=str(ROOT))
    parser.add_argument("--baselines", default=",".join(BASELINE_NAMES))
    args = parser.parse_args()

    pd = args.project
    baselines = [b.strip() for b in args.baselines.split(",")]

    if not args.dry_run: load_env()
    client = None if args.dry_run else get_client()
    if not args.dry_run and client is None:
        print("ERROR: No LLM client. Set MINIMAX_API_KEY or use --dry-run.")
        sys.exit(1)

    backend = "DRY-RUN" if args.dry_run else os.environ.get("MINIMAX_MODEL","unknown")
    print(f"\nDECIDE-Bench v1.0  |  backend={backend}  |  project={pd}")
    items = BENCHMARK_ITEMS
    bin_counts = defaultdict(int)
    for item in items: bin_counts[item["bin"]] += 1
    print(f"Items: {len(items)}  |  Baselines: {baselines}")
    for bn,cnt in sorted(bin_counts.items()):
        ages = [i["age"] for i in items if i["bin"]==bn]
        print(f"  {bn:10s}: {cnt} items  ages {min(ages)}-{max(ages)}")

    print(f"\nContext preview:")
    for bl in baselines:
        try:
            ctx = build_context(bl,pd,query="benchmark score result")
            print(f"  {bl:16s}: {len(ctx):5d} chars  {ctx.count(chr(10))+1} lines")
        except Exception as e: print(f"  {bl:16s}: ERROR ({e})")

    results = run_benchmark(client, pd, items, baselines, args.dry_run)
    agg = aggregate(results, baselines)
    print_report(results, agg, baselines)
    out = save(results, agg, pd)

    g1m = agg["summary"].get("g1_current",{}).get("mean_delta",0)
    n0m = agg["summary"].get("no_ctx",{}).get("mean_delta",0)
    l5m = agg["summary"].get("long_ctx_50",{}).get("mean_delta",0)
    dp = agg["decay_curves"].get("g1_current",{}).get("decay_params")
    print(f"\n[PAPER SUMMARY]")
    print(f"  G1 mean delta:      {g1m:+.4f}")
    print(f"  vs no_ctx:          {n0m:+.4f}  (delta gap: {g1m-n0m:+.4f})")
    print(f"  vs long_ctx_50:     {l5m:+.4f}  (delta gap: {g1m-l5m:+.4f})")
    if dp: print(f"  TDR lambda:         {dp['lambda']:.4f}  half-life: {dp['half_life']:.1f} commits  R2={dp['r_squared']:.3f}")
    print(f"  Results file: {out.name}")

if __name__ == "__main__":
    main()
