# Multi-stage build for C++ Inference Environment

# Stage 1: Builder (using cpp-train as base)
FROM piper-cpp-train:latest AS builder

WORKDIR /workspace

# Copy source code
COPY src/ /workspace/src/
COPY CMakeLists.txt /workspace/
COPY cmake/ /workspace/cmake/

# Build piper in release mode
RUN mkdir -p build && cd build && \
    cmake .. \
        -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/install \
        -DBUILD_TESTS=OFF \
        -DUSE_CUDA=ON && \
    ninja -j$(nproc) && \
    ninja install

# Stage 2: Runtime (minimal)
FROM nvidia/cuda:12.4.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:/usr/local/lib:$LD_LIBRARY_PATH

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    libgomp1 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install ONNX Runtime (runtime libraries only)
RUN cd /tmp && \
    wget -q https://github.com/microsoft/onnxruntime/releases/download/v1.17.1/onnxruntime-linux-x64-gpu-1.17.1.tgz && \
    tar -xzf onnxruntime-linux-x64-gpu-1.17.1.tgz && \
    cp onnxruntime-linux-x64-gpu-1.17.1/lib/*.so* /usr/local/lib/ && \
    rm -rf onnxruntime-linux-x64-gpu-1.17.1* && \
    ldconfig

# Copy installed files from builder
COPY --from=builder /install/bin/piper /usr/local/bin/piper
COPY --from=builder /install/lib/*.so* /usr/local/lib/
COPY --from=builder /install/share/ /usr/local/share/

# Copy pre-built libraries from builder
COPY --from=builder /usr/local/lib/libpiper_phonemize.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libespeak-ng.so* /usr/local/lib/
COPY --from=builder /usr/local/share/espeak-ng-data /usr/local/share/espeak-ng-data

# Install Japanese support libraries (runtime only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmecab2 \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

# Copy OpenJTalk runtime libraries
COPY --from=builder /usr/local/lib/libHTSEngine.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/lib*jpcommon.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/lib*njd*.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libtext2mecab.so* /usr/local/lib/
COPY --from=builder /usr/local/lib/libmecab2njd.so* /usr/local/lib/

# Update library cache
RUN ldconfig

# Create directories
RUN mkdir -p /app/models /app/output /app/config

# Set working directory
WORKDIR /app

# Copy entrypoint script
COPY docker/cpp-inference/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Verify installation
RUN piper --version || echo "Piper not found, will be mounted at runtime"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD piper --version || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["piper", "--help"]