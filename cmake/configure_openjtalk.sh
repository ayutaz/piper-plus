#!/bin/bash
set -e

echo "Configuring OpenJTalk in directory: $1"
cd "$1/src" || { echo "Failed to cd to $1/src"; exit 1; }

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

# Platform-specific configuration
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS: iconv is part of the system
    export LDFLAGS="-liconv"
    export LIBS=""
    # Ensure we're building for the correct architecture
    if [[ $(uname -m) == "arm64" ]]; then
        export CFLAGS="-arch arm64 -mmacosx-version-min=11.0"
        export CXXFLAGS="-arch arm64 -mmacosx-version-min=11.0"
    else
        export CFLAGS="-arch x86_64 -mmacosx-version-min=10.15"
        export CXXFLAGS="-arch x86_64 -mmacosx-version-min=10.15"
    fi
else
    # Linux: iconv is part of glibc, so we don't need -liconv
    export LDFLAGS="-Wl,--as-needed"
    export LIBS=""
fi

./configure --prefix="$2" --with-hts-engine-header-path="$3/include" --with-hts-engine-library-path="$3/lib" --with-charset=UTF-8 --without-libiconv-prefix