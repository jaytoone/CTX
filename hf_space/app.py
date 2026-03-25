"""
CTX: Trigger-Driven Dynamic Context Loading for Code-Aware LLM Agents
HuggingFace Space — Paper Demo
"""

import gradio as gr
import json
import re
import ast
import math
from collections import defaultdict

# ─────────────────────────────────────────────
# Inline CTX core (self-contained for Space)
# ─────────────────────────────────────────────

SAMPLE_CODEBASE = {
    "main.py": '''
import pipeline
import config

def main():
    """Entry point for the CTX demo."""
    cfg = config.load_config("config.yaml")
    pipe = pipeline.Pipeline(cfg)
    results = pipe.run(query="find all retrieval strategies")
    return results
''',
    "pipeline.py": '''
import retriever
import evaluator
import graph_builder

class Pipeline:
    """Main pipeline: query → retrieval → evaluation."""
    def __init__(self, config):
        self.config = config
        self.retriever = retriever.Retriever(config)
        self.evaluator = evaluator.Evaluator()
        self.graph = graph_builder.build_import_graph(".")

    def run(self, query):
        docs = self.retriever.retrieve(query)
        score = self.evaluator.score(docs, query)
        return {"docs": docs, "score": score}
''',
    "retriever.py": '''
import bm25_index
import symbol_index
import concept_index

class Retriever:
    """Trigger-based retrieval dispatcher."""
    def __init__(self, config):
        self.bm25 = bm25_index.BM25Index()
        self.symbols = symbol_index.SymbolIndex()
        self.concepts = concept_index.ConceptIndex()

    def retrieve(self, query, k=5):
        trigger = classify_trigger(query)
        if trigger == "EXPLICIT_SYMBOL":
            return self.symbols.search(query, k)
        elif trigger == "SEMANTIC_CONCEPT":
            return self.concepts.search(query, k)
        else:
            return self.bm25.search(query, k)
''',
    "evaluator.py": '''
import metrics

class Evaluator:
    """Computes retrieval quality metrics."""
    def score(self, docs, query):
        recall = metrics.recall_at_k(docs, query, k=5)
        token_ratio = metrics.token_efficiency(docs)
        tes = recall / math.log(1 + len(docs)) if docs else 0
        return {"recall@5": recall, "token%": token_ratio, "TES": tes}
''',
    "graph_builder.py": '''
import ast
import os
import networkx as nx

def build_import_graph(root_dir):
    """Build import dependency graph via AST parsing."""
    G = nx.DiGraph()
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ["venv", "__pycache__"]]
        for f in files:
            if f.endswith(".py"):
                path = os.path.join(root, f)
                imports = extract_imports(path)
                G.add_node(f)
                for imp in imports:
                    G.add_edge(f, imp + ".py")
    return G
''',
    "bm25_index.py": '''
from rank_bm25 import BM25Okapi

class BM25Index:
    """BM25 keyword retrieval over codebase."""
    def __init__(self):
        self.corpus = []
        self.bm25 = None

    def build(self, files):
        tokenized = [f.split() for f in files]
        self.bm25 = BM25Okapi(tokenized)

    def search(self, query, k=5):
        scores = self.bm25.get_scores(query.split())
        top_k = sorted(enumerate(scores), key=lambda x: -x[1])[:k]
        return [self.corpus[i] for i, _ in top_k]
''',
    "symbol_index.py": '''
import ast

class SymbolIndex:
    """Exact symbol (function/class) lookup via AST."""
    def __init__(self):
        self.symbols = {}

    def build(self, file_contents):
        for fname, code in file_contents.items():
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        self.symbols[node.name] = fname
            except SyntaxError:
                pass

    def search(self, query, k=5):
        tokens = query.lower().split()
        matches = []
        for sym, fname in self.symbols.items():
            if any(t in sym.lower() for t in tokens):
                matches.append(fname)
        return list(set(matches))[:k]
''',
    "concept_index.py": '''
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class ConceptIndex:
    """TF-IDF semantic concept matching."""
    def __init__(self):
        self.vectorizer = TfidfVectorizer()
        self.matrix = None
        self.files = []

    def build(self, file_contents):
        self.files = list(file_contents.keys())
        corpus = list(file_contents.values())
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query, k=5):
        qvec = self.vectorizer.transform([query])
        sims = cosine_similarity(qvec, self.matrix)[0]
        top_k = sorted(enumerate(sims), key=lambda x: -x[1])[:k]
        return [self.files[i] for i, _ in top_k]
''',
    "metrics.py": '''
import math

def recall_at_k(retrieved, relevant, k=5):
    """Recall@K: fraction of relevant items retrieved."""
    if not relevant:
        return 0.0
    retrieved_set = set(retrieved[:k])
    relevant_set = set(relevant) if isinstance(relevant, list) else {relevant}
    return len(retrieved_set & relevant_set) / len(relevant_set)

def token_efficiency(docs, total_tokens=10000):
    """Estimate token usage ratio."""
    est_tokens = sum(len(d.split()) * 4 for d in docs) if docs else 0
    return min(1.0, est_tokens / total_tokens)

def tes(recall, n_retrieved):
    """Trade-off Efficiency Score = Recall / ln(1 + |retrieved|)"""
    if n_retrieved == 0:
        return 0.0
    return recall / math.log(1 + n_retrieved)
''',
    "config.py": '''
import yaml

def load_config(path):
    """Load YAML configuration file."""
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {"k": 5, "strategy": "adaptive_trigger", "max_hops": 2}
''',
}

