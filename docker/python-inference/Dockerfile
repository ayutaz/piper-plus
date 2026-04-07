# Python Inference Environment for piper-plus (GPU/CPU)
# GPU support via onnxruntime-gpu; also works without --gpus (CPU fallback)
# Includes Gradio WebUI (--webui mode)
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

# Install uv (Ubuntu 22.04's pip doesn't support --break-system-packages)
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy source tree for piper_train install
# setup.py reads ../../VERSION relative to src/python/
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python/ /app/src/python/

# Install piper_plus_g2p (standalone G2P package) and piper_train
RUN uv pip install --system "/app/src/python/g2p"
RUN uv pip install --system "/app/src/python[inference-gpu]"

# Install Gradio WebUI requirements
COPY src/python_run/requirements_webui.txt /app/requirements_webui.txt
RUN uv pip install --system -r /app/requirements_webui.txt

# Pre-download NLTK data for g2p-en (both old and new resource names for NLTK compatibility)
# Use a shared path so data is accessible after USER switch to non-root
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Create directories for models and output
RUN mkdir -p /app/models /app/output

# Copy inference script, test script, and WebUI app
COPY docker/python-inference/inference.py /app/
COPY docker/python-inference/test.py /app/
COPY docker/webui/app.py /app/webui.py

# Expose FastAPI (8000) and Gradio (7860) ports
EXPOSE 8000 7860

# Gradio environment defaults
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Healthcheck: verify the API server is responding.
# When used via docker-compose, the compose healthcheck overrides this.
# start-period allows the model to load before checks begin.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Build-time smoke test
RUN python --version && \
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}'); print(f'Providers: {ort.get_available_providers()}')" && \
    python -c "import piper_train; print('piper_train installed')" && \
    python -c "import gradio; print(f'Gradio: {gradio.__version__}')"

# Run as non-root user for security
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /app/models /app/output
USER piper

CMD ["echo", "Container started successfully"]
