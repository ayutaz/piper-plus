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

# Build OpenJTalk as a static library and copy the MeCab dictionary, from
# the pyopenjtalk-plus sdist. The same script builds the library for the
# `openjtalk` job of .github/workflows/go-ci.yml, which runs the
# openjtalk-tagged tests.
COPY src/go/scripts/build-openjtalk.sh /usr/local/bin/build-openjtalk.sh
RUN bash /usr/local/bin/build-openjtalk.sh /openjtalk-src /openjtalk-install /openjtalk-dic \
    && rm -rf /openjtalk-src

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
# Selects the correct tarball based on docker buildx's TARGETARCH automatic
# argument so multi-arch builds (linux/amd64, linux/arm64) work transparently.
ARG TARGETARCH
ARG ORT_VERSION=1.24.4
ARG ORT_SHA256_AMD64=3a211fbea252c1e66290658f1b735b772056149f28321e71c308942cdb54b747
ARG ORT_SHA256_ARM64=866109a9248d057671a039b9d725be4bd86888e3754140e6701ec621be9d4d7e
RUN set -eux \
    && case "${TARGETARCH:-amd64}" in \
         amd64) ORT_ARCH=x64;     ORT_SHA256=${ORT_SHA256_AMD64} ;; \
         arm64) ORT_ARCH=aarch64; ORT_SHA256=${ORT_SHA256_ARM64} ;; \
         *) echo "Unsupported TARGETARCH: ${TARGETARCH}"; exit 1 ;; \
       esac \
    && wget -q "https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}.tgz" \
    && echo "${ORT_SHA256}  onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}.tgz" | sha256sum -c - \
    && tar xzf "onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}.tgz" \
    && cp "onnxruntime-linux-${ORT_ARCH}-${ORT_VERSION}/lib/libonnxruntime.so" /usr/lib/ \
    && rm -rf onnxruntime-* \
    && ldconfig

# Copy the Go binary and OpenJTalk dictionary from the build stage
COPY --from=builder /piper-plus /usr/local/bin/piper-plus
COPY --from=builder /openjtalk-dic /usr/local/share/open_jtalk/dic

# Environment configuration
ENV ONNX_RUNTIME_SHARED_LIBRARY_PATH=/usr/lib/libonnxruntime.so
ENV OPENJTALK_DICTIONARY_PATH=/usr/local/share/open_jtalk/dic
ENV PIPER_PLUS_MODEL_DIR=/models

RUN mkdir -p /models

# Run as non-root user for security
RUN useradd -r -m -d /app piper \
    && chown piper:piper /models
USER piper

WORKDIR /app
ENTRYPOINT ["piper-plus"]
