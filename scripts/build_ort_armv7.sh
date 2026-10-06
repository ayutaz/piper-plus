#!/usr/bin/env bash
# Cross-compile the same upstream ORT release used by the other native packages.
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
sdk=${1:?Usage: build_ort_armv7.sh SDK_DIRECTORY}
mkdir -p "$sdk"
sdk=$(cd "$sdk" && pwd)
version=$(sed -n 's/.*set(ONNXRUNTIME_VERSION "\([0-9.]*\)").*/\1/p' "$root/cmake/OnnxRuntime.cmake")
# This commit is the peeled upstream v1.20.0 tag, not a moving branch.
test "$version" = 1.20.0
commit=c4fb724e810bb496165b9015c77f402727392933
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git -C "$work" init
git -C "$work" remote add origin https://github.com/microsoft/onnxruntime.git
git -C "$work" fetch --depth 1 origin "$commit"
git -C "$work" checkout --detach FETCH_HEAD
test "$(git -C "$work" rev-parse HEAD)" = "$commit"
test "$(tr -d '\r\n' < "$work/VERSION_NUMBER")" = "$version"
git -C "$work" submodule update --init --recursive --depth 1
# GitLab regenerated the archive referenced by this older ORT release, so its
# archive digest no longer matches. Fetch exactly the dependency's Git commit
# instead of accepting different bytes or selecting a newer Eigen version.
eigen_commit=$(sed -n 's|^eigen;https://gitlab.com/libeigen/eigen/-/archive/\([0-9a-f]*\)/.*|\1|p' "$work/cmake/deps.txt")
[[ "$eigen_commit" =~ ^[0-9a-f]{40}$ ]]
mkdir "$work/eigen"
git -C "$work/eigen" init
git -C "$work/eigen" remote add origin https://gitlab.com/libeigen/eigen.git
git -C "$work/eigen" fetch --depth 1 origin "$eigen_commit"
git -C "$work/eigen" checkout --detach FETCH_HEAD
test "$(git -C "$work/eigen" rev-parse HEAD)" = "$eigen_commit"
root_args=()
if [ "$(id -u)" = 0 ]; then
  root_args+=(--allow_running_as_root)
fi
"$work/build.sh" --config Release --update --build --arm --build_shared_lib \
  --skip_tests --skip_submodule_sync --parallel 2 --cmake_generator Ninja \
  --compile_no_warning_as_error "${root_args[@]}" \
  --use_preinstalled_eigen --eigen_path "$work/eigen" \
  --cmake_extra_defines "CMAKE_TOOLCHAIN_FILE=$root/cmake/linux-armv7-toolchain.cmake" \
  onnxruntime_BUILD_UNIT_TESTS=OFF
mkdir -p "$sdk/include" "$sdk/lib"
cp -a "$work"/build/Linux/Release/libonnxruntime*.so* "$sdk/lib/"
find "$work/include/onnxruntime/core/session" -maxdepth 1 -name '*.h' \
  -exec cp '{}' "$sdk/include/" \;
cp "$work/LICENSE" "$work/ThirdPartyNotices.txt" "$sdk/"
test -s "$sdk/lib/libonnxruntime.so"
test -s "$sdk/include/onnxruntime_cxx_api.h"
arm-linux-gnueabihf-readelf -h "$sdk/lib/libonnxruntime.so" | grep 'Class:.*ELF32'
arm-linux-gnueabihf-readelf -h "$sdk/lib/libonnxruntime.so" | grep 'Machine:.*ARM'
