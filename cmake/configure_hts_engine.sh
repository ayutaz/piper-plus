#!/bin/bash
set -e

echo "Configuring HTS Engine in directory: $1"
cd "$1/src" || { echo "Failed to cd to $1/src"; exit 1; }

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

./configure --prefix="$2" --enable-static --disable-shared