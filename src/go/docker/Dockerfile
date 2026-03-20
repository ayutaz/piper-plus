# ============================================================
# Stage 1: Build
# Compile the Go CLI binary with CGO enabled (required for
# ONNX Runtime C bindings). Alpine's musl-dev provides the
# C toolchain needed for CGO.
# ============================================================
FROM golang:1.26-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /src
COPY src/go/ ./src/go/

WORKDIR /src/src/go
RUN CGO_ENABLED=1 go build -o /piper-plus ./cmd/piper-plus

# ============================================================
# Stage 2: Runtime
# Minimal Alpine image with only the compiled binary and
# ONNX Runtime shared library. Suitable for both CLI usage
# and as a base for HTTP server mode.
# ============================================================
FROM alpine:3.21

# ca-certificates: HTTPS model downloads; libstdc++: ONNX Runtime dependency
RUN apk add --no-cache ca-certificates libstdc++

# Download ONNX Runtime shared library at build time.
# Override TARGETARCH for cross-compilation (e.g. aarch64).
ARG ORT_VERSION=1.21.0
ARG TARGETARCH=x86_64
RUN set -eux \
    && wget -q https://github.com/microsoft/onnxruntime/releases/download/v${ORT_VERSION}/onnxruntime-linux-${TARGETARCH}-${ORT_VERSION}.tgz \
    && tar xzf onnxruntime-linux-${TARGETARCH}-${ORT_VERSION}.tgz \
    && cp onnxruntime-linux-${TARGETARCH}-${ORT_VERSION}/lib/libonnxruntime.so /usr/lib/ \
    && rm -rf onnxruntime-* \
    && ldconfig /usr/lib || true

# Copy the statically-linked Go binary from the build stage
COPY --from=builder /piper-plus /usr/local/bin/piper-plus

# Tell the Go binary where to find the ONNX Runtime library
ENV ONNX_RUNTIME_SHARED_LIBRARY_PATH=/usr/lib/libonnxruntime.so

# Default directory for mounting ONNX voice models
ENV PIPER_MODEL_DIR=/models
RUN mkdir -p /models

# Run as non-root user for security
RUN adduser -D -h /app piper
USER piper

WORKDIR /app
ENTRYPOINT ["piper-plus"]
