# ============================================================
# Stage 1: Build OpenJTalk static library + Go binary
# Uses Debian-based golang image for glibc compatibility with
# ONNX Runtime. OpenJTalk is built from pyopenjtalk-plus source
# to enable Japanese G2P via CGO bindings.
# ============================================================
FROM golang:1.26 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ cmake make wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download pyopenjtalk-plus (contains OpenJTalk source + MeCab dictionary)
ARG PYOPENJTALK_URL=https://files.pythonhosted.org/packages/82/4e/1e2c165b04dd250dbcb1c270df8517681eed5c20b755c72bec2b42853851/pyopenjtalk_plus-0.4.1.post7.tar.gz
WORKDIR /openjtalk-src
RUN wget -q "${PYOPENJTALK_URL}" -O pyopenjtalk-plus.tar.gz \
    && tar xzf pyopenjtalk-plus.tar.gz --strip-components=1 \
    && rm pyopenjtalk-plus.tar.gz

# Patch CMakeLists.txt (equivalent to cmake/patch_r9y9_openjtalk.cmake):
#   1. Enable install() on all platforms (not just non-MSVC)
#   2. Add C++17 compatibility for MeCab's std::binary_function
RUN sed -i 's/if(NOT MSVC)/if(1)/' \
        /openjtalk-src/lib/open_jtalk/src/CMakeLists.txt \
    && sed -i '/^project(openjtalk)/a\\nadd_compile_definitions(_GLIBCXX_USE_DEPRECATED=1)' \
        /openjtalk-src/lib/open_jtalk/src/CMakeLists.txt

# Build OpenJTalk as a static library
RUN cmake -S /openjtalk-src/lib/open_jtalk/src -B /openjtalk-build \
      -DCMAKE_INSTALL_PREFIX=/openjtalk-install \
      -DCMAKE_BUILD_TYPE=Release \
      -DBUILD_SHARED_LIBS=OFF \
      -DCHARSET=utf8 \
      -DCMAKE_POSITION_INDEPENDENT_CODE=ON \
    && cmake --build /openjtalk-build --parallel "$(nproc)" \
    && cmake --install /openjtalk-build

# Copy MeCab dictionary for runtime
RUN mkdir -p /openjtalk-dic \
    && cp -r /openjtalk-src/pyopenjtalk/dictionary/* /openjtalk-dic/

# Build Go binary with OpenJTalk CGO bindings
WORKDIR /src
COPY src/go/ ./src/go/

WORKDIR /src/src/go
RUN CGO_ENABLED=1 \
    CGO_CFLAGS="-I/openjtalk-install/include/openjtalk" \
    CGO_LDFLAGS="-L/openjtalk-install/lib -lopenjtalk -lstdc++ -lm" \
    go build -tags openjtalk -o /piper-plus ./cmd/piper-plus

# ============================================================
# Stage 2: Runtime
# Minimal Debian image with ONNX Runtime, the compiled Go
# binary, and OpenJTalk dictionary for Japanese G2P.
# ============================================================
FROM debian:trixie-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libstdc++6 wget \
    && rm -rf /var/lib/apt/lists/*

# Download ONNX Runtime shared library.
# Uses x64 naming convention (changed from x86_64 in recent releases).
ARG ORT_VERSION=1.24.4
RUN set -eux \
    && wget -q "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    && tar xzf "onnxruntime-linux-x64-${ORT_VERSION}.tgz" \
    && cp "onnxruntime-linux-x64-${ORT_VERSION}/lib/libonnxruntime.so" /usr/lib/ \
    && rm -rf onnxruntime-* \
    && ldconfig

# Copy the Go binary and OpenJTalk dictionary from the build stage
COPY --from=builder /piper-plus /usr/local/bin/piper-plus
COPY --from=builder /openjtalk-dic /usr/share/open_jtalk/dic

# Environment configuration
ENV ONNX_RUNTIME_SHARED_LIBRARY_PATH=/usr/lib/libonnxruntime.so
ENV OPENJTALK_DIC_DIR=/usr/share/open_jtalk/dic
ENV PIPER_MODEL_DIR=/models

RUN mkdir -p /models

# Run as non-root user for security
RUN useradd -r -m -d /app piper \
    && chown piper:piper /models
USER piper

WORKDIR /app
ENTRYPOINT ["piper-plus"]