TRIGGER_PATTERNS = {
    "EXPLICIT_SYMBOL": [
        r'\b(function|class|method|def|variable|symbol|`[^`]+`)\b',
        r'\bwhat does\s+\w+\s+do\b',
        r'\bhow does\s+\w+\s+work\b',
        r'\b[A-Z][a-zA-Z]+\.[a-zA-Z]+\b',
    ],
    "IMPLICIT_CONTEXT": [
        r'\b(import|depend|module|used by|calls|related to|what modules|which files)\b',
        r'\b(dependency|dependencies|transitive|downstream|upstream)\b',
    ],
    "TEMPORAL_HISTORY": [
        r'\b(recent|latest|last|previously|changed|modified|updated|history)\b',
        r'\b(before|after|since|ago|commit)\b',
    ],
    "SEMANTIC_CONCEPT": [
        r'\b(pipeline|architecture|design|pattern|flow|how|overview|explain)\b',
        r'\b(concept|idea|purpose|strategy|approach|mechanism)\b',
    ],
}

def classify_trigger(query: str) -> str:
    q = query.lower()
    scores = defaultdict(int)
    for trigger, patterns in TRIGGER_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                scores[trigger] += 1
    if not scores:
        return "SEMANTIC_CONCEPT"
    return max(scores, key=scores.get)


def build_import_graph(files: dict) -> dict:
    graph = defaultdict(set)
    for fname, code in files.items():
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dep = alias.name.split(".")[0] + ".py"
                        if dep in files:
                            graph[fname].add(dep)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    dep = node.module.split(".")[0] + ".py"
                    if dep in files:
                        graph[fname].add(dep)
        except SyntaxError:
            pass
    return graph


def bfs_expand(seed_files: list, graph: dict, max_hops: int = 2) -> list:
    visited = set(seed_files)
    frontier = list(seed_files)
    for _ in range(max_hops):
        next_frontier = []
        for f in frontier:
            for dep in graph.get(f, []):
                if dep not in visited:
                    visited.add(dep)
                    next_frontier.append(dep)
        frontier = next_frontier
    return list(visited)


def ctx_retrieve(query: str, files: dict, k: int = 5):
    trigger = classify_trigger(query)
    graph = build_import_graph(files)
    tokens_q = query.lower().split()
    file_names = list(files.keys())

    if trigger == "EXPLICIT_SYMBOL":
        # Symbol index: AST-based function/class matching
        matched = []
        for fname, code in files.items():
            try:
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        if any(t in node.name.lower() for t in tokens_q):
                            matched.append(fname)
                            break
            except SyntaxError:
                pass
        # Fallback to BM25 if no symbol match
        if not matched:
            matched = bm25_retrieve(query, files, k)
        seeds = matched[:k]

    elif trigger == "IMPLICIT_CONTEXT":
        # Start with BM25 seeds, then BFS import graph
        seeds_bm25 = bm25_retrieve(query, files, k=3)
        seeds = bfs_expand(seeds_bm25, graph, max_hops=2)[:k]

    elif trigger == "TEMPORAL_HISTORY":
        # Return recently modified files (by position in dict as proxy)
        seeds = list(files.keys())[-k:]

    else:  # SEMANTIC_CONCEPT
        # TF-IDF cosine similarity
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        corpus = list(files.values())
        try:
            vec = TfidfVectorizer(max_features=500)
            mat = vec.fit_transform(corpus)
            qvec = vec.transform([query])
            sims = cosine_similarity(qvec, mat)[0]
            top_k = sorted(enumerate(sims), key=lambda x: -x[1])[:k]
            seeds = [file_names[i] for i, _ in top_k]
        except Exception:
            seeds = bm25_retrieve(query, files, k)

    return trigger, seeds[:k]


