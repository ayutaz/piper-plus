# Python Inference Environment for piper-plus (GPU/CPU)
# GPU support via onnxruntime-gpu; also works without --gpus (CPU fallback)
# Includes Gradio WebUI (--webui mode)
#
# Base: CUDA 12.8.1 + cuDNN 9 + Ubuntu 24.04 (Issue #527 Fully-aligned 戦略
# DR-001 で bump、 12.6.3 + Ubuntu 22.04 → 12.8.1 + Ubuntu 24.04)。
# - CUDA 12.8 で RTX 5090 (Blackwell sm_120) を正式サポート
# - wheel cu128 と image CUDA toolkit を同 major で揃え、 forward-compat
#   依存を解消
# - Ubuntu 24.04 (Noble) は EOL 2029-04 で OS 寿命延長
# - host driver R570+ が前提 (新 GPU 環境では問題なし、 OQ-01 で確定)
FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.13 via deadsnakes PPA. Ubuntu 24.04 (Noble) の apt
# 標準は python3.12、 3.13 は deadsnakes PPA (CPython core dev maintained)
# 経由で取得。 Issue #527 / DR-001 で deadsnakes 採用が確定。
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.13 \
    python3.13-venv \
    python3-pip \
    libsndfile1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.13 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.13 1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip / setuptools / wheel to clear Trivy supply-chain CVEs.
# Run before installing uv so the upgraded pip is what bootstraps the rest.
# --ignore-installed は Ubuntu 24.04 の apt-installed pip 24.0 で
# 「Cannot uninstall pip 24.0, RECORD file not found」 を回避するため必須
# (debian package が pip metadata を持たないことに起因する既知問題)。
RUN pip install --no-cache-dir --upgrade --break-system-packages --ignore-installed pip setuptools wheel

# Install uv. --break-system-packages は Ubuntu 24.04 + Python 3.13 環境で
# PEP 668 protections を bypass するため。 venv を使わず system Python に
# 直接 install する Docker 慣習に沿う。
RUN pip install --no-cache-dir --break-system-packages uv

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
