"""
expand_mab_templates.py — Expand 10 base reversal templates to 50 by varying
distractor content + reversal phrasing. Maintains same ground-truth structure.
"""
import json, random, sys
sys.path.insert(0, "/home/jayone/Project/CTX/benchmarks/eval")
import tier1_memoryagentbench as t

# For each base template, generate 5 variants by shuffling distractor pool + rephrasing slightly
DISTRACTOR_POOLS = [
    ["discussing Q3 planning", "reviewing design mockups", "ordering pizza for the team",
     "noting a customer escalation", "scheduling a 1:1 with PM"],
    ["reading the Rust newsletter", "fixing a typo in the README", "debugging a flaky test",
     "planning a retro", "drafting a blog post"],
    ["exploring alternatives briefly", "checking out a competitor demo", "noting an open issue",
     "mentioning a library upgrade", "discussing office logistics"],
    ["reviewing benchmark numbers", "chatting about conferences", "ordering lunch",
     "considering contractor hires", "discussing cloud costs"],
    ["noting a bug report", "planning the next sprint", "checking linting rules",
     "discussing UX feedback", "reviewing metrics dashboards"],
]

# Alternative phrasings for each reversal (same semantic meaning)
REVERSAL_VARIANTS = {
    "retrieval backend":   [
        "We replaced TF-IDF with BM25 after benchmarking.",
        "Switched from TF-IDF to BM25 to improve Recall@3.",
        "After the benchmark, we migrated TF-IDF -> BM25.",
        "TF-IDF retired; BM25 is now the production retrieval engine.",
        "Replacing TF-IDF with BM25 delivered a 72% Recall@3 lift.",
    ],
    "database":   [
        "Migrated from PostgreSQL to SQLite for deployment simplicity.",
        "Switched session storage PostgreSQL -> SQLite last week.",
        "PostgreSQL retired; SQLite now backs session storage.",
        "Replaced PostgreSQL with SQLite (simpler deployment).",
        "Dropped PostgreSQL in favor of SQLite for this project.",
    ],
    "frontend framework":   [
        "Rewrote the dashboard in vanilla JS to remove the React dep.",
        "Dashboard migrated React -> vanilla JS after the dep audit.",
        "React retired; dashboard is now pure vanilla JS.",
        "Rewrote the entire dashboard in vanilla JavaScript.",
        "Dashboard React dependency removed; now using plain JS only.",
    ],
    "embedding model":   [
        "Switched to multilingual-e5-small for Korean support.",
        "Replaced all-MiniLM-L6-v2 with multilingual-e5-small.",
        "Upgraded embedding model to multilingual-e5-small.",
        "multilingual-e5-small is now the production embedding model.",
        "Migration complete: all-MiniLM -> multilingual-e5-small.",
    ],
    "concurrency model":   [
        "Rewrote the loop to use threading after asyncio race bugs.",
        "Dropped asyncio in favor of threading.",
        "Main loop migrated asyncio -> threading.",
        "Threading replaced asyncio after race conditions were found.",
        "Switched concurrency model from asyncio to threading.",
    ],
    "package manager":   [
        "Moved from pip to uv for lockfile determinism.",
        "Replaced pip with uv; lockfile now deterministic.",
        "Package management switched pip -> uv.",
        "uv is the new package manager (replaces pip).",
        "Migrated to uv from pip for reliability.",
    ],
    "CI provider":   [
        "Migrated CI from CircleCI to GitHub Actions after quota issues.",
        "Switched CI provider CircleCI -> GitHub Actions.",
        "CircleCI retired; CI now runs on GitHub Actions.",
        "Moved CI to GitHub Actions (dropping CircleCI).",
        "GitHub Actions replaced CircleCI for CI.",
    ],
    "rerank layer":   [
        "Replaced cosine with BGE cross-encoder for stronger semantic signal.",
        "Switched reranker: cosine similarity -> BGE cross-encoder.",
        "BGE cross-encoder now handles reranking (cosine retired).",
        "Upgraded rerank: cosine -> BGE cross-encoder.",
        "BGE cross-encoder is the new reranker.",
    ],
    "log sink":   [
        "Added structured JSONL logging to .omc/live-progress.log alongside stdout.",
        "Logs now split between stdout AND .omc/live-progress.log JSONL.",
        "JSONL log sink added at .omc/live-progress.log (stdout preserved).",
        "Logging upgraded: now writes to both stdout AND structured JSONL file.",
        "Structured logs go to .omc/live-progress.log; stdout continues.",
    ],
    "monitoring stack":   [
        "Dropped Grafana/Prometheus in favor of a minimal FastAPI /api/health endpoint.",
        "Monitoring simplified: Grafana/Prometheus retired, /api/health now canonical.",
        "Replaced Grafana+Prometheus with FastAPI /api/health.",
        "/api/health is the new monitoring endpoint (Grafana/Prometheus dropped).",
        "Monitoring downgraded to FastAPI /api/health endpoint.",
    ],
}


def expand(seed=42, n_per_template=5):
    rng = random.Random(seed)
    cases = []
    for tpl in t.REVERSAL_TEMPLATES:
        subj = tpl["subject"]
        variants = REVERSAL_VARIANTS.get(subj, [tpl["reversed"]])
        for i in range(n_per_template):
            v_rev = variants[i % len(variants)]
            new_tpl = {**tpl, "reversed": v_rev}
            c = t.generate_synthetic_case(new_tpl, seed=seed + hash(subj + v_rev) % 10000)
            c["question_id"] = f"synth-{subj.replace(' ','-')}-v{i}"
            cases.append(c)
    return cases


if __name__ == "__main__":
    cases = expand(n_per_template=5)
    print(f"Generated {len(cases)} cases (10 subjects × 5 variants)")
    import json
    out = "/home/jayone/Project/CTX/benchmarks/datasets/mab_n50.json"
    with open(out, "w") as f:
        json.dump(cases, f, indent=2)
    print(f"wrote {out}")
    # Sample verification
    for c in cases[:3]:
        rev_content = c["haystack_sessions"][-1]["turns"][0]["content"]
        print(f"  {c['question_id']:<45}  reversal: {rev_content[:60]}")
