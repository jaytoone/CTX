"""
Synthetic evaluation dataset generator for CTX experiment.

Generates Python codebases with Head/Torso/Tail Zipf distribution,
along with ground-truth query-to-file relevance labels.
"""

import json
import math
import os
import random
import string
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class FileSpec:
    """Specification for a generated Python file."""
    path: str
    module_name: str
    tier: str  # head, torso, tail
    reference_count: int
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    concepts: List[str] = field(default_factory=list)


@dataclass
class Query:
    """A test query with ground-truth relevant files."""
    id: str
    text: str
    trigger_type: str  # EXPLICIT_SYMBOL, SEMANTIC_CONCEPT, TEMPORAL_HISTORY, IMPLICIT_CONTEXT
    relevant_files: List[str]
    relevant_symbols: List[str] = field(default_factory=list)


# Domain vocabularies for realistic code generation
DOMAINS = {
    "auth": {
        "concepts": ["authentication", "authorization", "login", "session", "token", "password", "jwt", "oauth"],
        "functions": ["authenticate_user", "verify_token", "hash_password", "create_session", "check_permission",
                       "refresh_token", "logout_user", "validate_credentials"],
        "classes": ["AuthManager", "TokenService", "SessionStore", "PermissionChecker"],
    },
    "database": {
        "concepts": ["database", "query", "connection", "migration", "schema", "orm", "transaction", "pool"],
        "functions": ["connect_db", "execute_query", "run_migration", "create_pool", "close_connection",
                       "begin_transaction", "commit_transaction", "rollback"],
        "classes": ["DatabaseConnection", "QueryBuilder", "MigrationRunner", "ConnectionPool"],
    },
    "api": {
        "concepts": ["endpoint", "request", "response", "middleware", "route", "handler", "rest", "graphql"],
        "functions": ["handle_request", "parse_body", "send_response", "register_route", "apply_middleware",
                       "validate_input", "rate_limit", "serialize_output"],
        "classes": ["Router", "RequestHandler", "MiddlewareChain", "APIServer"],
    },
    "cache": {
        "concepts": ["cache", "redis", "memcached", "invalidation", "ttl", "eviction", "lru"],
        "functions": ["get_cached", "set_cache", "invalidate_cache", "compute_ttl", "evict_lru",
                       "warm_cache", "cache_decorator"],
        "classes": ["CacheManager", "LRUCache", "CachePolicy", "RedisAdapter"],
    },
    "logging": {
        "concepts": ["logging", "log", "trace", "debug", "monitor", "alert", "metric"],
        "functions": ["setup_logger", "log_event", "trace_request", "emit_metric", "send_alert",
                       "rotate_logs", "format_message"],
        "classes": ["Logger", "LogFormatter", "MetricCollector", "AlertManager"],
    },
    "file_io": {
        "concepts": ["file", "stream", "buffer", "read", "write", "serialize", "csv", "json_parse"],
        "functions": ["read_file", "write_file", "parse_csv", "serialize_json", "stream_data",
                       "compress_file", "validate_path"],
        "classes": ["FileReader", "StreamProcessor", "CSVParser", "JSONSerializer"],
    },
    "config": {
        "concepts": ["configuration", "settings", "environment", "dotenv", "yaml_config", "feature_flag"],
        "functions": ["load_config", "get_setting", "parse_env", "merge_configs", "validate_config",
                       "toggle_feature", "reload_settings"],
        "classes": ["ConfigLoader", "SettingsManager", "FeatureFlagService", "EnvParser"],
    },
    "testing": {
        "concepts": ["test", "mock", "fixture", "assertion", "coverage", "benchmark", "stub"],
        "functions": ["run_tests", "create_mock", "setup_fixture", "assert_equal", "measure_coverage",
                       "benchmark_function", "generate_test_data"],
        "classes": ["TestRunner", "MockFactory", "FixtureManager", "CoverageReporter"],
    },
    "security": {
        "concepts": ["encryption", "hashing", "sanitize", "xss", "csrf", "injection", "firewall"],
        "functions": ["encrypt_data", "decrypt_data", "sanitize_input", "check_csrf", "prevent_injection",
                       "generate_key", "verify_signature"],
        "classes": ["Encryptor", "InputSanitizer", "FirewallRule", "KeyManager"],
    },
    "scheduling": {
        "concepts": ["scheduler", "cron", "task_queue", "worker", "retry", "deadline", "periodic"],
        "functions": ["schedule_task", "run_worker", "retry_failed", "parse_cron", "check_deadline",
                       "enqueue_job", "process_queue"],
        "classes": ["TaskScheduler", "WorkerPool", "RetryPolicy", "CronParser"],
    },
}

