#!/usr/bin/env bash
# Publish ctx-retriever to PyPI
# Usage: bash scripts/publish.sh [--test]
set -e

TEST=${1:-""}

echo "Building distribution..."
python3 -m pip install --quiet build twine
python3 -m build

if [ "$TEST" = "--test" ]; then
    echo "Uploading to TestPyPI..."
    python3 -m twine upload --repository testpypi dist/*
    echo "Test install:"
    echo "  pip install --index-url https://test.pypi.org/simple/ ctx-retriever"
else
    echo "Uploading to PyPI..."
    python3 -m twine upload dist/*
    echo "Install with: pip install ctx-retriever"
fi
