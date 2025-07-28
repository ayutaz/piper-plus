# Python Inference Environment for Piper TTS
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=$CUDA_HOME/bin:$PATH
ENV LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Install system dependencies (minimal for inference)
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    wget \
    curl \
    libsndfile1 \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    libasound2 \
    libpulse0 \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

# Upgrade pip
RUN python -m pip install --upgrade pip setuptools wheel

# Create working directory
WORKDIR /app

# Copy requirements file
COPY docker/python-inference/requirements-inference.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-inference.txt

# Install piper-tts
RUN pip install --no-cache-dir piper-tts

# Create directories for models and output
RUN mkdir -p /app/models /app/output

# Copy inference script
COPY docker/python-inference/inference.py /app/

# Expose port for API service (optional)
EXPOSE 8000

# Set up healthcheck
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import torch; import piper; print('Health check passed')" || exit 1

CMD ["python", "inference.py"]