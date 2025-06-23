#!/bin/bash
set -e

cd "$1/src"

if [ ! -f configure ]; then
    touch ChangeLog AUTHORS NEWS README
    autoreconf -fiv || (aclocal && automake --add-missing && autoconf)
fi

./configure --prefix="$2" --enable-static --disable-shared