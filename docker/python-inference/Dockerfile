# Python Inference Environment for Piper TTS (GPU/CPU)
# GPU support via onnxruntime-gpu; also works without --gpus (CPU fallback)
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11 and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    libsndfile1 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir --break-system-packages uv

WORKDIR /app

# Copy source tree for piper_train install
# setup.py reads ../../VERSION relative to src/python/
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python/ /app/src/python/

# Install piper_train with inference-gpu extras (includes onnxruntime-gpu)
RUN uv pip install --system "/app/src/python[inference-gpu]"

# Create directories for models and output
RUN mkdir -p /app/models /app/output

# Copy inference script and test script
COPY docker/python-inference/inference.py /app/
COPY docker/python-inference/test.py /app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import piper_train; import onnxruntime" || exit 1

# Build-time smoke test
RUN python --version && \
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}'); print(f'Providers: {ort.get_available_providers()}')" && \
    python -c "import piper_train; print('piper_train installed')"

CMD ["echo", "Container started successfully"]
