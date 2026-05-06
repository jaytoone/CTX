"""
CTX: Cross-Session Memory for Claude Code
HuggingFace Space — Interactive Demo (v1.0)

Shows G1 (decision recall) and G2 (file retrieval) before/after comparison.
Fully self-contained — no backend, no vault.db, no vec-daemon required.
"""

import gradio as gr

# ── G1 scenarios: simulated before/after decision recall ──────────────────────

G1_SCENARIOS = {
    "Why did we switch from TF-IDF to BM25?": {
        "without": (
            "I don't have context about previous decisions in this project. "
            "Could you tell me more about the retrieval system you're working on?"
        ),
        "injected": [
            {
                "date": "2026-03-27",
                "decision": "Switched retrieval scorer from TF-IDF to BM25",
                "reason": "keyword R@3 improved 0.379 → 0.655 (+27.3pp). "
                          "TF-IDF penalized domain terms via low IDF on small corpora.",
            },
            {
                "date": "2026-03-27",
                "decision": "BM25Okapi (IDF-weighted) also underperformed — routed keyword queries to TF-only BM25",
                "reason": "Domain terms ('retrieval', 'ctx') appear in many docs → IDF ≈ 0. "
                          "TF-only variant brought keyword R@3 to 0.724.",
            },
            {
                "date": "2026-04-03",
                "decision": "External codebase R@5 gap (0.152) identified as next priority",
                "reason": "Heuristic over-fitting to internal 29-doc corpus. AST parser upgrade queued.",
            },
        ],
        "with": (
            "We switched from TF-IDF to BM25 on 2026-03-27 because keyword R@3 improved from "
            "0.379 → 0.655 (+27.3pp). The root cause: TF-IDF assigned near-zero IDF to domain "
            "terms like 'retrieval' and 'ctx' that appear across many documents in the small "
            "29-doc corpus, effectively ignoring the most relevant terms.\n\n"
            "We later discovered BM25Okapi (IDF-weighted) had the same problem, so keyword queries "
            "were re-routed to a TF-only BM25 variant — bringing keyword R@3 to 0.724."
        ),
    },
    "What were the 3 telemetry schema bugs?": {
        "without": (
            "I'm not aware of any telemetry schema fixes in my current context. "
            "Could you describe the issue?"
        ),
        "injected": [
            {
                "date": "2026-04-29",
                "decision": "Fixed G1 block key mismatch: 'g1' → 'g1_decisions' in bm25-memory.py",
                "reason": "by_block key 'g1' never matched meta dict key 'g1_decisions' "
                          "→ all G1 records logged UNKNOWN for query_type, retrieval_method, top_score.",
            },
            {
                "date": "2026-04-29",
                "decision": "Fixed UNKNOWN string truthy bug in utility-rate.py",
                "reason": "'UNKNOWN' is truthy → or-chain skipped fallback classifier. "
                          "Replaced with explicit != 'UNKNOWN' guard.",
            },
            {
                "date": "2026-04-29",
                "decision": "G2-DOCS candidates_returned was hardcoded None",
                "reason": "Now calls build_docs_bm25() to get actual corpus size — "
                          "consistent with G1 which uses len(corpus).",
            },
        ],
        "with": (
            "Three telemetry schema bugs were fixed on 2026-04-29:\n\n"
            "1. **Block key mismatch** — bm25-memory.py keyed the G1 injection block as 'g1' "
            "but utility-rate.py looked for 'g1_decisions'. Every G1 record logged UNKNOWN "
            "for all metadata fields.\n\n"
            "2. **UNKNOWN truthy bug** — the string 'UNKNOWN' is truthy in Python, so "
            "`block_meta.get('query_type') or _classify_query()` never called the fallback "
            "classifier. Fixed with an explicit `!= 'UNKNOWN'` guard.\n\n"
            "3. **candidates_returned hardcoded None** — G2-DOCS was always logging None "
            "instead of calling build_docs_bm25() for the actual corpus size."
        ),
    },
    "Why does chat-memory need vec-daemon?": {
        "without": (
            "I don't have details about chat-memory's architecture in my current context."
        ),
        "injected": [
            {
                "date": "2026-04-17",
                "decision": "chat-memory.py uses hybrid BM25 + vec0 (multilingual-e5-small, 384-dim)",
                "reason": "Semantic rescue: dense recovers paraphrase queries BM25 misses. "
                          "G1 hybrid Recall@7 = 0.983 vs BM25 0.967.",
            },
            {
                "date": "2026-04-17",
                "decision": "vec-daemon communicates via Unix socket at ~/.local/share/claude-vault/",
                "reason": "< 1ms IPC round-trip. Windows-native has no Unix socket — P0 distribution blocker.",
            },
            {
                "date": "2026-04-17",
                "decision": "bm25-memory.py has zero vec-daemon dependency by design",
                "reason": "BM25 path must work standalone. chat-memory falls back to BM25-only "
                          "with ⚠ warning when daemon is down.",
            },
        ],
        "with": (
            "chat-memory.py uses vec-daemon for hybrid BM25 + semantic search. vec-daemon runs "
            "multilingual-e5-small (384-dim) and communicates via a Unix domain socket at "
            "~/.local/share/claude-vault/, giving <1ms round-trip latency.\n\n"
            "The semantic layer rescues paraphrase queries that BM25 misses — G1 hybrid "
            "Recall@7 is 0.983 vs 0.967 BM25-only.\n\n"
            "Unix sockets don't exist on Windows-native, making this a P0 distribution "
            "blocker for v1.0. bm25-memory.py was deliberately designed with zero vec-daemon "
            "dependency so the BM25-only path always works as a fallback."
        ),
    },
}

