# [expert-research-v2] CTX Plugin Install Validation Strategy
**Date**: 2026-05-02  **Skill**: expert-research-v2

## Original Question
How to validate CTX plugin installation end-to-end in a clean/isolated environment?
Setup hook: (1) creates Python venv, (2) pip-installs ctx-retriever from PyPI, (3) runs ctx-install.

## Web Facts
[FACT-1] `--plugin-dir` flag loads plugin locally without marketplace install. Same-name local plugin overrides installed. (source: https://code.claude.com/docs/en/plugins)
[FACT-2] `/reload-plugins` reloads hooks/skills without restarting Claude Code. (source: https://code.claude.com/docs/en/plugins)
[FACT-3] DevContainer (official Anthropic): Node.js 20 base, default-deny firewall, full filesystem isolation. (source: https://claudelab.net/en/articles/claude-code/claude-code-devcontainer-secure-isolated-environment)
[FACT-4] Plugin hooks live in `hooks/hooks.json` at plugin root — separate from settings.json format. (source: https://code.claude.com/docs/en/plugins)
[FACT-5] Hooks loaded at session start; changes require /reload-plugins or restart. (source: https://code.claude.com/docs/en/plugins)

## Synthesis

### Strategy 1 — Temp HOME (5 min, automated)
```bash
export TEST_HOME=/tmp/ctx-validate-$$
mkdir -p $TEST_HOME/.claude
HOME=$TEST_HOME python3 -m pip install --target $TEST_HOME/pkgs ctx-retriever==0.3.9 -q
HOME=$TEST_HOME PYTHONPATH=$TEST_HOME/pkgs python3 -m ctx_retriever.cli.install
ls $TEST_HOME/.claude/hooks/
cat $TEST_HOME/.claude/settings.json | python3 -m json.tool | grep -A3 '"hooks"'
rm -rf $TEST_HOME
```

### Strategy 2 — Docker DevContainer (full, ~15 min)
```bash
docker run -it --rm -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY cc-test bash
# /plugin marketplace add jaytoone/CTX && /plugin install ctx
```

### Strategy 3 — --plugin-dir (local plugin scaffold test)
```bash
claude --plugin-dir ./plugin/
```

## Verification Checklist
- 5 hook files present in ~/.claude/hooks/
- settings.json has CTX hooks (grep bm25-memory → count=1, no duplicates)
- bm25-memory.py fires on echo '{"prompt":"test"}' input
- last-injection.json written after smoke test

## Sources
- https://code.claude.com/docs/en/plugins
- https://claudelab.net/en/articles/claude-code/claude-code-devcontainer-secure-isolated-environment
