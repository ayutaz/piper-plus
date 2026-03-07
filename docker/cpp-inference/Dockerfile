# Multi-stage build for C++ Inference Environment

# Stage 1: Builder
FROM ubuntu:22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Install build dependencies
# All C++ libraries (fmt, spdlog, piper-phonemize, espeak-ng, OpenJTalk)
# are built automatically via CMake ExternalProject
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    ninja-build \
    pkg-config \
    ca-certificates \
    autoconf automake libtool \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy build files and source code
COPY CMakeLists.txt VERSION ./
COPY cmake/ cmake/
COPY src/cpp/ src/cpp/

# Build piper (all C++ deps resolved via CMake ExternalProject)
RUN mkdir -p build && cd build && \
    cmake .. \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/install \
        -DBUILD_TESTS=OFF && \
    ninja -j$(nproc) && \
    ninja install

# Stage 2: Runtime (minimal with CUDA support)
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy build artifacts from builder
COPY --from=builder /install/ /usr/local/

# Install ONNX Runtime GPU (auto-detect version to match builder)
RUN ONNX_VERSION=$(ls /usr/local/lib/libonnxruntime.so.* 2>/dev/null | grep -oP '\d+\.\d+\.\d+' | head -1) && \
    echo "Detected ONNX Runtime version: $ONNX_VERSION" && \
    cd /tmp && \
    wget -q "https://github.com/microsoft/onnxruntime/releases/download/v${ONNX_VERSION}/onnxruntime-linux-x64-gpu-${ONNX_VERSION}.tgz" && \
    tar -xzf "onnxruntime-linux-x64-gpu-${ONNX_VERSION}.tgz" && \
    cp onnxruntime-linux-x64-gpu-${ONNX_VERSION}/lib/*.so* /usr/local/lib/ && \
    rm -rf onnxruntime-linux-x64-gpu-${ONNX_VERSION}* && \
    ldconfig

# Create directories
RUN mkdir -p /app/models /app/output /app/config

WORKDIR /app

# Copy entrypoint and test scripts
COPY docker/cpp-inference/entrypoint.sh /entrypoint.sh
COPY docker/cpp-inference/test.sh /test.sh
RUN chmod +x /entrypoint.sh /test.sh

# Verify installation
RUN piper --version || echo "Piper not found, will be mounted at runtime"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD piper --version || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