# ── G2 scenarios: simulated file retrieval ────────────────────────────────────

G2_SCENARIOS = {
    "Update the BM25 scoring weights in the retrieval scorer": {
        "files": [
            {
                "path": "src/retrieval/adaptive_trigger.py",
                "line": 214,
                "score": 0.91,
                "reason": "BM25 weight parameters — _bm25_retrieve(), _concept_retrieve() scoring",
            },
            {
                "path": "benchmarks/eval/doc_retrieval_eval_v2.py",
                "line": 89,
                "score": 0.74,
                "reason": "BM25-augmented scoring in rank_ctx_doc() — stage 2 weight constants",
            },
            {
                "path": "src/retrieval/full_context.py",
                "line": 12,
                "score": 0.61,
                "reason": "RetrievalResult dataclass — score field definitions",
            },
        ],
        "tool_calls_without": 7,
        "latency_ms": 0.8,
    },
    "Fix the telemetry block key mismatch": {
        "files": [
            {
                "path": "~/.claude/hooks/bm25-memory.py",
                "line": 312,
                "score": 0.94,
                "reason": "G1 injection block keyed 'g1' — must match meta dict key 'g1_decisions'",
            },
            {
                "path": "~/.claude/hooks/utility-rate.py",
                "line": 47,
                "score": 0.88,
                "reason": "block_meta lookup + UNKNOWN fallback guard — cm_block_meta merge logic",
            },
        ],
        "tool_calls_without": 5,
        "latency_ms": 0.6,
    },
    "Add Korean query expansion to G2-DOCS search": {
        "files": [
            {
                "path": "~/.claude/hooks/bm25-memory.py",
                "line": 178,
                "score": 0.96,
                "reason": "_KO_EN_DOCS dict + _expand_ko_en_docs() — Korean→English expansion for docs BM25",
            },
            {
                "path": "docs/research/20260426-g2-docs-korean-crosslingual-fix.md",
                "line": None,
                "score": 0.82,
                "reason": "Korean crosslingual fix design — H@5 0.400→1.000 after expansion",
            },
            {
                "path": "benchmarks/eval/g2_docs_eval.py",
                "line": 203,
                "score": 0.67,
                "reason": "Korean query goldset + eval harness",
            },
        ],
        "tool_calls_without": 9,
        "latency_ms": 0.7,
    },
}

# ── Benchmark data ────────────────────────────────────────────────────────────

