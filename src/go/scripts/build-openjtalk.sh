#!/usr/bin/env bash
# Build OpenJTalk as a static library from the pyopenjtalk-plus sdist, for
# the `openjtalk` build tag (phonemize/openjtalk_engine.go).
#
# Usage: build-openjtalk.sh <work-dir> <install-prefix> <dictionary-dir>
#
# Used by src/go/docker/Dockerfile and by the `openjtalk` job of
# .github/workflows/go-ci.yml, so the binary in the image and the code the
# CI tests are built the same way. Then build Go with:
#   CGO_ENABLED=1
#   CGO_CFLAGS="-I<install-prefix>/include/openjtalk"
#   CGO_LDFLAGS="-L<install-prefix>/lib -lopenjtalk -lstdc++ -lm"
#   go build -tags openjtalk ...
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <work-dir> <install-prefix> <dictionary-dir>" >&2
  exit 2
fi
work=$1
prefix=$2
dict=$3

# pyopenjtalk-plus contains the OpenJTalk source and the MeCab dictionary.
url=https://files.pythonhosted.org/packages/82/4e/1e2c165b04dd250dbcb1c270df8517681eed5c20b755c72bec2b42853851/pyopenjtalk_plus-0.4.1.post7.tar.gz
sha256=555fdf86310d6d72f4a37e92beb251cdc2114aafc133d4c77b136a07a4b17119

mkdir -p "$work/src"
wget -q "$url" -O "$work/pyopenjtalk-plus.tar.gz"
echo "$sha256  $work/pyopenjtalk-plus.tar.gz" | sha256sum -c -
tar xzf "$work/pyopenjtalk-plus.tar.gz" -C "$work/src" --strip-components=1
rm "$work/pyopenjtalk-plus.tar.gz"

# Patch CMakeLists.txt (equivalent to cmake/patch_r9y9_openjtalk.cmake):
#   1. Enable install() on all platforms (not just non-MSVC)
#   2. Add C++17 compatibility for MeCab's std::binary_function
cmakelists="$work/src/lib/open_jtalk/src/CMakeLists.txt"
sed -i 's/if(NOT MSVC)/if(1)/' "$cmakelists"
sed -i '/^project(openjtalk)/a\\nadd_compile_definitions(_GLIBCXX_USE_DEPRECATED=1)' "$cmakelists"

cmake -S "$work/src/lib/open_jtalk/src" -B "$work/build" \
  -DCMAKE_INSTALL_PREFIX="$prefix" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=OFF \
  -DCHARSET=utf8 \
  -DCMAKE_POSITION_INDEPENDENT_CODE=ON
cmake --build "$work/build" --parallel "$(nproc)"
cmake --install "$work/build"

mkdir -p "$dict"
cp -r "$work/src/pyopenjtalk/dictionary/"* "$dict/"
