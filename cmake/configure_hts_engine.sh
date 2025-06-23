#!/bin/bash
set -e

echo "Configuring HTS Engine in directory: $1"
cd "$1/src" || { echo "Failed to cd to $1/src"; exit 1; }

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

# Platform-specific configuration
if [[ "$OSTYPE" == "darwin"* ]]; then
    # Ensure we're building for the correct architecture on macOS
    if [[ $(uname -m) == "arm64" ]]; then
        export CFLAGS="-arch arm64 -mmacosx-version-min=11.0"
        export CXXFLAGS="-arch arm64 -mmacosx-version-min=11.0"
    else
        export CFLAGS="-arch x86_64 -mmacosx-version-min=10.15"
        export CXXFLAGS="-arch x86_64 -mmacosx-version-min=10.15"
    fi
fi

./configure --prefix="$2" --enable-static --disable-shared