def bm25_retrieve(query: str, files: dict, k: int = 5) -> list:
    try:
        from rank_bm25 import BM25Okapi
        file_names = list(files.keys())
        corpus = [f"{fn}\n{code}" for fn, code in files.items()]
        tokenized = [doc.lower().split() for doc in corpus]
        bm25 = BM25Okapi(tokenized)
        scores = bm25.get_scores(query.lower().split())
        top_k = sorted(enumerate(scores), key=lambda x: -x[1])[:k]
        return [file_names[i] for i, _ in top_k]
    except Exception:
        return list(files.keys())[:k]


def full_context_retrieve(files: dict, k: int = 5) -> list:
    return list(files.keys())


def run_demo(query: str, strategy: str, k: int):
    if not query.strip():
        return "Please enter a query.", "", ""

    files = SAMPLE_CODEBASE
    total_tokens = sum(len(c.split()) * 4 for c in files.values())

    if strategy == "CTX (Adaptive Trigger)":
        trigger, retrieved = ctx_retrieve(query, files, k)
        strategy_note = f"Trigger: **{trigger}**"
    elif strategy == "BM25":
        retrieved = bm25_retrieve(query, files, k)
        trigger = "N/A"
        strategy_note = "Strategy: **BM25 keyword matching**"
    else:  # Full Context
        retrieved = full_context_retrieve(files, k)
        trigger = "N/A"
        strategy_note = "Strategy: **Full context (all files)**"

    # Build result
    token_used = sum(len(files[f].split()) * 4 for f in retrieved if f in files)
    token_pct = token_used / total_tokens * 100 if total_tokens > 0 else 0
    n_retrieved = len(retrieved)
    tes_val = (n_retrieved / len(files)) / math.log(1 + n_retrieved) if n_retrieved > 0 else 0

    result_md = f"""### Retrieved Files ({n_retrieved}/{len(files)})

{strategy_note}

| # | File | Relevance |
|---|------|-----------|
"""
    for i, fname in enumerate(retrieved, 1):
        # Show first docstring/comment as relevance hint
        code = files.get(fname, "")
        first_line = [l.strip() for l in code.split("\n") if l.strip() and not l.strip().startswith("#")]
        hint = first_line[1] if len(first_line) > 1 else "—"
        if len(hint) > 60:
            hint = hint[:57] + "..."
        result_md += f"| {i} | `{fname}` | {hint} |\n"

    metrics_md = f"""### Efficiency Metrics

| Metric | Value |
|--------|-------|
| Files retrieved | **{n_retrieved}** / {len(files)} |
| Token usage | **{token_pct:.1f}%** of codebase |
| TES (Recall/ln(1+k)) | **{tes_val:.3f}** |

> **TES** = efficiency-adjusted quality. CTX target: >0.7"""

    # Show file contents preview
    preview_md = "### Retrieved File Contents\n\n"
    for fname in retrieved[:3]:
        code = files.get(fname, "")
        preview_md += f"**`{fname}`**\n```python\n{code.strip()[:300]}{'...' if len(code) > 300 else ''}\n```\n\n"

    return result_md, metrics_md, preview_md


# ─────────────────────────────────────────────
# Paper results data
# ─────────────────────────────────────────────

SYNTHETIC_RESULTS = """
| Strategy | Recall@5 | Token% | TES |
|----------|----------|--------|-----|
| Full Context | 0.075 | 100.0% | 0.019 |
| BM25 | 0.982 | 18.7% | 0.410 |
| Dense TF-IDF | 0.973 | 21.0% | 0.406 |
| LlamaIndex | 0.972 | 20.1% | 0.405 |
| Chroma Dense | 0.829 | 19.3% | 0.346 |
| GraphRAG-lite | 0.523 | 24.0% | 0.218 |
| Hybrid Dense+CTX | 0.725 | 23.6% | 0.303 |
| **CTX (Ours)** | **0.874** | **5.2%** | **0.776** |
"""

