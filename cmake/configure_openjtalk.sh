#!/bin/bash
set -e

echo "Configuring OpenJTalk in directory: $1"
cd "$1/src" || { echo "Failed to cd to $1/src"; exit 1; }

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

# On Linux, iconv is part of glibc, so we don't need -liconv
# Set LDFLAGS to help the build system understand this
export LDFLAGS="-Wl,--as-needed"
export LIBS=""

./configure --prefix="$2" --with-hts-engine-header-path="$3/include" --with-hts-engine-library-path="$3/lib" --with-charset=UTF-8 --without-libiconv-prefix