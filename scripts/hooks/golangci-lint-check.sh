#!/usr/bin/env bash
# pre-commit hook wrapper for `golangci-lint run`.
#
# The upstream pre-commit-mirrors hook runs from repo root and cannot
# locate the src/go go.mod, so we use this local wrapper that cd's into
# the module. Skips gracefully when the binary is absent locally —
# CI (.github/workflows/go-ci.yml) still gates the merge.
set -euo pipefail

if ! command -v golangci-lint >/dev/null 2>&1; then
    echo "[skip] golangci-lint not on PATH (brew install golangci-lint to enable)"
    exit 0
fi

cd src/go
exec golangci-lint run --timeout=5m ./... ./phonemize/...