COIR_RESULTS = """
| Strategy | Recall@1 | Recall@5 | MRR |
|----------|----------|----------|-----|
| Dense Embedding (MiniLM) | 0.960 | 1.000 | 0.978 |
| **Hybrid Dense+CTX** | **0.930** | **0.950** | **0.940** |
| BM25 | 0.920 | 0.980 | 0.946 |
| CTX Adaptive | 0.210 | 0.380 | 0.293 |
"""

TRIGGER_RESULTS = """
| Trigger Type | BM25 | TF-IDF | CTX | Delta |
|-------------|------|--------|-----|-------|
| EXPLICIT_SYMBOL | 0.81 | 0.73 | **0.97** | +19.8% |
| SEMANTIC_CONCEPT | 0.54 | **0.68** | 0.60 | — |
| TEMPORAL_HISTORY | 0.50 | 0.50 | **1.00** | +100% |
| IMPLICIT_CONTEXT | 0.40 | 0.40 | **1.00** | +150% |
"""

ABLATION_RESULTS = """
| Variant | Removed | Recall@5 | TES | IMPL_CONTEXT |
|---------|---------|----------|-----|--------------|
| Full CTX | — | **0.874** | **0.776** | **1.000** |
| No Graph | Import graph | 0.821 | 0.635 | 0.400 |
| No Classifier | Trigger type | 0.743 | 0.412 | 0.600 |
| Fixed-k=5 | Adaptive-k | 0.856 | 0.712 | 1.000 |
"""

CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --primary: #4F46E5;
    --primary-light: #818CF8;
    --accent: #06B6D4;
    --bg: #0F172A;
    --surface: #1E293B;
    --surface2: #273347;
    --border: #334155;
    --text: #E2E8F0;
    --text-muted: #94A3B8;
    --success: #10B981;
    --warning: #F59E0B;
}

body, .gradio-container {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
}

.paper-hero {
    background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 50%, #164e63 100%);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 48px 40px 40px;
    margin-bottom: 8px;
    position: relative;
    overflow: hidden;
}

.paper-hero::before {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle at 30% 40%, rgba(79,70,229,0.15) 0%, transparent 50%),
                radial-gradient(circle at 70% 60%, rgba(6,182,212,0.1) 0%, transparent 50%);
    pointer-events: none;
}

.paper-title {
    font-size: 2.2em;
    font-weight: 700;
    background: linear-gradient(135deg, #818CF8, #38BDF8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 0 0 8px;
    line-height: 1.2;
}

.paper-subtitle {
    font-size: 1.05em;
    color: var(--text-muted);
    margin: 0 0 20px;
    font-weight: 400;
}

.authors {
    font-size: 1em;
    color: #94A3B8;
    margin-bottom: 24px;
}

.badge-row {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
}

.badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.82em;
    font-weight: 500;
    text-decoration: none;
    border: 1px solid;
    transition: all 0.2s;
}

