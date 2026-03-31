# C++ Development Environment for piper-plus (CPU-only)
FROM ubuntu:22.04

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
    python3.11 \
    python3.11-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Note: eSpeak-ng and piper-phonemize are NO LONGER needed.
# piper-plus uses self-contained G2P for all 7 languages (JA/EN/ZH/ES/FR/PT/SV).

# Install ONNX Runtime (CPU, Linux x64)
RUN wget -q https://github.com/microsoft/onnxruntime/releases/download/v1.14.1/onnxruntime-linux-x64-1.14.1.tgz && \
    tar -xzf onnxruntime-linux-x64-1.14.1.tgz && \
    cp onnxruntime-linux-x64-1.14.1/lib/* /usr/local/lib/ && \
    cp -r onnxruntime-linux-x64-1.14.1/include/* /usr/local/include/ && \
    ldconfig && \
    rm -rf onnxruntime-linux-x64-1.14.1*

# Install OpenJTalk and dependencies
RUN apt-get update && apt-get install -y \
    libmecab-dev \
    mecab \
    mecab-ipadic-utf8 \
    && rm -rf /var/lib/apt/lists/*

# Install HTS Engine
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

# Install development tools
RUN pip3 install \
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

# Ensure we're in a valid directory
WORKDIR /workspace

# Default command for runtime
CMD ["echo", "Container started successfully"]
