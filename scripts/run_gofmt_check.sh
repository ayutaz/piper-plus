#!/usr/bin/env bash
# pre-commit gofmt wrapper.
#
# gofmt -l prints offending file names but exits 0 even when drift exists,
# which is unusable as a pre-commit gate. This wrapper converts the
# "non-empty output" signal into a proper exit code with a human-readable
# error message.
#
# Important: gofmt exits with code 2 on syntax/parse errors (not just format
# drift). Under `set -e` the command substitution would abort silently. We
# capture the exit code explicitly so syntax errors are surfaced rather than
# swallowed.
#
# Args: pre-commit passes staged file paths positionally.
set -uo pipefail

if [ "$#" -eq 0 ]; then
    exit 0
fi

out=$(gofmt -l "$@" 2>&1)
rc=$?

if [ "$rc" -ne 0 ]; then
    # Non-zero exit from gofmt (e.g., syntax error). Surface the message
    # and propagate the exit code so reviewers see the real problem.
    echo "gofmt exited with code $rc (likely syntax/parse error)"
    if [ -n "$out" ]; then
        echo "$out"
    fi
    exit "$rc"
fi

if [ -n "$out" ]; then
    echo "Go files need gofmt"
    echo "$out"
    echo ""
    echo "Run 'gofmt -w' on the listed files to fix."
    exit 1
fi
exit 0