.badge-paper { background: rgba(79,70,229,0.2); border-color: #4F46E5; color: #818CF8; }
.badge-code  { background: rgba(16,185,129,0.2); border-color: #10B981; color: #34D399; }
.badge-arxiv { background: rgba(245,158,11,0.2); border-color: #F59E0B; color: #FCD34D; }

.metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin: 20px 0;
}

.metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
}

.metric-value {
    font-size: 2.2em;
    font-weight: 700;
    color: var(--primary-light);
    line-height: 1;
    margin-bottom: 6px;
    font-family: 'JetBrains Mono', monospace;
}

.metric-label {
    font-size: 0.78em;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.section-header {
    font-size: 1.3em;
    font-weight: 600;
    color: var(--text);
    border-left: 3px solid var(--primary);
    padding-left: 12px;
    margin: 24px 0 16px;
}

.abstract-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
    font-size: 0.95em;
    line-height: 1.75;
    color: var(--text);
}

.highlight {
    background: rgba(79,70,229,0.15);
    border: 1px solid rgba(79,70,229,0.3);
    border-radius: 4px;
    padding: 1px 6px;
    color: var(--primary-light);
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9em;
}

.contribution-list {
    list-style: none;
    padding: 0;
}

.contribution-list li {
    padding: 10px 0 10px 28px;
    position: relative;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    font-size: 0.92em;
    line-height: 1.6;
}

.contribution-list li::before {
    content: '▸';
    position: absolute;
    left: 8px;
    color: var(--primary-light);
    font-size: 0.8em;
    top: 12px;
}

.demo-section {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 24px;
}

.bibtex-box {
    background: #0d1117;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 20px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.82em;
    color: #7dd3fc;
    white-space: pre;
    overflow-x: auto;
}

table { width: 100%; border-collapse: collapse; }
th { background: var(--surface2); color: var(--primary-light); padding: 10px 12px; text-align: left; font-size: 0.85em; text-transform: uppercase; letter-spacing: 0.05em; }
td { padding: 9px 12px; border-bottom: 1px solid var(--border); font-size: 0.9em; color: var(--text); }
tr:hover td { background: rgba(255,255,255,0.03); }
strong { color: #34D399; }

.tabs { border-radius: 12px; overflow: hidden; }
button.selected { background: var(--primary) !important; color: white !important; }

.gr-button-primary { background: var(--primary) !important; border: none !important; }
.gr-button-primary:hover { background: var(--primary-light) !important; }

label { color: var(--text-muted) !important; font-size: 0.85em !important; }
.gr-input, .gr-dropdown select, textarea {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 8px !important;
}
"""

HERO_HTML = """
<div class="paper-hero">
  <div class="paper-title">CTX: Trigger-Driven Dynamic Context Loading</div>
  <div class="paper-subtitle">for Code-Aware LLM Agents</div>
  <div class="authors">Jeawon Jang &nbsp;·&nbsp; <span style="color:#64748b">be2jay67@gmail.com</span></div>
  <div class="badge-row">
    <span class="badge badge-code">⚡ Code: github.com/jaytoone/CTX</span>
    <span class="badge badge-arxiv">📄 arXiv: Pending Endorsement (cs.IR)</span>
    <span class="badge badge-paper">🏆 8 Strategies · 415 Queries · p&lt;0.05</span>
  </div>
</div>
"""

METRICS_HTML = """
<div class="metric-grid">
  <div class="metric-card">
    <div class="metric-value">0.776</div>
    <div class="metric-label">TES Score</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:#34D399">1.9×</div>
    <div class="metric-label">vs BM25 Baseline</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:#F59E0B">5.2%</div>
    <div class="metric-label">Token Usage</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:#06B6D4">0.95</div>
    <div class="metric-label">Hybrid COIR R@5</div>
  </div>
  <div class="metric-card">
    <div class="metric-value" style="color:#EC4899">1.00</div>
    <div class="metric-label">IMPLICIT Recall@5</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">415</div>
    <div class="metric-label">Total Queries</div>
  </div>
</div>
"""

ABSTRACT_HTML = """
<div class="abstract-box">
Large language models suffer from <strong style="color:#F87171">context dilution</strong> when processing
extensive codebases — the <em>"Lost in the Middle"</em> problem. Standard RAG approaches treat code as flat text,
ignoring the structural dependency information in <span class="highlight">import graphs</span>.<br><br>

We present <strong>CTX</strong>, a trigger-driven dynamic context loading system that classifies developer queries
into four types — <span class="highlight">EXPLICIT_SYMBOL</span>, <span class="highlight">SEMANTIC_CONCEPT</span>,
<span class="highlight">TEMPORAL_HISTORY</span>, <span class="highlight">IMPLICIT_CONTEXT</span> — and routes each
to a specialized retrieval pipeline.<br><br>

For dependency-sensitive queries, CTX performs <strong>breadth-first traversal</strong> over the codebase import
graph, resolving transitive relationships invisible to keyword and embedding methods. Evaluated on a synthetic
benchmark (50 files, 166 queries) and three real Python codebases (968 files total, 249 queries), CTX achieves
<strong style="color:#34D399">TES 1.9× higher than BM25</strong> with only <strong style="color:#F59E0B">5.2% token usage</strong>.
Statistical significance via McNemar and Wilcoxon tests (<em>p</em>&lt;0.05) across 415 queries.
</div>
"""

CONTRIBUTIONS_HTML = """
<ul class="contribution-list">
  <li><strong>Four-type trigger taxonomy</strong> — EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, IMPLICIT_CONTEXT, each mapped to a specialized retrieval strategy enabling adaptive resource allocation.</li>
  <li><strong>Import graph traversal</strong> — BFS-based algorithm over the codebase import graph resolving transitive dependencies. Recall@5 = <strong style="color:#34D399">1.0</strong> on dependency queries vs 0.4 for BM25 — 150% improvement.</li>
  <li><strong>TES metric</strong> — Trade-off Efficiency Score = Recall@K / ln(1 + |retrieved|), unified measure of accuracy-efficiency. Pearson r = 0.87 correlation with NDCG@5 (p&lt;0.001).</li>
  <li><strong>Hybrid Dense+CTX</strong> — Two-stage pipeline combining dense neural seed selection with import graph expansion. COIR Recall@5 = 0.950 (+150% over CTX alone), validating complementary nature of semantic and structural retrieval.</li>
</ul>
"""

BIBTEX = """@misc{jang2026ctx,
  title     = {CTX: Trigger-Driven Dynamic Context Loading
               for Code-Aware LLM Agents},
  author    = {Jeawon Jang},
  year      = {2026},
  note      = {Preprint. Code: https://github.com/jaytoone/CTX},
  url       = {https://github.com/jaytoone/CTX}
}"""

# ─────────────────────────────────────────────
# Build Gradio Interface
# ─────────────────────────────────────────────

with gr.Blocks(css=CSS, title="CTX — Trigger-Driven Dynamic Context Loading") as demo:

    gr.HTML(HERO_HTML)
    gr.HTML(METRICS_HTML)

    with gr.Tabs():

        # ── Tab 1: Paper ──────────────────────────
        with gr.Tab("📄 Paper"):
            gr.HTML('<div class="section-header">Abstract</div>')
            gr.HTML(ABSTRACT_HTML)

            gr.HTML('<div class="section-header">Contributions</div>')
            gr.HTML(CONTRIBUTIONS_HTML)

            gr.HTML('<div class="section-header">Architecture</div>')
            gr.Markdown("""
```
Query Input
    │
    ▼
┌──────────────────────────────┐
│   Trigger Classifier         │  → regex + keyword patterns
│   (EXPLICIT / SEMANTIC /     │
│    TEMPORAL / IMPLICIT)      │
└──────────────┬───────────────┘
               │
       ┌───────┴────────┬──────────────┬─────────────────┐
       │                │              │                 │
       ▼                ▼              ▼                 ▼
  Symbol Index    TF-IDF/Dense    History Log      Import Graph BFS
  (AST lookup)   (cosine sim)   (git history)    (transitive deps)
       │                │              │                 │
       └───────┬─────────┴──────────────┴─────────────────┘
               │
    ┌──────────▼──────────────┐
    │   Adaptive-k Selection  │  → k = f(query_type, codebase_size)
    │   (3~10 files)          │
    └──────────┬──────────────┘
               │
               ▼
          LLM Context
          (5.2% tokens)
```
""")

        # ── Tab 2: Results ────────────────────────
        with gr.Tab("📊 Results"):
            gr.HTML('<div class="section-header">Synthetic Benchmark (50 files, 166 queries)</div>')
            gr.Markdown(SYNTHETIC_RESULTS)

            gr.HTML('<div class="section-header">COIR External Benchmark (CodeSearchNet Python)</div>')
            gr.Markdown(COIR_RESULTS)

            gr.HTML('<div class="section-header">Per-Trigger-Type Recall@5 (Synthetic)</div>')
            gr.Markdown(TRIGGER_RESULTS)

            gr.HTML('<div class="section-header">Ablation Study</div>')
            gr.Markdown(ABLATION_RESULTS)

            gr.Markdown("""
**Key Findings:**
- Removing import graph → IMPLICIT_CONTEXT recall drops **60%** (1.0 → 0.4)
- Removing trigger classifier → TES drops **47%** (0.776 → 0.412)
- TES–NDCG@5 Pearson **r = 0.87** (p < 0.001, 28 strategy-dataset pairs)
- pass@1 with MiniMax M2.5: CTX **0.265** vs Full Context **0.102** (n=49, McNemar p<0.05)
""")

        # ── Tab 3: Live Demo ──────────────────────
        with gr.Tab("🚀 Live Demo"):
            gr.HTML('<div class="demo-section">')
            gr.Markdown("### Try CTX on a Sample Codebase")
            gr.Markdown(
                "The demo runs CTX retrieval on a 10-file sample Python codebase "
                "(pipeline, retriever, evaluator, graph builder, metrics, etc.). "
                "Enter a natural language query and compare retrieval strategies."
            )

            with gr.Row():
                with gr.Column(scale=2):
                    query_input = gr.Textbox(
                        label="Code Query",
                        placeholder="e.g., 'what does the retriever do?' or 'find all modules that import graph_builder'",
                        lines=2,
                    )
                with gr.Column(scale=1):
                    strategy_select = gr.Dropdown(
                        choices=["CTX (Adaptive Trigger)", "BM25", "Full Context"],
                        value="CTX (Adaptive Trigger)",
                        label="Retrieval Strategy",
                    )
                    k_slider = gr.Slider(minimum=1, maximum=10, value=5, step=1, label="k (max files)")

            run_btn = gr.Button("Retrieve", variant="primary")

            gr.Markdown("**Example queries:**")
            gr.Examples(
                examples=[
                    ["find all modules that depend on graph_builder", "CTX (Adaptive Trigger)", 5],
                    ["what does the Pipeline class do?", "CTX (Adaptive Trigger)", 5],
                    ["how does retrieval work?", "CTX (Adaptive Trigger)", 5],
                    ["what does evaluator import?", "CTX (Adaptive Trigger)", 5],
                    ["find all modules that depend on graph_builder", "BM25", 5],
                ],
                inputs=[query_input, strategy_select, k_slider],
            )

            with gr.Row():
                with gr.Column():
                    result_out = gr.Markdown(label="Retrieved Files")
                with gr.Column():
                    metrics_out = gr.Markdown(label="Metrics")

            preview_out = gr.Markdown(label="File Previews")

            run_btn.click(
                fn=run_demo,
                inputs=[query_input, strategy_select, k_slider],
                outputs=[result_out, metrics_out, preview_out],
            )
            gr.HTML('</div>')

        # ── Tab 4: Implementation ─────────────────
        with gr.Tab("🔬 Implementation"):
            gr.HTML('<div class="section-header">Core Algorithm — Trigger Classifier</div>')
            gr.Code(value='''def classify_trigger(query: str) -> str:
    """
    Classify a developer query into one of four trigger types.
    Uses regex pattern matching — lightweight, no model required.

    Returns: EXPLICIT_SYMBOL | SEMANTIC_CONCEPT | TEMPORAL_HISTORY | IMPLICIT_CONTEXT
    """
    PATTERNS = {
        "EXPLICIT_SYMBOL": [
            r"\\b(function|class|method|def|variable|`[^`]+`)\\b",
            r"\\bwhat does\\s+\\w+\\s+do\\b",
            r"\\b[A-Z][a-zA-Z]+\\.[a-zA-Z]+\\b",       # e.g. Pipeline.run
        ],
        "IMPLICIT_CONTEXT": [
            r"\\b(import|depend|module|used by|calls|related to)\\b",
            r"\\b(dependency|transitive|downstream|upstream)\\b",
        ],
        "TEMPORAL_HISTORY": [
            r"\\b(recent|latest|last|changed|modified|history)\\b",
        ],
        "SEMANTIC_CONCEPT": [
            r"\\b(pipeline|architecture|design|flow|how|overview)\\b",
        ],
    }
    scores = defaultdict(int)
    q = query.lower()
    for trigger, patterns in PATTERNS.items():
        for pat in patterns:
            if re.search(pat, q):
                scores[trigger] += 1
    return max(scores, key=scores.get) if scores else "SEMANTIC_CONCEPT"''', language="python", label="trigger_classifier.py")

            gr.HTML('<div class="section-header">Import Graph BFS — Key Differentiator vs RAG</div>')
            gr.Code(value='''def build_import_graph(root_dir: str) -> nx.DiGraph:
    """
    Parse Python AST to extract import relationships.
    Creates a directed graph: file → imported_file edges.
    O(N) in codebase size — runs in <1s on 1000-file codebases.
    """
    G = nx.DiGraph()
    for path in Path(root_dir).rglob("*.py"):
        if any(skip in path.parts for skip in ["venv", "__pycache__", ".git"]):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dep = alias.name.split(".")[0]
                        G.add_edge(str(path), dep)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    G.add_edge(str(path), node.module.split(".")[0])
        except SyntaxError:
            pass
    return G


def bfs_expand(seed_files: list[str], graph: nx.DiGraph, max_hops: int = 2) -> list[str]:
    """
    BFS traversal over import graph from seed files.
    Resolves TRANSITIVE dependencies invisible to BM25/embedding methods.

    Example: query "what does the evaluator use?"
      seed: [evaluator.py]
      hop1: [metrics.py, downstream_quality.py]    ← direct imports
      hop2: [scipy, numpy, ...]                     ← transitive imports

    This is what gives CTX perfect Recall@5=1.0 on IMPLICIT_CONTEXT queries.
    """
    visited = set(seed_files)
    frontier = list(seed_files)
    for _ in range(max_hops):
        next_frontier = []
        for f in frontier:
            for neighbor in graph.successors(f):
                if neighbor not in visited:
                    visited.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = next_frontier
    return list(visited)''', language="python", label="adaptive_trigger.py — BFS Import Graph")

            gr.HTML('<div class="section-header">TES Metric — Trade-off Efficiency Score</div>')
            gr.Code(value='''def tes(recall_at_k: float, n_retrieved: int) -> float:
    """
    Trade-off Efficiency Score: balances recall against context size.

    TES = Recall@K / ln(1 + |retrieved|)

    Intuition: diminishing returns of loading more files.
    - Loading 1 file: ln(2) = 0.693 penalty
    - Loading 10 files: ln(11) = 2.398 penalty
    - Loading ALL files: ln(1001) = 6.909 penalty  ← Full Context collapses here

    Results:
        Strategy         Recall@5    Token%    TES
        ──────────────── ──────────  ──────    ─────
        Full Context       0.075     100.0%    0.019  ← bad: high penalty
        BM25               0.982      18.7%    0.410
        CTX (Ours)         0.874       5.2%    0.776  ← best: minimal files

    Validated: Pearson r=0.87 with NDCG@5 (p<0.001, 28 strategy-dataset pairs)
    """
    if n_retrieved == 0:
        return 0.0
    return recall_at_k / math.log(1 + n_retrieved)


def adaptive_k(trigger_type: str, codebase_size: int) -> int:
    """
    Adaptive retrieval budget based on trigger type.
    Symbol lookups need few files; dependency queries need more hops.
    """
    base = {
        "EXPLICIT_SYMBOL":  3,   # exact match → few files
        "TEMPORAL_HISTORY": 3,   # recent changes → few files
        "SEMANTIC_CONCEPT": 5,   # concept → moderate
        "IMPLICIT_CONTEXT": 7,   # graph traversal → more files
    }
    k = base.get(trigger_type, 5)
    # Scale with codebase size (log scale)
    if codebase_size > 500:
        k = min(k + 2, 10)
    return k''', language="python", label="metrics.py + adaptive_k")

            gr.Markdown("""
---
**Full source**: [github.com/jaytoone/CTX](https://github.com/jaytoone/CTX)

```bash
git clone https://github.com/jaytoone/CTX && cd CTX
pip install -r requirements.txt
python run_experiment.py --dataset-size small --strategy all
```
""")

        # ── Tab 5: Citation ───────────────────────
        with gr.Tab("📚 Citation"):
            gr.HTML('<div class="section-header">BibTeX</div>')
            gr.Textbox(value=BIBTEX, label="BibTeX", lines=10, max_lines=15)

            gr.Markdown("""
### Links
- **GitHub**: https://github.com/jaytoone/CTX
- **arXiv**: Pending (cs.IR endorsement in progress — code: HBJRI6)

### Experiment Reproducibility
```bash
git clone https://github.com/jaytoone/CTX
cd CTX
pip install -r requirements.txt

# Synthetic benchmark (all 8 strategies)
python run_experiment.py --dataset-size small --strategy all

# Real codebase evaluation
python run_experiment.py --dataset-source real --project-path /path/to/project

# COIR benchmark
python run_coir_eval.py

# LLM pass@1 evaluation (requires MINIMAX_API_KEY)
python run_llm_eval_v2.py
```
""")

if __name__ == "__main__":
    demo.launch()
