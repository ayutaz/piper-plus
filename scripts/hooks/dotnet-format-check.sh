#!/usr/bin/env bash
# pre-commit hook wrapper for `dotnet format --verify-no-changes`.
#
# Skips gracefully when the .NET SDK or the version pinned by global.json
# is absent locally. CI (.github/workflows/csharp-ci.yml) still gates the
# merge, so a missing local install does not let drift through to main.
set -euo pipefail

if ! command -v dotnet >/dev/null 2>&1; then
    echo "[skip] dotnet not on PATH (install .NET 10 SDK to enable this hook)"
    exit 0
fi

# global.json pins the SDK major version. If it is missing locally, the
# `dotnet` invocation would fail with "A compatible .NET SDK was not found".
# Detect that case before running so the hook output is informative.
if ! dotnet --list-sdks 2>/dev/null | awk '{print $1}' | grep -q '^10\.'; then
    echo "[skip] .NET 10 SDK not installed (global.json requires it; CI still gates)"
    echo "       install: https://dotnet.microsoft.com/download/dotnet/10.0"
    exit 0
fi

exec dotnet format src/csharp/PiperPlus.sln --verify-no-changes --no-restore
