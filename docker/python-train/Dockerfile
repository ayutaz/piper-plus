# Python Training Environment for Piper TTS
FROM nvidia/cuda:12.4.0-cudnn8-devel-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    libsndfile1 \
    libsndfile1-dev \
    libportaudio2 \
    libportaudiocpp0 \
    portaudio19-dev \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    python3-pip \
    sox \
    ffmpeg \
    libsox-dev \
    libsox-fmt-all \
    libasound2-dev \
    libpulse-dev \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip
RUN python -m pip install --upgrade pip setuptools wheel

# Create working directory
WORKDIR /workspace

# Copy requirements file (will be created separately)
COPY requirements-train.txt /workspace/

# Install Python dependencies
RUN pip install -r requirements-train.txt

# Install piper-train from source
RUN git clone https://github.com/rhasspy/piper.git && \
    cd piper && \
    pip install -e src/python/

# Install additional tools for training
RUN pip install \
    tensorboard \
    wandb \
    matplotlib \
    seaborn \
    jupyter \
    ipywidgets

# Create directories for datasets and checkpoints
RUN mkdir -p /workspace/datasets /workspace/checkpoints /workspace/logs

# Expose ports for tensorboard and jupyter
EXPOSE 6006 8888

# Set up entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/bin/bash"]