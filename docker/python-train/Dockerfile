# Python Training Environment for piper-plus
# Multi-stage build to reduce final image size

# Build stage
# Base: CUDA 12.6.3 + cuDNN 9 + Ubuntu 22.04
#
# Why the CUDA/cuDNN version mismatch with torch==2.2.1+cu121 is safe:
#   - torch wheel bundles its own CUDA runtime libraries (libcudart, libcublas,
#     libcufft, libcurand, libcusolver, libcusparse, libcudnn 8.9, libnccl) under
#     /opt/venv/lib/python*/site-packages/{nvidia,torch/lib} and uses them
#     dynamically at runtime. The system CUDA 12.6 toolkit installed under
#     /usr/local/cuda is NOT used by torch — it ships only for non-torch CUDA
#     consumers (CMake / nvcc invocations from third-party packages).
#   - NVIDIA CUDA forward compatibility: drivers from newer toolkits (12.6)
#     fully support binaries built against older toolkits (12.1), so wheel-
#     bundled cu121 runtime libs load correctly on the 12.6 image's driver.
#   - cuDNN bundled by torch (8.9) takes precedence at dlopen time because
#     site-packages/nvidia/cudnn/lib appears earlier in the loader path than
#     the image's /usr/lib/x86_64-linux-gnu cuDNN 9.
# Bumped from 12.1.0 to clear Trivy OS-package CVEs (libssl/glibc/libxml2
# etc.) accumulated since the 2023-04 base.
FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu22.04 AS builder

# Free up space in the build environment
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* || true

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH
# Disable uv wheel cache to prevent layer bloat. Builder stage installs
# torch+CUDA (~3GB) and scipy/numpy/librosa via uv pip — without this,
# uv keeps a full archive of every wheel under /root/.cache/uv (~3-5GB
# extra layer), exhausting the runner's ephemeral disk during multi-stage
# COPY of /opt/venv. Wheels are re-downloaded on rebuild, but that's
# absorbed by docker/build-push-action's GitHub-Actions cache (cache-from:
# type=gha) — we only pay this cost on cache miss. Issue #495.
ENV UV_NO_CACHE=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    portaudio19-dev \
    libsndfile1-dev \
    libasound2-dev \
    libpulse-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Install uv
RUN pip install --no-cache-dir uv

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# PyTorch (CUDA 12.1)
RUN uv pip install \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.2.1+cu121" "torchaudio==2.2.1+cu121" "torchvision==0.17.1+cu121"

# Copy source code for piper-train installation
# setup.py reads ../../VERSION relative to src/python/
COPY src/python /tmp/src/python
COPY VERSION /tmp/VERSION

# Install piper_plus_g2p (standalone G2P package, not on PyPI)
RUN uv pip install "/tmp/src/python/g2p"

# Install piper_train with training extras
RUN uv pip install "/tmp/src/python[train]"

# Runtime stage
# Base: CUDA 12.6.3 + cuDNN 9 + Ubuntu 22.04 (matches builder stage)
# Same CUDA/cuDNN compatibility argument as builder stage: torch 2.2.1+cu121
# wheel (copied via /opt/venv) bundles its own CUDA 12.1 runtime + cuDNN 8.9
# under site-packages and loads them via the venv's library path. The image's
# 12.6 system libraries are used only for non-torch CUDA consumers. NVIDIA
# driver forward compat ensures cu121 binaries run on 12.6 drivers.
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    libsndfile1 \
    libportaudio2 \
    sox \
    ffmpeg \
    libsox-fmt-all \
    libasound2-dev \
    libpulse-dev \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy piper source
COPY --from=builder /tmp/src /opt/piper/src
COPY --from=builder /tmp/VERSION /opt/piper/VERSION

# Create working directory
WORKDIR /workspace

# Create directories for datasets and checkpoints
RUN mkdir -p /workspace/datasets /workspace/checkpoints /workspace/logs

# Expose ports for tensorboard and jupyter
EXPOSE 6006 8888

# Download NLTK data required by g2p-en (English phonemizer)
# Use a shared path so data is accessible after USER switch to non-root
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Run tests during build to verify the container is working
RUN echo "=== Running build-time tests ===" && \
    python --version && \
    python -c "import torch; print(f'PyTorch: {torch.__version__}')" && \
    python -c "import pytorch_lightning; print(f'PyTorch Lightning: {pytorch_lightning.__version__}')" && \
    cd /opt/piper/src/python && python -c "import piper_train; print('piper_train accessible')" && \
    echo "=== Build-time tests passed ==="

# Create non-root user and transfer ownership of working directories
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /workspace /opt/venv /opt/piper
USER piper

# Ensure we have a valid working directory
WORKDIR /workspace

# Default command for runtime
CMD ["echo", "Container started successfully"]
