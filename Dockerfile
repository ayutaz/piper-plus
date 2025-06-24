# ========== BASE STAGE ==========
FROM debian:bullseye AS base
ARG TARGETARCH
ARG TARGETVARIANT

ENV LANG=C.UTF-8
ENV DEBIAN_FRONTEND=noninteractive

# Retryの設定
RUN echo 'Acquire::Retries "3";' > /etc/apt/apt.conf.d/80-retries

# ========== DEPENDENCIES STAGE ==========
FROM base AS dependencies

# 基本ツールのインストール（レイヤーキャッシュ最適化）
RUN apt-get update && \
    apt-get install --yes --no-install-recommends \
        ca-certificates curl gnupg lsb-release && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# メインパッケージのインストール（エラー処理強化）
RUN for i in 1 2 3; do \
        apt-get update && \
        apt-get install --yes --no-install-recommends \
            build-essential cmake git pkg-config libicu-dev libespeak-ng-dev \
            make ninja-build python3 ccache \
            autoconf automake libtool libc6-dev && \
        apt-get clean && \
        rm -rf /var/lib/apt/lists/* && break || { \
            echo "Package install failed (attempt $i)"; \
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
FROM dependencies AS build

WORKDIR /build

# ccacheの設定（ARM64ビルド用に増量）
ENV CCACHE_DIR=/tmp/ccache
ENV CCACHE_MAXSIZE=2G
ENV CCACHE_COMPRESS=1
RUN mkdir -p /tmp/ccache

# CMakeLists.txtと設定ファイルを先にコピー（依存関係キャッシュ最適化）
COPY CMakeLists.txt VERSION ./
COPY cmake/ cmake/
COPY src/cpp/ src/cpp/

# ツールチェインファイルを作成（COPYの後に作成してオーバーライドを防ぐ）
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        echo 'set(CMAKE_SYSTEM_NAME Linux)' > cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_SYSTEM_PROCESSOR aarch64)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH /usr/aarch64-linux-gnu)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)' >> cmake/linux-aarch64.cmake && \
        echo 'set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)' >> cmake/linux-aarch64.cmake; \
    fi

# 残りのソースファイルをコピー
COPY . .

# Ensure scripts are executable
RUN chmod +x cmake/*.sh

# Configure step (deps resolution)
# Increase ccache size for OpenJTalk builds
RUN ccache -M 2G

RUN if [ "$TARGETARCH" = "amd64" ]; then \
        cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
              -DCMAKE_BUILD_TYPE=Release \
              -DCMAKE_C_COMPILER_LAUNCHER=ccache \
              -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
              -DCMAKE_BUILD_PARALLEL_LEVEL=2 \
              -DUSE_OPENJTALK=ON \
              -GNinja; \
    elif [ "$TARGETARCH" = "arm64" ]; then \
        cmake -Bbuild -DCMAKE_INSTALL_PREFIX=install \
            -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_TOOLCHAIN_FILE=cmake/linux-aarch64.cmake \
            -DCMAKE_C_COMPILER_LAUNCHER=ccache \
            -DCMAKE_CXX_COMPILER_LAUNCHER=ccache \
            -DCMAKE_BUILD_PARALLEL_LEVEL=1 \
            -DUSE_OPENJTALK=ON \
            -GNinja; \
    else \
        echo "Unsupported architecture: $TARGETARCH" && exit 1; \
    fi

# CMake will handle dictionary download via ExternalProject_Add
# No pre-download needed

# Build step (with architecture-specific optimizations)
RUN if [ "$TARGETARCH" = "arm64" ]; then \
        # ARM64 builds: single thread, timeout handling, retry on failure \
        echo "Starting ARM64 build with single thread..." && \
        timeout 3600 cmake --build build --config Release --parallel 1 || \
        (echo "Build failed, retrying..." && \
         timeout 1800 cmake --build build --config Release --parallel 1); \
    else \
        # x86_64 builds: standard parallel build \
        echo "Starting AMD64 build with 2 parallel threads..." && \
        cmake --build build --config Release --parallel 2 || \
        (echo "Build failed with parallel build, retrying with single thread..." && \
         cmake --build build --config Release --parallel 1); \
    fi

# Install step  
RUN cmake --install build

# テスト実行（amd64のみ）
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        ./build/piper --help && \
        echo "Testing OpenJTalk support..." && \
        ./build/piper --help 2>&1 | grep -q "openjtalk" && echo "OpenJTalk support confirmed" || echo "OpenJTalk support not found"; \
    fi

# アーカイブの作成（辞書ファイルも含める）
WORKDIR /dist
RUN mkdir -p piper && \
    cp -dR /build/install/* ./piper/ && \
    # Copy dictionary if it exists
    if [ -d /build/build/naist-jdic ]; then \
        mkdir -p ./piper/share/piper && \
        cp -r /build/build/naist-jdic ./piper/share/piper/openjtalk-dict; \
    fi && \
    tar -czf "piper_${TARGETARCH}.tar.gz" piper/

FROM scratch
COPY --from=build /dist/piper_*.tar.gz ./