LEGACY_DOMAINS = {
    "legacy_protocol": {
        "concepts": ["legacy_protocol", "backward_compat", "deprecated_api", "migration_shim"],
        "functions": ["decode_legacy_packet", "convert_v1_to_v2", "legacy_handshake", "shim_old_format"],
        "classes": ["LegacyProtocolHandler", "V1Adapter", "DeprecationWrapper"],
    },
    "edge_case": {
        "concepts": ["edge_case", "boundary", "overflow", "unicode_edge", "null_handling"],
        "functions": ["handle_overflow", "sanitize_unicode", "null_coalesce", "boundary_check",
                       "handle_empty_input"],
        "classes": ["BoundaryValidator", "NullHandler", "UnicodeNormalizer"],
    },
}


def _zipf_weights(n: int, s: float = 1.0) -> List[float]:
    """Generate Zipf distribution weights for n items."""
    raw = [1.0 / (k ** s) for k in range(1, n + 1)]
    total = sum(raw)
    return [w / total for w in raw]


def _random_identifier(prefix: str = "", length: int = 6) -> str:
    """Generate a random identifier."""
    suffix = "".join(random.choices(string.ascii_lowercase, k=length))
    return f"{prefix}_{suffix}" if prefix else suffix


def _generate_function_body(func_name: str, imports: List[str], depth: int = 2) -> str:
    """Generate a realistic-looking function body."""
    lines = [f"def {func_name}(data, config=None):"]
    lines.append(f'    """Process data using {func_name} logic."""')

    # Add some variable assignments
    lines.append(f"    result = {{}}")
    lines.append(f"    if config is None:")
    lines.append(f"        config = {{}}")

    # Add some logic
    lines.append(f"    for key, value in data.items():")
    lines.append(f"        if isinstance(value, str):")
    lines.append(f'            result[key] = value.strip()')
    lines.append(f"        elif isinstance(value, (int, float)):")
    lines.append(f"            result[key] = value")
    lines.append(f"        else:")
    lines.append(f"            result[key] = str(value)")

    # Reference imported modules sometimes
    if imports and random.random() > 0.5:
        imp = random.choice(imports)
        mod_name = imp.split(".")[-1] if "." in imp else imp
        lines.append(f"    # Uses {mod_name} for processing")

    lines.append(f"    return result")
    lines.append("")
    return "\n".join(lines)


def _generate_class_body(class_name: str, methods: List[str]) -> str:
    """Generate a realistic-looking class body."""
    lines = [f"class {class_name}:"]
    lines.append(f'    """Manages {class_name.replace("_", " ")} operations."""')
    lines.append("")
    lines.append(f"    def __init__(self, config=None):")
    lines.append(f"        self.config = config or {{}}")
    lines.append(f"        self._initialized = False")
    lines.append("")

    for method in methods[:3]:
        method_name = method.lower().replace(" ", "_")
        lines.append(f"    def {method_name}(self, *args, **kwargs):")
        lines.append(f'        """Execute {method_name}."""')
        lines.append(f"        if not self._initialized:")
        lines.append(f"            self._initialized = True")
        lines.append(f"        return self.config.get('{method_name}', None)")
        lines.append("")

    return "\n".join(lines)


def _generate_python_file(spec: FileSpec) -> str:
    """Generate full Python file content from a FileSpec."""
    lines = [f'"""Module: {spec.module_name}']
    lines.append(f"Tier: {spec.tier} | Reference count: {spec.reference_count}")
    lines.append(f'Concepts: {", ".join(spec.concepts)}')
    lines.append(f'"""')
    lines.append("")

    # Imports
    if spec.imports:
        for imp in spec.imports:
            lines.append(f"# import {imp}")
        lines.append("")

    # Constants
    lines.append(f'MODULE_NAME = "{spec.module_name}"')
    lines.append(f'MODULE_VERSION = "1.0.0"')
    lines.append("")

    # Functions
    for func in spec.functions:
        lines.append(_generate_function_body(func, spec.imports))
        lines.append("")

    # Classes
    for cls in spec.classes:
        methods = [_random_identifier("method") for _ in range(random.randint(2, 4))]
        lines.append(_generate_class_body(cls, methods))
        lines.append("")

    return "\n".join(lines)