BENCHMARKS = [
    ("G1 Decision Recall",   "1.000",  "0.219",  "Recall@7",        "MiniMax M2.5 downstream eval"),
    ("G2 Docs Retrieval",    "1.000",  "0.800",  "H@5 (Hybrid)",    "20-query goldset, 87 docs"),
    ("G2 Code Retrieval",    "0.958",  "0.946",  "R@5",             "vs Nemotron-Cascade-2"),
    ("Hallucination Rate",   "0.000",  "0.170",  "rate ↓",          "0% with CTX vs 17% without"),
    ("Hook Latency",         "< 1 ms", "—",      "per prompt",      "Pure BM25 — no LLM, no embedding"),
    ("Utility Rate",         "50%",    "—",      "tool-use turns",  "Context actually cited by Claude"),
]

# ── Custom CSS ────────────────────────────────────────────────────────────────

CSS = """
.ctx-header { text-align: center; padding: 1.5rem 0 0.5rem; }
.ctx-header h1 { font-size: 2rem; font-weight: 700; margin-bottom: 0.25rem; }
.ctx-header p  { color: #6b7280; font-size: 1rem; margin: 0; }

.panel-without { background: #fff8f8; border: 1px solid #fca5a5; border-radius: 8px; padding: 1rem; }
.panel-inject  { background: #f0fdf4; border: 1px solid #86efac; border-radius: 8px; padding: 1rem; }
.panel-with    { background: #eff6ff; border: 1px solid #93c5fd; border-radius: 8px; padding: 1rem; }

.inject-item { background: #f9fafb; border-left: 3px solid #10b981;
               border-radius: 4px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; font-size: 0.875rem; }
.inject-date { font-weight: 600; color: #059669; }
.inject-decision { font-weight: 500; margin: 0.2rem 0; }
.inject-reason   { color: #6b7280; font-size: 0.8rem; }

.file-item  { background: #f9fafb; border-left: 3px solid #6366f1;
              border-radius: 4px; padding: 0.6rem 0.8rem; margin-bottom: 0.5rem; font-size: 0.875rem; }
.file-path  { font-family: monospace; font-weight: 600; color: #4f46e5; }
.file-score { float: right; background: #e0e7ff; color: #4338ca;
              padding: 0.1rem 0.4rem; border-radius: 4px; font-size: 0.75rem; font-weight: 700; }
.file-reason { color: #6b7280; font-size: 0.8rem; margin-top: 0.25rem; }

.bench-table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
.bench-table th { background: #1e293b; color: white; padding: 0.6rem 0.8rem; text-align: left; }
.bench-table td { padding: 0.55rem 0.8rem; border-bottom: 1px solid #e2e8f0; }
.bench-table tr:hover td { background: #f8fafc; }
.good { color: #059669; font-weight: 700; }
.note-cell { color: #6b7280; font-size: 0.8rem; }

.install-box { background: #0f172a; color: #e2e8f0; border-radius: 8px;
               padding: 1rem 1.25rem; font-family: monospace; font-size: 0.95rem; }
.install-comment { color: #64748b; }
.install-cmd { color: #34d399; }

.stat-box { text-align: center; background: #f8fafc; border: 1px solid #e2e8f0;
            border-radius: 8px; padding: 1rem; }
.stat-num  { font-size: 2rem; font-weight: 700; color: #4f46e5; }
.stat-label { font-size: 0.8rem; color: #6b7280; margin-top: 0.25rem; }
"""

# ── Helper: render G1 injection block as HTML ─────────────────────────────────

def _render_injection(items: list) -> str:
    html = "<div style='font-size:0.8rem;color:#059669;font-weight:600;margin-bottom:0.5rem;'>"
    html += f"📥 CTX G1 — {len(items)} decisions injected</div>"
    for d in items:
        html += (
            f"<div class='inject-item'>"
            f"<span class='inject-date'>{d['date']}</span><br>"
            f"<div class='inject-decision'>→ {d['decision']}</div>"
            f"<div class='inject-reason'>Reason: {d['reason']}</div>"
            f"</div>"
        )
    return html


def _render_files(files: list, latency_ms: float) -> str:
    html = "<div style='font-size:0.8rem;color:#4f46e5;font-weight:600;margin-bottom:0.5rem;'>"
    html += f"📂 CTX G2 — {len(files)} files injected in {latency_ms}ms</div>"
    for f in files:
        line_str = f":L{f['line']}" if f["line"] else ""
        html += (
            f"<div class='file-item'>"
            f"<span class='file-score'>score {f['score']:.2f}</span>"
            f"<span class='file-path'>{f['path']}{line_str}</span><br>"
            f"<div class='file-reason'>→ {f['reason']}</div>"
            f"</div>"
        )
    return html


