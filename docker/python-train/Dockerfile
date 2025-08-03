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

# Upgrade pip
RUN python -m pip install --upgrade pip setuptools wheel

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements files
COPY docker/python-train/requirements-train.txt /tmp/
COPY docker/python-train/requirements-torch.txt /tmp/

# Install PyTorch packages first with CUDA support
RUN pip install --no-cache-dir -r /tmp/requirements-torch.txt && \
    pip cache purge && \
    rm -rf ~/.cache/pip/*

# Install other Python dependencies in virtual environment
RUN pip install --no-cache-dir -r /tmp/requirements-train.txt && \
    pip cache purge && \
    rm -rf ~/.cache/pip/*

# Copy source code for piper-train installation
COPY src/python /tmp/piper-src/python

# Install piper-train from local source
RUN cd /tmp/piper-src/python && \
    pip install --no-cache-dir -e . && \
    pip cache purge && \
    rm -rf ~/.cache/pip/*

# Install additional tools
RUN pip install --no-cache-dir \
    tensorboard \
    wandb \
    matplotlib \
    seaborn \
    jupyter \
    ipywidgets && \
    pip cache purge && \
    rm -rf ~/.cache/pip/*

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

# Copy test script
COPY docker/python-train/test.py /test.py

# Run tests during build to verify the container is working
RUN echo "=== Running build-time tests ===" && \
    python --version && \
    python -c "import torch; print(f'PyTorch: {torch.__version__}')" && \
    python -c "import piper_train; print('piper_train installed successfully')" && \
    echo "=== Build-time tests passed ==="

# Default command for runtime
CMD ["/bin/bash"]