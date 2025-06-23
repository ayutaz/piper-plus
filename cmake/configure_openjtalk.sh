#!/bin/bash
set -e

echo "Configuring OpenJTalk in directory: $1"
cd "$1/src" || { echo "Failed to cd to $1/src"; exit 1; }

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

./configure --prefix="$2" --with-hts-engine-header-dir="$3/include" --with-hts-engine-library-dir="$3/lib" --with-hts-engine-library-name=HTSEngine --with-charset=UTF-8 --enable-static --disable-shared