class DatasetGenerator:
    """Generates synthetic Python codebases with Zipf-distributed file references."""

    SIZES = {
        "small": {"file_count": 50, "lines_per_file": (50, 200)},
        "medium": {"file_count": 200, "lines_per_file": (80, 400)},
    }

    def __init__(self, seed: int = 42):
        self.seed = seed
        random.seed(seed)

    def generate(self, size: str, output_dir: str) -> Dict:
        """Generate a synthetic codebase and return metadata with ground truth.

        Args:
            size: 'small' or 'medium'
            output_dir: Directory to write generated files

        Returns:
            Dictionary with file specs, queries, and ground truth
        """
        if size not in self.SIZES:
            raise ValueError(f"Unknown size: {size}. Use: {list(self.SIZES.keys())}")

        config = self.SIZES[size]
        file_count = config["file_count"]

        # Create output directories
        code_dir = os.path.join(output_dir, "codebase")
        os.makedirs(code_dir, exist_ok=True)

        # Step 1: Assign tiers with Zipf distribution
        file_specs = self._create_file_specs(file_count)

        # Step 2: Generate cross-references (imports between files)
        self._add_cross_references(file_specs)

        # Step 3: Generate actual Python files
        for spec in file_specs:
            file_path = os.path.join(code_dir, spec.path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            content = _generate_python_file(spec)
            with open(file_path, "w") as f:
                f.write(content)

        # Step 4: Generate queries with ground truth
        queries = self._generate_queries(file_specs)

        # Step 5: Save metadata
        metadata = {
            "size": size,
            "file_count": len(file_specs),
            "seed": self.seed,
            "tier_distribution": {
                "head": sum(1 for f in file_specs if f.tier == "head"),
                "torso": sum(1 for f in file_specs if f.tier == "torso"),
                "tail": sum(1 for f in file_specs if f.tier == "tail"),
            },
            "files": [asdict(spec) for spec in file_specs],
            "queries": [asdict(q) for q in queries],
        }

        meta_path = os.path.join(output_dir, "metadata.json")
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)

        return metadata

    def _create_file_specs(self, file_count: int) -> List[FileSpec]:
        """Create file specifications with Zipf-distributed reference counts."""
        specs = []
        weights = _zipf_weights(file_count, s=1.2)

        # Assign tiers: top 20% = head, next 30% = torso, bottom 50% = tail
        head_cutoff = int(file_count * 0.2)
        torso_cutoff = int(file_count * 0.5)

        # Distribute across domains
        all_domains = list(DOMAINS.keys())
        legacy_domain_keys = list(LEGACY_DOMAINS.keys())

        for i in range(file_count):
            if i < head_cutoff:
                tier = "head"
                domain_key = all_domains[i % len(all_domains)]
                domain = DOMAINS[domain_key]
            elif i < torso_cutoff:
                tier = "torso"
                domain_key = all_domains[i % len(all_domains)]
                domain = DOMAINS[domain_key]
            else:
                tier = "tail"
                # Tail files use legacy/edge-case domains more often
                if random.random() < 0.4 and legacy_domain_keys:
                    domain_key = random.choice(legacy_domain_keys)
                    domain = LEGACY_DOMAINS[domain_key]
                else:
                    domain_key = random.choice(all_domains)
                    domain = DOMAINS[domain_key]

            ref_count = max(1, int(weights[i] * file_count * 10))
            module_name = f"{domain_key}_{_random_identifier('mod', 4)}"

            # Select functions and classes from domain
            num_funcs = random.randint(2, 5) if tier == "head" else random.randint(1, 3)
            num_classes = random.randint(1, 2) if tier == "head" else random.randint(0, 1)

            funcs = random.sample(domain["functions"], min(num_funcs, len(domain["functions"])))
            # Make function names unique by adding suffix
            funcs = [f"{fn}_{_random_identifier('', 3)}" if random.random() > 0.3 else fn for fn in funcs]

            classes = random.sample(domain["classes"], min(num_classes, len(domain["classes"])))

            concepts = random.sample(domain["concepts"], min(3, len(domain["concepts"])))

            spec = FileSpec(
                path=f"{domain_key}/{module_name}.py",
                module_name=module_name,
                tier=tier,
                reference_count=ref_count,
                functions=funcs,
                classes=classes,
                concepts=concepts,
            )
            specs.append(spec)

        return specs

    def _add_cross_references(self, specs: List[FileSpec]) -> None:
        """Add import references between files based on Zipf popularity."""
        for spec in specs:
            # Number of imports proportional to tier
            if spec.tier == "head":
                num_imports = random.randint(2, 5)
            elif spec.tier == "torso":
                num_imports = random.randint(1, 3)
            else:
                num_imports = random.randint(0, 2)

            candidates = [s for s in specs if s.module_name != spec.module_name]
            if candidates and num_imports > 0:
                # Head files are imported more often (weighted sampling)
                weights = [c.reference_count for c in candidates]
                total = sum(weights)
                probs = [w / total for w in weights]

                chosen = set()
                for _ in range(min(num_imports, len(candidates))):
                    idx = random.choices(range(len(candidates)), weights=probs, k=1)[0]
                    chosen.add(candidates[idx].module_name)

                spec.imports = list(chosen)

    def _generate_queries(self, specs: List[FileSpec]) -> List[Query]:
        """Generate test queries with ground truth for each trigger type."""
        queries = []
        query_id = 0

        # 1. EXPLICIT_SYMBOL queries - ask about specific function/class names
        for spec in specs:
            if spec.functions:
                func = random.choice(spec.functions)
                base_func = func.split("_")[0] + "_" + func.split("_")[1] if "_" in func else func
                queries.append(Query(
                    id=f"q_{query_id:04d}",
                    text=f"Find the function {func} and show its implementation",
                    trigger_type="EXPLICIT_SYMBOL",
                    relevant_files=[spec.path],
                    relevant_symbols=[func],
                ))
                query_id += 1

            if spec.classes:
                cls = random.choice(spec.classes)
                queries.append(Query(
                    id=f"q_{query_id:04d}",
                    text=f"Show the class {cls} definition",
                    trigger_type="EXPLICIT_SYMBOL",
                    relevant_files=[spec.path],
                    relevant_symbols=[cls],
                ))
                query_id += 1

        # 2. SEMANTIC_CONCEPT queries - ask about concepts
        concept_to_files: Dict[str, List[str]] = {}
        for spec in specs:
            for concept in spec.concepts:
                concept_to_files.setdefault(concept, []).append(spec.path)

        for concept, files in concept_to_files.items():
            queries.append(Query(
                id=f"q_{query_id:04d}",
                text=f"Find all code related to {concept}",
                trigger_type="SEMANTIC_CONCEPT",
                relevant_files=files,
                relevant_symbols=[],
            ))
            query_id += 1

        # 3. TEMPORAL_HISTORY queries - simulated history references
        for spec in random.sample(specs, min(10, len(specs))):
            queries.append(Query(
                id=f"q_{query_id:04d}",
                text=f"Show the module we discussed previously about {spec.concepts[0] if spec.concepts else spec.module_name}",
                trigger_type="TEMPORAL_HISTORY",
                relevant_files=[spec.path],
                relevant_symbols=[],
            ))
            query_id += 1

        # 4. IMPLICIT_CONTEXT queries - requires inference
        for spec in random.sample(specs, min(10, len(specs))):
            if spec.imports:
                imported_specs = [s for s in specs if s.module_name in spec.imports]
                all_relevant = [spec.path] + [s.path for s in imported_specs]
                queries.append(Query(
                    id=f"q_{query_id:04d}",
                    text=f"What modules are needed to fully understand {spec.module_name}?",
                    trigger_type="IMPLICIT_CONTEXT",
                    relevant_files=all_relevant,
                    relevant_symbols=[],
                ))
                query_id += 1

        return queries
