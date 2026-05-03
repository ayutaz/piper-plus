# ========== BASE STAGE ==========
FROM debian:trixie AS base
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

# Retryの設定
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries

# ========== DEPENDENCIES STAGE ==========
FROM base AS dependencies

# Debug: Show build arguments
RUN echo "Build arguments - TARGETARCH: ${TARGETARCH}, TARGETVARIANT: ${TARGETVARIANT}"

# 基本ツールのインストール（レイヤーキャッシュ最適化）
# ARM64エミュレーション環境でのlibc-binエラー対策
RUN rm -f /var/cache/ldconfig/aux-cache || true && \
    # libc-binのpost-installスクリプトエラーを回避
    mkdir -p /etc/apt/apt.conf.d && \
    echo 'DPkg::Post-Invoke { "rm -f /var/cache/ldconfig/aux-cache || true"; };' > /etc/apt/apt.conf.d/00apt-post-invoke && \
    # dpkgオプションでトリガーを遅延
    echo 'APT::Immediate-Configure "false";' > /etc/apt/apt.conf.d/00postpone && \
    apt-get update && \
    # 最初にlibc-binを単独でインストール（エラーを無視）
    apt-get install --yes --no-install-recommends libc-bin || true && \
    # 再設定を試行
    dpkg --configure -a || true && \
    # 通常のパッケージインストール
    apt-get install --yes --no-install-recommends \
        ca-certificates curl gnupg lsb-release && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# メインパッケージのインストール（エラー処理強化）
