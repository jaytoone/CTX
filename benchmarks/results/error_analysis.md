# CTX Error Analysis Report


## Dataset: small
Files: 50, Queries: 166

### full_context
- Queries: 166, Failures: 156, Rate: 94.0%
- Patterns: {'FALSE_POSITIVE': 149, 'FALSE_NEGATIVE': 2, 'GRAPH_MISS': 5}
  - EXPLICIT_SYMBOL: 72/79 (91%)
  - IMPLICIT_CONTEXT: 5/5 (100%)
  - SEMANTIC_CONCEPT: 69/72 (96%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [FALSE_POSITIVE] "Find all code related to mock" missed=4
  - [FALSE_POSITIVE] "Find all code related to test" missed=4
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_lxos?" missed=4

### bm25
- Queries: 166, Failures: 5, Rate: 3.0%
- Patterns: {'GRAPH_MISS': 5}
  - EXPLICIT_SYMBOL: 0/79 (0%)
  - IMPLICIT_CONTEXT: 5/5 (100%)
  - SEMANTIC_CONCEPT: 0/72 (0%)
  - TEMPORAL_HISTORY: 0/10 (0%)
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_lxos?" missed=3
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_ndjb?" missed=3
  - [GRAPH_MISS] "What modules are needed to fully understand config_mod_hqpt?" missed=2

### dense_tfidf
- Queries: 166, Failures: 9, Rate: 5.4%
- Patterns: {'FALSE_NEGATIVE': 1, 'FALSE_POSITIVE': 3, 'GRAPH_MISS': 5}
  - EXPLICIT_SYMBOL: 0/79 (0%)
  - IMPLICIT_CONTEXT: 5/5 (100%)
  - SEMANTIC_CONCEPT: 4/72 (6%)
  - TEMPORAL_HISTORY: 0/10 (0%)
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_lxos?" missed=3
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_ndjb?" missed=3
  - [FALSE_POSITIVE] "Find all code related to test" missed=2

### graph_rag
- Queries: 166, Failures: 88, Rate: 53.0%
- Patterns: {'FALSE_POSITIVE': 84, 'GRAPH_MISS': 4}
  - EXPLICIT_SYMBOL: 6/79 (8%)
  - IMPLICIT_CONTEXT: 4/5 (80%)
  - SEMANTIC_CONCEPT: 70/72 (97%)
  - TEMPORAL_HISTORY: 8/10 (80%)
  - [FALSE_POSITIVE] "Find all code related to configuration" missed=4
  - [FALSE_POSITIVE] "Find all code related to mock" missed=4
  - [FALSE_POSITIVE] "Find all code related to test" missed=4

### adaptive_trigger
- Queries: 166, Failures: 37, Rate: 22.3%
- Patterns: {'FALSE_POSITIVE': 22, 'FALSE_NEGATIVE': 15}
  - EXPLICIT_SYMBOL: 1/79 (1%)
  - IMPLICIT_CONTEXT: 0/5 (0%)
  - SEMANTIC_CONCEPT: 36/72 (50%)
  - TEMPORAL_HISTORY: 0/10 (0%)
  - [FALSE_POSITIVE] "Find all code related to test" missed=3
  - [FALSE_POSITIVE] "Find all code related to file" missed=2
  - [FALSE_NEGATIVE] "Find all code related to environment" missed=2

### llamaindex
- Queries: 166, Failures: 10, Rate: 6.0%
- Patterns: {'FALSE_POSITIVE': 3, 'FALSE_NEGATIVE': 2, 'GRAPH_MISS': 5}
  - EXPLICIT_SYMBOL: 0/79 (0%)
  - IMPLICIT_CONTEXT: 5/5 (100%)
  - SEMANTIC_CONCEPT: 5/72 (7%)
  - TEMPORAL_HISTORY: 0/10 (0%)
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_lxos?" missed=3
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_ndjb?" missed=3
  - [GRAPH_MISS] "What modules are needed to fully understand config_mod_hqpt?" missed=2

### chroma_dense
- Queries: 166, Failures: 39, Rate: 23.5%
- Patterns: {'FALSE_POSITIVE': 33, 'FALSE_NEGATIVE': 1, 'GRAPH_MISS': 5}
  - EXPLICIT_SYMBOL: 10/79 (13%)
  - IMPLICIT_CONTEXT: 5/5 (100%)
  - SEMANTIC_CONCEPT: 23/72 (32%)
  - TEMPORAL_HISTORY: 1/10 (10%)
  - [GRAPH_MISS] "What modules are needed to fully understand cache_mod_lxos?" missed=3
  - [FALSE_POSITIVE] "Find all code related to environment" missed=2
  - [FALSE_POSITIVE] "Find all code related to injection" missed=2

### Cross-Strategy: CTX vs Baselines (small)
- **adaptive_trigger vs bm25**: adaptive_trigger vs bm25 (n=166): adaptive_trigger-only wins=3, bm25-only wins=10, both succeed=153, both fail=0
  CTX-only wins: {'IMPLICIT_CONTEXT': 3}
  IMPLICIT example: "What modules are needed to fully understand config_mod_hqpt?"
- **adaptive_trigger vs llamaindex**: adaptive_trigger vs llamaindex (n=166): adaptive_trigger-only wins=3, llamaindex-only wins=10, both succeed=153, both fail=0
  CTX-only wins: {'IMPLICIT_CONTEXT': 3}
  IMPLICIT example: "What modules are needed to fully understand config_mod_hqpt?"
- **adaptive_trigger vs dense_tfidf**: adaptive_trigger vs dense_tfidf (n=166): adaptive_trigger-only wins=3, dense_tfidf-only wins=10, both succeed=153, both fail=0
  CTX-only wins: {'IMPLICIT_CONTEXT': 3}
  IMPLICIT example: "What modules are needed to fully understand config_mod_hqpt?"
- **adaptive_trigger vs chroma_dense**: adaptive_trigger vs chroma_dense (n=166): adaptive_trigger-only wins=21, chroma_dense-only wins=8, both succeed=135, both fail=2
  CTX-only wins: {'EXPLICIT_SYMBOL': 10, 'SEMANTIC_CONCEPT': 7, 'TEMPORAL_HISTORY': 1, 'IMPLICIT_CONTEXT': 3}
  IMPLICIT example: "What modules are needed to fully understand config_mod_hqpt?"

## Dataset: real_GraphPrompt
Files: 73, Queries: 80

### full_context
- Queries: 80, Failures: 74, Rate: 92.5%
- Patterns: {'FALSE_POSITIVE': 59, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 30/35 (86%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 9/10 (90%)
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=12
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=12
  - [FALSE_POSITIVE] "Find all code related to thinking" missed=10

### bm25
- Queries: 80, Failures: 51, Rate: 63.7%
- Patterns: {'FALSE_POSITIVE': 36, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 9/35 (26%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 7/10 (70%)
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=14
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=12
  - [FALSE_POSITIVE] "Find all code related to thinking" missed=10

### dense_tfidf
- Queries: 80, Failures: 45, Rate: 56.2%
- Patterns: {'FALSE_POSITIVE': 29, 'FALSE_NEGATIVE': 2, 'GRAPH_MISS': 14}
  - EXPLICIT_SYMBOL: 7/35 (20%)
  - IMPLICIT_CONTEXT: 14/15 (93%)
  - SEMANTIC_CONCEPT: 18/20 (90%)
  - TEMPORAL_HISTORY: 6/10 (60%)
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=14
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=12
  - [GRAPH_MISS] "What modules are needed to fully understand runner?" missed=10

### graph_rag
- Queries: 80, Failures: 46, Rate: 57.5%
- Patterns: {'FALSE_POSITIVE': 32, 'FALSE_NEGATIVE': 1, 'GRAPH_MISS': 13}
  - EXPLICIT_SYMBOL: 3/35 (9%)
  - IMPLICIT_CONTEXT: 13/15 (87%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=11
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=11
  - [GRAPH_MISS] "What modules are needed to fully understand harness?" missed=10

### adaptive_trigger
- Queries: 80, Failures: 69, Rate: 86.2%
- Patterns: {'FALSE_POSITIVE': 54, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 29/35 (83%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 5/10 (50%)
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=14
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=12
  - [FALSE_POSITIVE] "Find all code related to thinking" missed=10

### llamaindex
- Queries: 80, Failures: 49, Rate: 61.3%
- Patterns: {'FALSE_POSITIVE': 35, 'GRAPH_MISS': 14}
  - EXPLICIT_SYMBOL: 7/35 (20%)
  - IMPLICIT_CONTEXT: 14/15 (93%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 8/10 (80%)
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=14
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=12
  - [GRAPH_MISS] "What modules are needed to fully understand runner?" missed=10

### chroma_dense
- Queries: 80, Failures: 51, Rate: 63.7%
- Patterns: {'FALSE_POSITIVE': 36, 'FALSE_NEGATIVE': 1, 'GRAPH_MISS': 14}
  - EXPLICIT_SYMBOL: 14/35 (40%)
  - IMPLICIT_CONTEXT: 14/15 (93%)
  - SEMANTIC_CONCEPT: 19/20 (95%)
  - TEMPORAL_HISTORY: 4/10 (40%)
  - [GRAPH_MISS] "What modules are needed to fully understand app?" missed=12
  - [GRAPH_MISS] "What modules are needed to fully understand search?" missed=11
  - [GRAPH_MISS] "What modules are needed to fully understand harness?" missed=11

### Cross-Strategy: CTX vs Baselines (real_GraphPrompt)
- **adaptive_trigger vs bm25**: adaptive_trigger vs bm25 (n=80): adaptive_trigger-only wins=4, bm25-only wins=28, both succeed=8, both fail=40
  CTX-only wins: {'EXPLICIT_SYMBOL': 1, 'TEMPORAL_HISTORY': 2, 'IMPLICIT_CONTEXT': 1}
  IMPLICIT example: "What modules are needed to fully understand test_mixed_effec"
- **adaptive_trigger vs llamaindex**: adaptive_trigger vs llamaindex (n=80): adaptive_trigger-only wins=3, llamaindex-only wins=33, both succeed=9, both fail=35
  CTX-only wins: {'TEMPORAL_HISTORY': 3}
- **adaptive_trigger vs dense_tfidf**: adaptive_trigger vs dense_tfidf (n=80): adaptive_trigger-only wins=2, dense_tfidf-only wins=34, both succeed=10, both fail=34
  CTX-only wins: {'TEMPORAL_HISTORY': 2}
- **adaptive_trigger vs chroma_dense**: adaptive_trigger vs chroma_dense (n=80): adaptive_trigger-only wins=3, chroma_dense-only wins=26, both succeed=9, both fail=42
  CTX-only wins: {'EXPLICIT_SYMBOL': 2, 'TEMPORAL_HISTORY': 1}

## Dataset: real_OneViral
Files: 299, Queries: 84

### full_context
- Queries: 84, Failures: 84, Rate: 100.0%
- Patterns: {'FALSE_POSITIVE': 69, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 39/39 (100%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=10
  - [FALSE_POSITIVE] "Find all code related to count" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7

### bm25
- Queries: 84, Failures: 75, Rate: 89.3%
- Patterns: {'FALSE_POSITIVE': 60, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 32/39 (82%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 18/20 (90%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=9
  - [GRAPH_MISS] "What modules are needed to fully understand long_form_genera" missed=7
  - [GRAPH_MISS] "What modules are needed to fully understand auto_discover_ap" missed=7

### dense_tfidf
- Queries: 84, Failures: 68, Rate: 81.0%
- Patterns: {'FALSE_POSITIVE': 53, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 24/39 (62%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 9/10 (90%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=10
  - [FALSE_POSITIVE] "Find all code related to count" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7

### graph_rag
- Queries: 84, Failures: 70, Rate: 83.3%
- Patterns: {'FALSE_POSITIVE': 58, 'GRAPH_MISS': 12}
  - EXPLICIT_SYMBOL: 28/39 (72%)
  - IMPLICIT_CONTEXT: 12/15 (80%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=10
  - [FALSE_POSITIVE] "Find all code related to count" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7

### adaptive_trigger
- Queries: 84, Failures: 70, Rate: 83.3%
- Patterns: {'FALSE_POSITIVE': 55, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 25/39 (64%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=10
  - [FALSE_POSITIVE] "Find all code related to count" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7

### llamaindex
- Queries: 84, Failures: 57, Rate: 67.9%
- Patterns: {'FALSE_POSITIVE': 43, 'GRAPH_MISS': 14}
  - EXPLICIT_SYMBOL: 15/39 (38%)
  - IMPLICIT_CONTEXT: 14/15 (93%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 8/10 (80%)
  - [FALSE_POSITIVE] "Find all code related to viral" missed=9
  - [FALSE_POSITIVE] "Find all code related to count" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7

### chroma_dense
- Queries: 84, Failures: 66, Rate: 78.6%
- Patterns: {'FALSE_POSITIVE': 52, 'FALSE_NEGATIVE': 1, 'GRAPH_MISS': 13}
  - EXPLICIT_SYMBOL: 25/39 (64%)
  - IMPLICIT_CONTEXT: 13/15 (87%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 8/10 (80%)
  - [FALSE_NEGATIVE] "Find all code related to viral" missed=7
  - [FALSE_POSITIVE] "Find all code related to period" missed=7
  - [GRAPH_MISS] "What modules are needed to fully understand auto_discover_ap" missed=7

### Cross-Strategy: CTX vs Baselines (real_OneViral)
- **adaptive_trigger vs bm25**: adaptive_trigger vs bm25 (n=84): adaptive_trigger-only wins=11, bm25-only wins=10, both succeed=5, both fail=58
  CTX-only wins: {'EXPLICIT_SYMBOL': 9, 'IMPLICIT_CONTEXT': 2}
  IMPLICIT example: "What modules are needed to fully understand test_crypto_asse"
- **adaptive_trigger vs llamaindex**: adaptive_trigger vs llamaindex (n=84): adaptive_trigger-only wins=5, llamaindex-only wins=22, both succeed=11, both fail=46
  CTX-only wins: {'EXPLICIT_SYMBOL': 5}
- **adaptive_trigger vs dense_tfidf**: adaptive_trigger vs dense_tfidf (n=84): adaptive_trigger-only wins=8, dense_tfidf-only wins=13, both succeed=8, both fail=55
  CTX-only wins: {'EXPLICIT_SYMBOL': 8}
- **adaptive_trigger vs chroma_dense**: adaptive_trigger vs chroma_dense (n=84): adaptive_trigger-only wins=6, chroma_dense-only wins=11, both succeed=10, both fail=57
  CTX-only wins: {'EXPLICIT_SYMBOL': 5, 'IMPLICIT_CONTEXT': 1}
  IMPLICIT example: "What modules are needed to fully understand cache_flag_prese"

## Dataset: real_AgentNode
Files: 596, Queries: 85

### full_context
- Queries: 85, Failures: 84, Rate: 98.8%
- Patterns: {'FALSE_POSITIVE': 69, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 39/40 (98%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=382
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=239
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=51

### bm25
- Queries: 85, Failures: 66, Rate: 77.6%
- Patterns: {'FALSE_POSITIVE': 50, 'FALSE_NEGATIVE': 1, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 25/40 (62%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 19/20 (95%)
  - TEMPORAL_HISTORY: 7/10 (70%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=381
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=238
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=51

### dense_tfidf
- Queries: 85, Failures: 62, Rate: 72.9%
- Patterns: {'FALSE_POSITIVE': 47, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 21/40 (52%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 6/10 (60%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=382
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=238
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=51

### graph_rag
- Queries: 85, Failures: 83, Rate: 97.6%
- Patterns: {'FALSE_POSITIVE': 68, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 38/40 (95%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=380
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=237
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=48

### adaptive_trigger
- Queries: 85, Failures: 71, Rate: 83.5%
- Patterns: {'FALSE_POSITIVE': 56, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 28/40 (70%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 8/10 (80%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=382
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=239
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=51

### llamaindex
- Queries: 85, Failures: 71, Rate: 83.5%
- Patterns: {'FALSE_POSITIVE': 56, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 27/40 (68%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 19/20 (95%)
  - TEMPORAL_HISTORY: 10/10 (100%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=381
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=237
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=50

### chroma_dense
- Queries: 85, Failures: 75, Rate: 88.2%
- Patterns: {'FALSE_POSITIVE': 60, 'GRAPH_MISS': 15}
  - EXPLICIT_SYMBOL: 31/40 (78%)
  - IMPLICIT_CONTEXT: 15/15 (100%)
  - SEMANTIC_CONCEPT: 20/20 (100%)
  - TEMPORAL_HISTORY: 9/10 (90%)
  - [GRAPH_MISS] "What modules are needed to fully understand deprecation?" missed=382
  - [GRAPH_MISS] "What modules are needed to fully understand lock?" missed=238
  - [GRAPH_MISS] "What modules are needed to fully understand cmdoptions?" missed=50

### Cross-Strategy: CTX vs Baselines (real_AgentNode)
- **adaptive_trigger vs bm25**: adaptive_trigger vs bm25 (n=85): adaptive_trigger-only wins=3, bm25-only wins=9, both succeed=12, both fail=61
  CTX-only wins: {'EXPLICIT_SYMBOL': 2, 'IMPLICIT_CONTEXT': 1}
  IMPLICIT example: "What modules are needed to fully understand mtp_loss?"
- **adaptive_trigger vs llamaindex**: adaptive_trigger vs llamaindex (n=85): adaptive_trigger-only wins=9, llamaindex-only wins=11, both succeed=6, both fail=59
  CTX-only wins: {'EXPLICIT_SYMBOL': 7, 'TEMPORAL_HISTORY': 2}
- **adaptive_trigger vs dense_tfidf**: adaptive_trigger vs dense_tfidf (n=85): adaptive_trigger-only wins=7, dense_tfidf-only wins=19, both succeed=8, both fail=51
  CTX-only wins: {'EXPLICIT_SYMBOL': 6, 'TEMPORAL_HISTORY': 1}
- **adaptive_trigger vs chroma_dense**: adaptive_trigger vs chroma_dense (n=85): adaptive_trigger-only wins=10, chroma_dense-only wins=9, both succeed=5, both fail=61
  CTX-only wins: {'EXPLICIT_SYMBOL': 8, 'TEMPORAL_HISTORY': 2}
