# QA / pre-commit convenience targets (Tier 2-G).
#
# These targets wrap the canonical `pre-commit run` invocations so contributors
# don't have to remember the exact flag combos for each scenario.
#
# Setup (one-time per clone):
#   pip install pre-commit  # or: uvx pre-commit
#   pre-commit install                       # writes .git/hooks/pre-commit
#   pre-commit install --hook-type pre-push  # writes .git/hooks/pre-push (opt-in)
#
# Daily use:
#   make qa            # full repo QA — commit-stage + pre-push-stage hooks
#   make qa-commit     # commit-stage only (fast, ~10s; matches `git commit` gate)
#   make qa-push       # pre-push-stage only (heavy: markdownlint/codespell/etc.)
#   make qa-fix        # auto-apply fixes (run before commit if drift found)
#
# CI runs `pre-commit run --from-ref/--to-ref` on changed files only
# (per .github/workflows/pre-commit.yml). Local `make qa` is the equivalent of
# "full repo, all stages" — heavier than CI but catches latent drift CI skips.

.PHONY: qa qa-commit qa-push qa-fix

# Full QA pass — commit-stage then pre-push-stage hooks. Note: hooks without
# an explicit `stages:` clause run in both invocations; the duplication is
# acceptable given the convenience of a single target. Use qa-commit /
# qa-push for tighter scopes.
qa: qa-commit qa-push

qa-commit:
	pre-commit run --all-files --show-diff-on-failure

qa-push:
	pre-commit run --all-files --hook-stage pre-push --show-diff-on-failure

# Auto-apply fixes (ruff --fix, trailing-whitespace, end-of-file-fixer, etc.).
# Runs commit-stage hooks only; re-run `git add` + `make qa-commit` to verify.
qa-fix:
	pre-commit run --all-files