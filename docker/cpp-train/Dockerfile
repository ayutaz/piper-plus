# C++ Training/Development Environment for Piper TTS
FROM nvidia/cuda:12.4.1-cudnn-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

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

# Install ONNX Runtime
RUN wget https://github.com/microsoft/onnxruntime/releases/download/v1.17.1/onnxruntime-linux-x64-gpu-1.17.1.tgz && \
    tar -xzf onnxruntime-linux-x64-gpu-1.17.1.tgz && \
    cp -r onnxruntime-linux-x64-gpu-1.17.1/include/* /usr/local/include/ && \
    cp -r onnxruntime-linux-x64-gpu-1.17.1/lib/* /usr/local/lib/ && \
    rm -rf onnxruntime-linux-x64-gpu-1.17.1*

# Install espeak-ng from source
RUN git clone https://github.com/espeak-ng/espeak-ng.git && \
    cd espeak-ng && \
    ./autogen.sh && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install && \
    cd .. && rm -rf espeak-ng

# Install piper-phonemize
RUN git clone https://github.com/rhasspy/piper-phonemize.git && \
    cd piper-phonemize && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) && \
    make install && \
    cd ../.. && rm -rf piper-phonemize

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

# Install Open JTalk
RUN wget https://downloads.sourceforge.net/open-jtalk/open_jtalk-1.11.tar.gz && \
    tar -xzf open_jtalk-1.11.tar.gz && \
    cd open_jtalk-1.11 && \
    ./configure --prefix=/usr/local --with-hts-engine-header-path=/usr/local/include --with-hts-engine-library-path=/usr/local/lib && \
    make -j$(nproc) && \
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
COPY build.sh /workspace/
RUN chmod +x /workspace/build.sh

CMD ["/bin/bash"]