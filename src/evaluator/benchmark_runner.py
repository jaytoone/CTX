"""
Benchmark runner for CTX experiment.

Orchestrates dataset generation, retrieval strategy execution,
metric computation, and result aggregation.

Supports both synthetic and real codebase datasets.
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from src.data.dataset_generator import DatasetGenerator
from src.evaluator.metrics import compute_all_metrics
from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever
from src.retrieval.bm25_retriever import BM25Retriever
from src.retrieval.chroma_retriever import ChromaDenseRetriever
from src.retrieval.dense_retriever import DenseRetriever
from src.retrieval.full_context import FullContextRetriever
from src.retrieval.graph_rag import GraphRAGRetriever
from src.retrieval.hybrid_dense_ctx import HybridDenseCTXRetriever
from src.retrieval.ranger_approx import RANGERApproxRetriever
from src.retrieval.llamaindex_retriever import LlamaIndexRetriever


@dataclass
class QueryResult:
    """Result for a single query evaluation."""
    query_id: str
    query_text: str
    trigger_type: str
    strategy: str
    retrieved_files: List[str]
    relevant_files: List[str]
    metrics: Dict[str, float]
    tokens_used: int
    total_tokens: int


@dataclass
class StrategyResult:
    """Aggregated results for one strategy across all queries."""
    strategy: str
    query_results: List[QueryResult] = field(default_factory=list)
    aggregate_metrics: Dict[str, float] = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def compute_aggregates(self) -> None:
        """Compute mean metrics across all queries."""
        if not self.query_results:
            return

        # Collect all metric keys
        all_keys = set()
        for qr in self.query_results:
            all_keys.update(qr.metrics.keys())

        for key in sorted(all_keys):
            values = [qr.metrics[key] for qr in self.query_results if key in qr.metrics]
            self.aggregate_metrics[f"mean_{key}"] = sum(values) / len(values) if values else 0.0

        # Compute per-tier aggregates
        for tier in ["head", "torso", "tail"]:
            tier_results = [
                qr for qr in self.query_results
                # Heuristic: check if query references tier data
            ]

        # Compute per-trigger-type aggregates
        trigger_types = set(qr.trigger_type for qr in self.query_results)
        for tt in trigger_types:
            tt_results = [qr for qr in self.query_results if qr.trigger_type == tt]
            for key in sorted(all_keys):
                values = [qr.metrics[key] for qr in tt_results if key in qr.metrics]
                if values:
                    self.aggregate_metrics[f"mean_{key}_{tt}"] = sum(values) / len(values)

    def compute_tier_aggregates(self, file_tiers: Dict[str, str]) -> Dict[str, Dict[str, float]]:
        """Compute metrics broken down by file tier (head/torso/tail).

        Args:
            file_tiers: Mapping of file path -> tier

        Returns:
            Dict of tier -> metric_name -> mean_value
        """
        tier_metrics: Dict[str, List[Dict[str, float]]] = {
            "head": [], "torso": [], "tail": [],
        }

        for qr in self.query_results:
            # Determine the tier of the query based on relevant files
            tiers_for_query = [file_tiers.get(f, "unknown") for f in qr.relevant_files]
            if not tiers_for_query:
                continue
            # Use the most common tier
            primary_tier = max(set(tiers_for_query), key=tiers_for_query.count)
            if primary_tier in tier_metrics:
                tier_metrics[primary_tier].append(qr.metrics)

        result = {}
        for tier, metrics_list in tier_metrics.items():
            if not metrics_list:
                result[tier] = {}
                continue
            all_keys = set()
            for m in metrics_list:
                all_keys.update(m.keys())
            result[tier] = {}
            for key in sorted(all_keys):
                values = [m[key] for m in metrics_list if key in m]
                result[tier][key] = sum(values) / len(values) if values else 0.0

        return result


@dataclass
class BenchmarkResult:
    """Complete benchmark results."""
    dataset_size: str
    strategy_results: Dict[str, StrategyResult] = field(default_factory=dict)
    file_tiers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    downstream_metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    codebase_dir: str = ""


class BenchmarkRunner:
    """Runs the full benchmark pipeline."""

    STRATEGIES = {
        "full_context": FullContextRetriever,
        "bm25": BM25Retriever,
        "dense_tfidf": DenseRetriever,
        "graph_rag": GraphRAGRetriever,
        "adaptive_trigger": AdaptiveTriggerRetriever,
        "adaptive_trigger_dense": lambda d: AdaptiveTriggerRetriever(d, use_dense=True),
        "llamaindex": LlamaIndexRetriever,
        "chroma_dense": ChromaDenseRetriever,
        "hybrid_dense_ctx": HybridDenseCTXRetriever,
        "ranger_approx": RANGERApproxRetriever,
    }

    def __init__(self, base_dir: str, seed: int = 42):
        self.base_dir = base_dir
        self.seed = seed
        self.datasets_dir = os.path.join(base_dir, "benchmarks", "datasets")
        self.results_dir = os.path.join(base_dir, "benchmarks", "results")
        os.makedirs(self.datasets_dir, exist_ok=True)
        os.makedirs(self.results_dir, exist_ok=True)

    def run(
        self,
        dataset_size: str = "small",
        strategies: Optional[List[str]] = None,
        k_values: Optional[List[int]] = None,
    ) -> BenchmarkResult:
        """Run the full benchmark with synthetic dataset.

        Args:
            dataset_size: 'small' or 'medium'
            strategies: List of strategy names to run, or None for all
            k_values: K values for Recall@K / Precision@K

        Returns:
            BenchmarkResult with all strategy results
        """
        if strategies is None:
            strategies = list(self.STRATEGIES.keys())
        if k_values is None:
            k_values = [1, 3, 5, 10]

        # Step 1: Generate dataset
        print(f"\n[1/3] Generating {dataset_size} dataset...")
        dataset_dir = os.path.join(self.datasets_dir, dataset_size)
        generator = DatasetGenerator(seed=self.seed)
        metadata = generator.generate(dataset_size, dataset_dir)

        codebase_dir = os.path.join(dataset_dir, "codebase")
        queries = metadata["queries"]
        files_meta = metadata["files"]

        # Build file tier mapping
        file_tiers = {f["path"]: f["tier"] for f in files_meta}

        print(f"    Generated {metadata['file_count']} files, {len(queries)} queries")
        print(f"    Tiers: {metadata['tier_distribution']}")

        benchmark = self._run_strategies(
            codebase_dir=codebase_dir,
            queries=queries,
            file_tiers=file_tiers,
            strategies=strategies,
            k_values=k_values,
            dataset_label=dataset_size,
            metadata={
                "file_count": metadata["file_count"],
                "query_count": len(queries),
                "tier_distribution": metadata["tier_distribution"],
                "seed": self.seed,
            },
        )

        return benchmark

    def run_real(
        self,
        project_path: str,
        strategies: Optional[List[str]] = None,
        k_values: Optional[List[int]] = None,
    ) -> BenchmarkResult:
        """Run benchmark on a real codebase.

        Args:
            project_path: Path to the real Python project
            strategies: List of strategy names to run, or None for all
            k_values: K values for Recall@K / Precision@K

        Returns:
            BenchmarkResult with all strategy results
        """
        from src.data.real_codebase_loader import RealCodebaseLoader

        if strategies is None:
            strategies = list(self.STRATEGIES.keys())
        if k_values is None:
            k_values = [1, 3, 5, 10]

        # Step 1: Load real codebase
        print(f"\n[1/3] Loading real codebase from {project_path}...")
        loader = RealCodebaseLoader(project_path, seed=self.seed)
        metadata = loader.load()

        codebase_dir = metadata["codebase_dir"]
        queries = metadata["queries"]
        files_meta = metadata["files"]
        project_name = metadata["project_name"]

        # Build file tier mapping
        file_tiers = {f["path"]: f.get("tier", "tail") for f in files_meta}

        print(f"    Loaded {metadata['file_count']} files, {len(queries)} queries")
        print(f"    Project: {project_name}")
        print(f"    Tiers: {metadata['tier_distribution']}")

        benchmark = self._run_strategies(
            codebase_dir=codebase_dir,
            queries=queries,
            file_tiers=file_tiers,
            strategies=strategies,
            k_values=k_values,
            dataset_label=f"real_{project_name}",
            metadata={
                "file_count": metadata["file_count"],
                "query_count": len(queries),
                "tier_distribution": metadata["tier_distribution"],
                "seed": self.seed,
                "project_name": project_name,
                "project_path": project_path,
            },
        )

        return benchmark

    def _run_strategies(
        self,
        codebase_dir: str,
        queries: List[Dict],
        file_tiers: Dict[str, str],
        strategies: List[str],
        k_values: List[int],
        dataset_label: str,
        metadata: Dict[str, Any],
    ) -> BenchmarkResult:
        """Core strategy execution shared by synthetic and real modes."""
        print(f"\n[2/3] Running strategies: {', '.join(strategies)}...")
        benchmark = BenchmarkResult(
            dataset_size=dataset_label,
            file_tiers=file_tiers,
            metadata=metadata,
            codebase_dir=codebase_dir,
        )

        for strategy_name in strategies:
            if strategy_name not in self.STRATEGIES:
                print(f"    WARNING: Unknown strategy '{strategy_name}', skipping")
                continue

            print(f"    Running {strategy_name}...")
            start_time = time.time()

            retriever_class = self.STRATEGIES[strategy_name]
            retriever = retriever_class(codebase_dir)

            strategy_result = StrategyResult(strategy=strategy_name)

            for query_data in queries:
                q_id = query_data["id"]
                q_text = query_data["text"]
                q_type = query_data["trigger_type"]
                q_relevant = query_data["relevant_files"]

                # Run retrieval
                result = retriever.retrieve(q_id, q_text, k=max(k_values))

                # Compute metrics
                metrics = compute_all_metrics(
                    retrieved=result.retrieved_files,
                    relevant=q_relevant,
                    tokens_used=result.tokens_used,
                    total_tokens=result.total_tokens,
                    k_values=k_values,
                )

                query_result = QueryResult(
                    query_id=q_id,
                    query_text=q_text,
                    trigger_type=q_type,
                    strategy=strategy_name,
                    retrieved_files=result.retrieved_files[:max(k_values)],
                    relevant_files=q_relevant,
                    metrics=metrics,
                    tokens_used=result.tokens_used,
                    total_tokens=result.total_tokens,
                )
                strategy_result.query_results.append(query_result)

            elapsed = time.time() - start_time
            strategy_result.elapsed_seconds = elapsed
            strategy_result.compute_aggregates()

            benchmark.strategy_results[strategy_name] = strategy_result
            print(f"    {strategy_name}: {len(strategy_result.query_results)} queries in {elapsed:.2f}s")

        # Compute downstream quality metrics
        print(f"\n    Computing downstream quality metrics (CCS, ASS)...")
        self._compute_downstream(benchmark, codebase_dir)

        # Step 3: Save results
        print(f"\n[3/3] Saving results...")
        self._save_results(benchmark)

        return benchmark

    def _compute_downstream(self, benchmark: BenchmarkResult, codebase_dir: str) -> None:
        """Compute downstream quality metrics for all strategies."""
        from src.evaluator.downstream_quality import compute_downstream_metrics

        for name, sr in benchmark.strategy_results.items():
            dm = compute_downstream_metrics(sr, codebase_dir)
            benchmark.downstream_metrics[name] = {
                "mean_ccs": dm["mean_ccs"],
                "mean_ass": dm["mean_ass"],
            }
            # Also inject into aggregate metrics
            sr.aggregate_metrics["mean_ccs"] = dm["mean_ccs"]
            sr.aggregate_metrics["mean_ass"] = dm["mean_ass"]
            print(f"      {name}: CCS={dm['mean_ccs']:.4f}, ASS={dm['mean_ass']:.4f}")

    def _save_results(self, benchmark: BenchmarkResult) -> None:
        """Save benchmark results to JSON."""
        output = {
            "dataset_size": benchmark.dataset_size,
            "metadata": benchmark.metadata,
            "strategies": {},
            "downstream_metrics": benchmark.downstream_metrics,
        }

        # Save per-query results for error analysis and statistical tests
        query_results_by_strategy = {}

        for name, sr in benchmark.strategy_results.items():
            tier_agg = sr.compute_tier_aggregates(benchmark.file_tiers)
            output["strategies"][name] = {
                "aggregate_metrics": sr.aggregate_metrics,
                "tier_metrics": tier_agg,
                "elapsed_seconds": sr.elapsed_seconds,
                "query_count": len(sr.query_results),
            }

            # Store per-query results
            query_results_by_strategy[name] = [
                {
                    "query_id": qr.query_id,
                    "query_text": qr.query_text,
                    "trigger_type": qr.trigger_type,
                    "retrieved_files": qr.retrieved_files,
                    "relevant_files": qr.relevant_files,
                    "metrics": qr.metrics,
                    "tokens_used": qr.tokens_used,
                    "total_tokens": qr.total_tokens,
                }
                for qr in sr.query_results
            ]

        output["_query_results"] = query_results_by_strategy

        result_path = os.path.join(self.results_dir, f"benchmark_{benchmark.dataset_size}.json")
        with open(result_path, "w") as f:
            json.dump(output, f, indent=2)

        # Run statistical tests if multiple strategies available
        self._run_statistical_tests(benchmark)

        print(f"    Results saved to {result_path}")

    def _run_statistical_tests(self, benchmark: BenchmarkResult) -> None:
        """Run statistical significance tests and save results."""
        try:
            from src.evaluator.statistical_tests import compute_statistical_summary
        except ImportError:
            print("    WARNING: scipy not available, skipping statistical tests")
            return

        # Collect per-query Recall@5 scores for each strategy
        strategy_scores = {}
        for name, sr in benchmark.strategy_results.items():
            scores = [qr.metrics.get("recall@5", 0.0) for qr in sr.query_results]
            strategy_scores[name] = scores

        if not strategy_scores:
            return

        summary = compute_statistical_summary(
            strategy_scores,
            reference_strategy="adaptive_trigger",
            metric_name="recall@5",
            threshold=0.0,
        )

        stat_path = os.path.join(
            self.results_dir,
            f"statistical_tests_{benchmark.dataset_size}.json",
        )
        with open(stat_path, "w") as f:
            json.dump(summary, f, indent=2)

        print(f"    Statistical tests saved to {stat_path}")

    def run_ablation(
        self,
        codebase_dir: str,
        queries: list,
        file_tiers: dict,
        k_values: list = None,
        dataset_label: str = "ablation",
        metadata: dict = None,
    ) -> BenchmarkResult:
        """Run ablation study with 4 variants.

        Args:
            codebase_dir: Path to codebase
            queries: List of query dicts
            file_tiers: File tier mapping
            k_values: K values for Recall@K
            dataset_label: Label for saving results
            metadata: Additional metadata

        Returns:
            BenchmarkResult with ablation variant results
        """
        from src.retrieval.ablation_variants import (
            AblationVariantB, AblationVariantC, AblationVariantD,
        )
        from src.retrieval.adaptive_trigger import AdaptiveTriggerRetriever

        if k_values is None:
            k_values = [1, 3, 5, 10]
        if metadata is None:
            metadata = {}

        ablation_strategies = {
            "full_ctx_A": AdaptiveTriggerRetriever,
            "no_graph_B": AblationVariantB,
            "no_classifier_C": AblationVariantC,
            "fixed_k5_D": AblationVariantD,
        }

        print(f"\n[Ablation] Running 4 variants on {dataset_label}...")
        benchmark = BenchmarkResult(
            dataset_size=f"ablation_{dataset_label}",
            file_tiers=file_tiers,
            metadata=metadata,
            codebase_dir=codebase_dir,
        )

        for variant_name, variant_class in ablation_strategies.items():
            print(f"    Running {variant_name}...")
            start_time = time.time()
            retriever = variant_class(codebase_dir)
            strategy_result = StrategyResult(strategy=variant_name)

            for query_data in queries:
                q_id = query_data["id"]
                q_text = query_data["text"]
                q_type = query_data["trigger_type"]
                q_relevant = query_data["relevant_files"]

                result = retriever.retrieve(q_id, q_text, k=max(k_values))
                metrics = compute_all_metrics(
                    retrieved=result.retrieved_files,
                    relevant=q_relevant,
                    tokens_used=result.tokens_used,
                    total_tokens=result.total_tokens,
                    k_values=k_values,
                )

                query_result = QueryResult(
                    query_id=q_id,
                    query_text=q_text,
                    trigger_type=q_type,
                    strategy=variant_name,
                    retrieved_files=result.retrieved_files[:max(k_values)],
                    relevant_files=q_relevant,
                    metrics=metrics,
                    tokens_used=result.tokens_used,
                    total_tokens=result.total_tokens,
                )
                strategy_result.query_results.append(query_result)

            elapsed = time.time() - start_time
            strategy_result.elapsed_seconds = elapsed
            strategy_result.compute_aggregates()
            benchmark.strategy_results[variant_name] = strategy_result
            print(f"    {variant_name}: {len(strategy_result.query_results)} queries in {elapsed:.2f}s")

        self._save_results(benchmark)
        return benchmark
