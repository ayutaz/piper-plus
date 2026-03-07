# Python Training Environment for Piper TTS
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
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# PyTorch (CUDA 12.1)
RUN uv pip install --system \
    --extra-index-url https://download.pytorch.org/whl/cu121 \
    "torch==2.2.1+cu121" "torchaudio==2.2.1+cu121" "torchvision==0.17.1+cu121"

# Copy source code for piper-train installation
COPY src/python /tmp/piper-src/python
COPY VERSION /tmp/piper-src/VERSION

# Install piper_train with training extras
RUN uv pip install --system "/tmp/piper-src/python/[train]"

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
COPY --from=builder /tmp/piper-src /opt/piper

# Create working directory
WORKDIR /workspace

# Create directories for datasets and checkpoints
RUN mkdir -p /workspace/datasets /workspace/checkpoints /workspace/logs

# Expose ports for tensorboard and jupyter
EXPOSE 6006 8888

# Run tests during build to verify the container is working
RUN echo "=== Running build-time tests ===" && \
    python --version && \
    python -c "import torch; print(f'PyTorch: {torch.__version__}')" && \
    python -c "import pytorch_lightning; print(f'PyTorch Lightning: {pytorch_lightning.__version__}')" && \
    cd /opt/piper/python && python -c "import piper_train; print('piper_train accessible')" && \
    echo "=== Build-time tests passed ==="

# Ensure we have a valid working directory
WORKDIR /workspace

# Default command for runtime
CMD ["echo", "Container started successfully"]
