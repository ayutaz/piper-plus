# Multi-stage build for C++ Inference Environment

# Stage 1: Builder
FROM ubuntu:24.04 AS builder

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

# Ensure OpenJTalk dictionary is present for Japanese TTS support.
# The CMake install may have already copied it from the build output.
# If not, download it explicitly so the runtime image is self-contained.
RUN if [ ! -d /install/share/open_jtalk/dic ]; then \
      echo "OpenJTalk dictionary not found in install prefix, downloading..." && \
      mkdir -p /install/share/open_jtalk && \
      wget -q -O /tmp/open_jtalk_dic.tar.gz \
        "https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz" && \
      tar -xzf /tmp/open_jtalk_dic.tar.gz -C /install/share/open_jtalk && \
      mv /install/share/open_jtalk/open_jtalk_dic_utf_8-1.11 /install/share/open_jtalk/dic && \
      rm -f /tmp/open_jtalk_dic.tar.gz && \
      echo "OpenJTalk dictionary installed successfully"; \
    else \
      echo "OpenJTalk dictionary already present at /install/share/open_jtalk/dic"; \
    fi

# Stage 2: Runtime (CPU only)
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_LIBRARY_PATH=/usr/local/lib:$LD_LIBRARY_PATH

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy build artifacts from builder (includes CPU ONNX Runtime built via ExternalProject)
COPY --from=builder /install/ /usr/local/
RUN ldconfig

# Create directories
RUN mkdir -p /app/models /app/output /app/config

WORKDIR /app

# Copy entrypoint and test scripts
COPY docker/cpp-inference/entrypoint.sh /entrypoint.sh
COPY docker/cpp-inference/test.sh /test.sh
RUN chmod +x /entrypoint.sh /test.sh

# Verify installation
RUN piper --version || echo "Piper not found, will be mounted at runtime"

# Verify OpenJTalk dictionary is available for Japanese TTS
RUN test -d /usr/local/share/open_jtalk/dic && \
    echo "OpenJTalk dictionary verified at /usr/local/share/open_jtalk/dic" || \
    echo "WARNING: OpenJTalk dictionary not found, Japanese TTS may not work"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD piper --version || exit 1

# Run as non-root user for security
# ubuntu:24.04 has a default 'ubuntu' user with UID 1000; remove it first to avoid collision
RUN userdel -r ubuntu 2>/dev/null || true && \
    useradd -m -u 1000 piper && \
    chown -R piper:piper /app
USER piper

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]
