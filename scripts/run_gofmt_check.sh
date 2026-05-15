#!/usr/bin/env bash
# pre-commit gofmt wrapper.
#
# gofmt -l prints offending file names but exits 0 even when drift exists,
# which is unusable as a pre-commit gate. This wrapper converts the
# "non-empty output" signal into a proper exit code with a human-readable
# error message.
#
# Args: pre-commit passes staged file paths positionally.
set -euo pipefail

if [ "$#" -eq 0 ]; then
    exit 0
fi

out=$(gofmt -l "$@" 2>&1)
if [ -n "$out" ]; then
    echo "Go files need gofmt"
    echo "$out"
    echo ""
    echo "Run 'gofmt -w' on the listed files to fix."
    exit 1
fi
exit 0
