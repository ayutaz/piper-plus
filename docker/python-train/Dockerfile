# Python Training Environment for piper-plus
# Multi-stage build to reduce final image size

# Build stage
FROM nvidia/cuda:12.1.0-cudnn8-devel-ubuntu22.04 AS builder

# Free up space in the build environment
RUN rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* || true

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

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
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

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
