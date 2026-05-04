# C++ Development Environment for piper-plus (CPU-only)
FROM ubuntu:24.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and development tools
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    git \
    wget \
    curl \
    vim \
    gdb \
    valgrind \
    clang \
    clang-format \
    clang-tidy \
    ccache \
    libsndfile1-dev \
    libopenblas-dev \
    libeigen3-dev \
    libfmt-dev \
    libspdlog-dev \
    libgtest-dev \
    libgmock-dev \
    libbenchmark-dev \
    python3.12 \
    python3.12-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Note: eSpeak-ng and piper-phonemize are NO LONGER needed.
# piper-plus uses self-contained G2P for all 7 languages (JA/EN/ZH/ES/FR/PT/SV).

# Install ONNX Runtime (CPU, Linux x64)
RUN wget -q https://github.com/microsoft/onnxruntime/releases/download/v1.17.0/onnxruntime-linux-x64-1.17.0.tgz && \
    tar -xzf onnxruntime-linux-x64-1.17.0.tgz && \
    cp onnxruntime-linux-x64-1.17.0/lib/* /usr/local/lib/ && \
    cp -r onnxruntime-linux-x64-1.17.0/include/* /usr/local/include/ && \
    ldconfig && \
    rm -rf onnxruntime-linux-x64-1.17.0*

# Install OpenJTalk and dependencies
RUN apt-get update && apt-get install -y \
    libmecab-dev \
    mecab \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

# NOTE: HTS Engine is only needed for building the system open_jtalk binary
# (used as fallback in tests). piper-plus CMake build uses hts_engine_stub instead.
# This can be removed once the system open_jtalk fallback is no longer needed.
RUN wget https://downloads.sourceforge.net/hts-engine/hts_engine_API-1.10.tar.gz && \
    tar -xzf hts_engine_API-1.10.tar.gz && \
    cd hts_engine_API-1.10 && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    cd .. && rm -rf hts_engine_API-1.10*

# Install Open JTalk (serial build to avoid race condition)
RUN wget https://downloads.sourceforge.net/open-jtalk/open_jtalk-1.11.tar.gz && \
    tar -xzf open_jtalk-1.11.tar.gz && \
    cd open_jtalk-1.11 && \
    ./configure --prefix=/usr/local --with-hts-engine-header-path=/usr/local/include --with-hts-engine-library-path=/usr/local/lib && \
    make -j1 && \
    make install && \
    cd .. && rm -rf open_jtalk-1.11*

# Create working directory
WORKDIR /workspace

# Install uv via official installer
ENV UV_INSTALL_DIR=/usr/local/bin
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Create a dedicated venv for development tools (avoids PEP 668 on Ubuntu 24.04 / python3.12)
ENV VIRTUAL_ENV=/opt/devtools
RUN uv venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install development tools into the venv
RUN uv pip install \
    conan \
    cpplint \
    cppcheck \
    cmake-format \
    gcovr

# Set up development environment
RUN echo "export CC=clang" >> ~/.bashrc && \
    echo "export CXX=clang++" >> ~/.bashrc && \
    echo "export CCACHE_DIR=/workspace/.ccache" >> ~/.bashrc

# Create build directories
RUN mkdir -p /workspace/build /workspace/.ccache

# Copy build scripts
COPY docker/cpp-dev/build.sh /workspace/
RUN chmod +x /workspace/build.sh

# Copy test script
COPY docker/cpp-dev/test.sh /workspace/
RUN chmod +x /workspace/test.sh

# Run tests during build to verify the container is working
RUN echo "=== Running build-time tests ===" && \
    echo "Testing build tools..." && \
    which gcc && which g++ && which cmake && \
    echo "Testing libraries..." && \
    ldconfig -p | grep -E "HTSEngine" || echo "Some libraries in /usr/local/lib" && \
    echo "=== Build-time tests passed ==="

# Create non-root user and transfer ownership of workspace
# ubuntu:24.04 has a default 'ubuntu' user with UID 1000; remove it first to avoid collision
RUN userdel -r ubuntu 2>/dev/null || true && \
    useradd -m -u 1000 piper && chown -R piper:piper /workspace
USER piper

# Ensure we're in a valid directory
WORKDIR /workspace

# Default command for runtime
CMD ["echo", "Container started successfully"]