RUN for i in 1 2 3; do \
        apt-get update && \
        # ldconfigのキャッシュをクリア
        rm -f /var/cache/ldconfig/aux-cache && \
        apt-get install --yes --no-install-recommends \
            build-essential cmake git pkg-config libicu-dev libespeak-ng-dev \
            make ninja-build python3 ccache \
            libmecab-dev mecab mecab-ipadic-utf8 \
            autoconf automake libtool \
            flex bison strace && \
        apt-get clean && \
        rm -rf /var/lib/apt/lists/* && break || { \
            echo "Package install failed (attempt $i)"; \
            # エラー時にlibc-binの設定ファイルを削除
            rm -f /var/lib/dpkg/info/libc-bin.* || true; \
            sleep 5; \
        }; \
    done

# クロスコンパイルツール（条件付きインストール）
RUN HOST_ARCH=$(dpkg --print-architecture); \
    if [ "$HOST_ARCH" = "amd64" ] && [ "$TARGETARCH" = "arm64" ]; then \
        apt-get update && \
        apt-get install --yes --no-install-recommends \
            gcc-aarch64-linux-gnu g++-aarch64-linux-gnu binutils-aarch64-linux-gnu && \
        ln -s /usr/bin/ccache /usr/local/bin/aarch64-linux-gnu-gcc && \
        ln -s /usr/bin/ccache /usr/local/bin/aarch64-linux-gnu-g++ && \
        apt-get clean && rm -rf /var/lib/apt/lists/*; \
    fi

# ========== BUILD STAGE ==========
FROM dependencies AS builder

WORKDIR /build

# ccacheの設定（ARM64ビルド用に増量）
# TIP: For faster rebuilds with BuildKit, use cache mounts:
# RUN --mount=type=cache,target=/tmp/ccache cmake --build build ...
ENV CCACHE_DIR=/tmp/ccache
ENV CCACHE_MAXSIZE=2G
ENV CCACHE_COMPRESS=1
RUN mkdir -p /tmp/ccache

# ツールチェインファイルを作成（クロスコンパイル時のみ）
RUN mkdir -p cmake && \
    HOST_ARCH=$(dpkg --print-architecture) && \
    echo "Host architecture: $HOST_ARCH, Target architecture: $TARGETARCH" && \
    if [ "$TARGETARCH" = "arm64" ] && [ "$HOST_ARCH" = "amd64" ]; then \
        echo "Creating ARM64 cross-compilation toolchain file..." && \
        echo 'set(CMAKE_SYSTEM_NAME Linux)' > cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_SYSTEM_PROCESSOR aarch64)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH /usr/aarch64-linux-gnu)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)' >> cmake/linux-aarch64.cmake; \
    else \
        echo "Native build detected, no toolchain file needed"; \
    fi

# CMakeLists.txtと設定ファイルを先にコピー（依存関係キャッシュ最適化）
COPY CMakeLists.txt VERSION ./
COPY cmake/ cmake/
COPY src/cpp/ src/cpp/

# Configure step (deps resolution)
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
              -DCMAKE_BUILD_TYPE=Release \
              -DCMAKE_C_COMPILER_LAUNCHER=ccache \
              -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
              -DCMAKE_BUILD_PARALLEL_LEVEL=2 \
              -GNinja; \
    elif [ "$TARGETARCH" = "arm" ]; then \
        echo "Building for ARMv7 (arm)..." && \
        cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
              -DCMAKE_BUILD_TYPE=Release \
              -DCMAKE_C_COMPILER_LAUNCHER=ccache \
              -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
              -DCMAKE_BUILD_PARALLEL_LEVEL=1 \
              -DCMAKE_VERBOSE_MAKEFILE=ON \
              -GNinja; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        HOST_ARCH=$(dpkg --print-architecture) && \
        echo "Host architecture: $HOST_ARCH, Target: $TARGETARCH" && \
        echo "CMAKE_SYSTEM_PROCESSOR will be: $(uname -m)" && \
        if [ "$HOST_ARCH" = "amd64" ]; then \
            echo "Cross-compiling for ARM64..." && \
            cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
                -DCMAKE_BUILD_TYPE=Release \
                -DCMAKE_TOOLCHAIN_FILE=cmake/linux-aarch64.cmake \
                -DCMAKE_C_COMPILER_LAUNCHER=ccache \
                -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
                -DCMAKE_BUILD_PARALLEL_LEVEL=1 \
                -DCMAKE_VERBOSE_MAKEFILE=ON \
                -GNinja; \
        else \
            echo "Native ARM64 build..." && \
            echo "System processor: $(uname -m)" && \
            cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
                -DCMAKE_BUILD_TYPE=Release \
                -DCMAKE_C_COMPILER_LAUNCHER=ccache \
                -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
                -DCMAKE_BUILD_PARALLEL_LEVEL=1 \
                -DCMAKE_VERBOSE_MAKEFILE=ON \
                -GNinja; \
        fi; \
    else \
        echo "Unsupported architecture: $TARGETARCH" && exit 1; \
    fi

# 残りのソースファイルをコピー
COPY . .

# Build step (with architecture-specific optimizations)
RUN if [ "$TARGETARCH" = "arm" ]; then \
        # ARMv7 builds: Use more conservative optimization to avoid build failures \
        echo "Starting ARMv7 build..." && \
        export CFLAGS="-O1 -march=armv7-a -mfpu=neon -mfloat-abi=hard" && \
        export CXXFLAGS="-O1 -march=armv7-a -mfpu=neon -mfloat-abi=hard" && \
        export LDFLAGS="-Wl,--no-undefined" && \
        timeout 2400 cmake --build build --config Release --parallel 1 --verbose || \
        (echo "Build failed, retrying..." && cmake --build build --config Release --parallel 1 --verbose); \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        # ARM64 builds: optimized with NEON support \
        echo "Starting optimized ARM64 build..." && \
        export CFLAGS="-O2 -march=armv8-a+simd -mtune=cortex-a72 -fomit-frame-pointer" && \
        export CXXFLAGS="-O2 -march=armv8-a+simd -mtune=cortex-a72 -fomit-frame-pointer" && \
        timeout 2400 cmake --build build --config Release --parallel 1 --verbose || \
        (echo "Build failed, retrying..." && cmake --build build --config Release --parallel 1 --verbose); \
    else \
        # x86_64 builds: standard parallel build \
        echo "Starting AMD64 build with 2 parallel threads..." && \
        cmake --build build --config Release --parallel 2 --verbose || \
        (echo "Build failed with parallel build, retrying with single thread..." && \
         cmake --build build --config Release --parallel 1 --verbose); \
    fi

# Install step  
RUN cmake --install build

# Check piper-phonemize build results
RUN echo "=== Checking piper-phonemize build ===" && \
    find /build/build -name "*onnxruntime*" -type f | head -20 && \
    echo "=== Checking libraries in build directory ===" && \
    find /build/build -name "*.so*" -type f | grep -E "(onnx|espeak|piper)" | head -20 && \
    echo "=== Checking ONNX Runtime in piper-phonemize ===" && \
    find /build/build/p/src/piper_phonemize_external-build -name "*onnx*" 2>/dev/null | head -20 || echo "No ONNX files in piper-phonemize build" && \
    echo "=== Checking downloaded files ===" && \
    find /build/build -path "*/download/*" -name "*onnx*" 2>/dev/null | head -10 || echo "No downloaded ONNX files"

# Set up library paths for runtime and create symlinks
RUN echo "/build/install/lib" > /etc/ld.so.conf.d/piper.conf && \
    rm -f /var/cache/ldconfig/aux-cache || true && \
    ldconfig || true && \
    if [ -d /build/install/lib ]; then \
        cd /build/install/lib && \
        ONNX_SO=$(ls libonnxruntime.so.1.* 2>/dev/null | head -1) && \
        if [ -n "$ONNX_SO" ]; then \
            ln -sf "$ONNX_SO" libonnxruntime.so.1 && \
            ln -sf libonnxruntime.so.1 libonnxruntime.so; \
        fi \
    fi

# Strip binaries for smaller size on ARM64
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo "Stripping binaries for size optimization..." && \
        HOST_ARCH=$(dpkg --print-architecture) && \
        if [ "$HOST_ARCH" = "amd64" ]; then \
            find install/bin -type f -executable -exec aarch64-linux-gnu-strip {} \; 2>/dev/null || true; \
        else \
            find install/bin -type f -executable -exec strip {} \; 2>/dev/null || true; \
        fi; \
    fi

# ONNX Runtime確認
RUN echo "=== Checking ONNX Runtime ===" && \
    find /build -name "*onnxruntime*" -type f | head -20 && \
    echo "=== Checking piper binary dependencies ===" && \
    ldd /build/install/bin/piper | grep -i onnx || echo "ONNX Runtime not found in ldd output" && \
    echo "=== Checking install directory ===" && \
    find /build/install -name "*onnx*" -type f | head -10

# テスト実行（amd64のみ）
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        ./build/piper --help; \
    fi

# アーカイブの作成
WORKDIR /dist
RUN mkdir -p piper && \
    cp -dR /build/install/* ./piper/ && \
    echo "TARGETARCH=${TARGETARCH}, TARGETVARIANT=${TARGETVARIANT}" && \
    if [ "$TARGETARCH" = "arm" ]; then \
        if [ "$TARGETVARIANT" = "v7" ] || [ "$TARGETVARIANT" = "7" ]; then \
            echo "Creating ARMv7 tarball..." && \
            tar -czf "piper-linux-armv7.tar.gz" piper/; \
        elif [ -z "$TARGETVARIANT" ]; then \
            echo "ARM architecture with no variant specified, defaulting to ARMv7..." && \
            tar -czf "piper-linux-armv7.tar.gz" piper/; \
        else \
            echo "Unknown ARM variant: $TARGETVARIANT" && \
            tar -czf "piper-linux-arm-${TARGETVARIANT}.tar.gz" piper/; \
        fi \
    elif [ "$TARGETARCH" = "arm64" ] || [ "$TARGETARCH" = "aarch64" ]; then \
        echo "Creating ARM64 tarball..." && \
        tar -czf "piper-linux-arm64.tar.gz" piper/; \
    else \
        echo "Creating generic tarball for arch: $TARGETARCH" && \
        tar -czf "piper_${TARGETARCH}.tar.gz" piper/; \
    fi

# Add an alias for backward compatibility
FROM builder AS build

FROM scratch
COPY --from=build /dist/piper*.tar.gz ./
