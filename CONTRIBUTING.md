# Contributing to CTX

## Setup

```bash
git clone https://github.com/jaytoone/CTX
cd CTX
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -q
```

## Project Layout

```
src/retrieval/     # Retrieval strategies — add new ones here
src/trigger/       # Trigger classifier (TriggerClassifier)
hooks/             # Claude Code hooks
benchmarks/        # Benchmark scripts and results
```

## Adding a New Retrieval Strategy

1. Create `src/retrieval/my_strategy.py` implementing the `BaseRetriever` interface
2. Register it in `src/retrieval/__init__.py`
3. Add a test in `tests/`
4. Run `python run_experiment.py --strategy my_strategy` to benchmark

## Issues and PRs

Open issues at https://github.com/jaytoone/CTX/issues.
PRs welcome — please include benchmark results for retrieval changes.