def _render_bench_table() -> str:
    rows = ""
    for name, with_ctx, without_ctx, unit, note in BENCHMARKS:
        rows += (
            f"<tr>"
            f"<td><strong>{name}</strong></td>"
            f"<td class='good'>{with_ctx}</td>"
            f"<td>{without_ctx}</td>"
            f"<td>{unit}</td>"
            f"<td class='note-cell'>{note}</td>"
            f"</tr>"
        )
    return (
        "<table class='bench-table'>"
        "<thead><tr>"
        "<th>Metric</th><th>With CTX</th><th>Without CTX</th><th>Unit</th><th>Notes</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


# ── Event handlers ────────────────────────────────────────────────────────────

def run_g1(scenario_key: str):
    s = G1_SCENARIOS[scenario_key]
    without_html = (
        "<div class='panel-without'>"
        "<strong style='color:#dc2626'>❌ Without CTX</strong><br><br>"
        f"{s['without']}"
        "</div>"
    )
    inject_html = (
        "<div class='panel-inject'>"
        + _render_injection(s["injected"])
        + "</div>"
    )
    with_html = (
        "<div class='panel-with'>"
        "<strong style='color:#2563eb'>✅ With CTX</strong><br><br>"
        + s["with"].replace("\n\n", "<br><br>").replace("\n", "<br>")
        + "</div>"
    )
    return without_html, inject_html, with_html


def run_g2(task_key: str):
    s = G2_SCENARIOS[task_key]
    without_html = (
        "<div class='panel-without'>"
        "<strong style='color:#dc2626'>❌ Without CTX</strong><br><br>"
        f"Claude runs <strong>{s['tool_calls_without']} Grep/Glob tool calls</strong> "
        "scanning the codebase before locating the relevant file."
        "</div>"
    )
    files_html = (
        "<div class='panel-inject'>"
        + _render_files(s["files"], s["latency_ms"])
        + "</div>"
    )
    with_html = (
        "<div class='panel-with'>"
        "<strong style='color:#2563eb'>✅ With CTX</strong><br><br>"
        f"Claude opens the correct file <strong>on the first tool call</strong>. "
        f"Context injected in <strong>{s['latency_ms']}ms</strong> — "
        "no directory scan, no grep loop."
        "</div>"
    )
    return without_html, files_html, with_html


# ── Build Gradio app ──────────────────────────────────────────────────────────

with gr.Blocks(css=CSS, title="CTX — Cross-Session Memory for Claude Code") as demo:

    gr.HTML(
        "<div class='ctx-header'>"
        "<h1>🧠 CTX</h1>"
        "<p>Cross-session memory for Claude Code — BM25 + hybrid semantic retrieval, "
        "&lt;1ms latency, zero LLM calls.</p>"
        "</div>"
    )

    with gr.Tabs():

        # ── Tab 1: G1 Demo ─────────────────────────────────────────────────────
        with gr.TabItem("G1 — Decision Memory"):
            gr.Markdown(
                "**G1** recalls past engineering decisions from your git history and previous sessions. "
                "Pick a question, click Run — see what Claude says with and without CTX."
            )
            g1_scenario = gr.Dropdown(
                choices=list(G1_SCENARIOS.keys()),
                value=list(G1_SCENARIOS.keys())[0],
                label="Scenario",
                interactive=True,
            )
            g1_btn = gr.Button("▶ Run comparison", variant="primary")

            with gr.Row():
                g1_without = gr.HTML(label="Without CTX")
            with gr.Row():
                g1_inject = gr.HTML(label="CTX injection")
            with gr.Row():
                g1_with = gr.HTML(label="With CTX")

            g1_btn.click(
                fn=run_g1,
                inputs=g1_scenario,
                outputs=[g1_without, g1_inject, g1_with],
            )

        # ── Tab 2: G2 Demo ─────────────────────────────────────────────────────
        with gr.TabItem("G2 — File Retrieval"):
            gr.Markdown(
                "**G2** finds the exact file and line number before Claude's first tool call. "
                "Searches docs, codebase, and hooks simultaneously — in under 1ms."
            )
            g2_task = gr.Dropdown(
                choices=list(G2_SCENARIOS.keys()),
                value=list(G2_SCENARIOS.keys())[0],
                label="Task",
                interactive=True,
            )
            g2_btn = gr.Button("▶ Run comparison", variant="primary")

            with gr.Row():
                g2_without = gr.HTML(label="Without CTX")
            with gr.Row():
                g2_files = gr.HTML(label="CTX injection")
            with gr.Row():
                g2_with = gr.HTML(label="With CTX")

            g2_btn.click(
                fn=run_g2,
                inputs=g2_task,
                outputs=[g2_without, g2_files, g2_with],
            )

        # ── Tab 3: Benchmarks ──────────────────────────────────────────────────
        with gr.TabItem("Benchmarks"):
            gr.Markdown("Results from empirical evaluation across G1 (decision recall) and G2 (retrieval) surfaces.")

            with gr.Row():
                gr.HTML("<div class='stat-box'><div class='stat-num'>1.000</div><div class='stat-label'>G1 Recall@7<br>with CTX</div></div>")
                gr.HTML("<div class='stat-box'><div class='stat-num'>0%</div><div class='stat-label'>Hallucination rate<br>with CTX</div></div>")
                gr.HTML("<div class='stat-box'><div class='stat-num'>&lt;1ms</div><div class='stat-label'>Hook latency<br>per prompt</div></div>")
                gr.HTML("<div class='stat-box'><div class='stat-num'>50%</div><div class='stat-label'>Utility rate<br>(cited turns)</div></div>")

            gr.HTML(_render_bench_table())

            gr.Markdown(
                "_G1 downstream eval: MiniMax M2.5, synthetic 32-query benchmark. "
                "G2 docs: 20-query goldset over 87 docs. "
                "G2 code: COIR RepoBench-style held-out eval._"
            )

        # ── Tab 4: Install ─────────────────────────────────────────────────────
        with gr.TabItem("Install"):
            gr.Markdown("## Linux + WSL2 — one command")
            gr.HTML(
                "<div class='install-box'>"
                "<span class='install-comment'># install + wire hooks into ~/.claude/settings.json</span><br>"
                "<span class='install-cmd'>pip install ctx-retriever &amp;&amp; ctx-install</span><br><br>"
                "<span class='install-comment'># verify</span><br>"
                "<span class='install-cmd'>ctx-install status</span>"
                "</div>"
            )
            gr.Markdown(
                "**What `ctx-install` does**\n"
                "1. Copies 4 hook files to `~/.claude/hooks/`\n"
                "2. Takes a timestamped backup of `~/.claude/settings.json`\n"
                "3. Merges CTX hook registrations — never overwrites your existing hooks\n"
                "4. Atomically writes the new settings.json\n"
                "5. Smoke-tests by firing `bm25-memory.py` once and confirming output\n\n"
                "Restart Claude Code after install. Hooks fire on every prompt automatically.\n\n"
                "> **Platform note**: v1.0 supports **Linux native and WSL2** only. "
                "Windows-native (Git Bash/MSYS2) support is in progress — "
                "blocked on upstream Claude Code issue [#34457](https://github.com/anthropics/claude-code/issues/34457).\n\n"
                "**Links**\n"
                "- [GitHub](https://github.com/jaytoone/CTX)\n"
                "- [CONTRIBUTING.md](https://github.com/jaytoone/CTX/blob/master/CONTRIBUTING.md)\n"
                "- [MIT License](https://github.com/jaytoone/CTX/blob/master/LICENSE)"
            )

    gr.HTML(
        "<div style='text-align:center;padding:1rem 0;color:#9ca3af;font-size:0.8rem;'>"
        "CTX v1.0 · MIT License · "
        "<a href='https://github.com/jaytoone/CTX' style='color:#6366f1;'>github.com/jaytoone/CTX</a>"
        "</div>"
    )

if __name__ == "__main__":
    demo.launch()
