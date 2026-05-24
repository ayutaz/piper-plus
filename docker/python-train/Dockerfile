# Python Training Environment for piper-plus
# Multi-stage build to reduce final image size

# Build stage
# Base: CUDA 12.8.1 + cuDNN 9 + Ubuntu 24.04 (Issue #527 Fully-aligned DR-001)
#
# Issue #527 で fully-aligned 戦略を採用:
#   - CUDA toolkit (image) と torch wheel (cu128) の major を揃え、 forward-
#     compat 依存を解消
#   - RTX 5090 (Blackwell sm_120) は CUDA 12.8+ + driver R570+ が必須
#   - Ubuntu 24.04 (Noble) EOL 2029-04 で OS 寿命延長 (Jammy 22.04 EOL 2027-04)
#   - Python 3.13 を deadsnakes PPA 経由で取得 (Ubuntu 24.04 apt default は 3.12)
#
# 旧版 (12.6.3 + ubuntu22.04 + torch 2.2.1+cu121) では wheel bundle cuDNN 8.9
# と image cuDNN 9 が共存していたが、 12.8 + torch 2.11.0+cu128 では wheel
# bundle cuDNN 9.5+ と image cuDNN 9 が同 major で揃う。
FROM nvidia/cuda:12.8.1-cudnn-devel-ubuntu24.04 AS builder

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

# Install build dependencies + Python 3.13 via deadsnakes PPA
# Ubuntu 24.04 (Noble) の apt 標準は python3.12、 3.13 は deadsnakes
# (CPython core dev maintained) 経由で取得 (Issue #527 / DR-001)。
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    python3.13 \
    python3.13-dev \
    python3.13-venv \
    python3-pip \
    portaudio19-dev \
    libsndfile1-dev \
    libasound2-dev \
    libpulse-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set Python 3.13 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1

# Install uv. --break-system-packages: Ubuntu 24.04 + Python 3.13 環境で
# PEP 668 protections を bypass。 後段で venv を作る用途のため system pip に
# 直接 install してよい。
RUN pip install --no-cache-dir --break-system-packages uv

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# PyTorch (CUDA 12.8、 Issue #527 / DR-001 で cu121 → cu128 bump)
# - RTX 5090 (Blackwell sm_120) を起動するために cu128 wheel 必須
# - uv.lock canonical (root pyproject.toml `[[tool.uv.index]]` cu128) と整合
# - torchvision は piper-train で未使用のため削除 (FR-02-05)
RUN uv pip install \
    --extra-index-url https://download.pytorch.org/whl/cu128 \
    "torch==2.11.0+cu128" "torchaudio==2.11.0+cu128"

# Copy source code for piper-train installation
# setup.py reads ../../VERSION relative to src/python/
COPY src/python /tmp/src/python
COPY VERSION /tmp/VERSION

# Install piper_plus_g2p (standalone G2P package, not on PyPI)
RUN uv pip install "/tmp/src/python/g2p"

# Install piper_train with training extras
RUN uv pip install "/tmp/src/python[train]"

# Runtime stage
# Base: CUDA 12.8.1 + cuDNN 9 + Ubuntu 24.04 (matches builder stage、
# Issue #527 / DR-001 Fully-aligned 戦略)
# wheel (copied via /opt/venv) bundles CUDA 12.8 runtime + cuDNN 9.5+
# under site-packages、 image cuDNN 9 と同 major で揃う。
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Install runtime dependencies + Python 3.13 via deadsnakes PPA
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.13 \
    python3.13-venv \
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

# Set Python 3.13 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1

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
