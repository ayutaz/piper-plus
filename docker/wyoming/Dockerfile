# Wyoming Protocol TTS adapter for piper-plus
# CPU-only by default (lightweight for Home Assistant usage)
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# System dependencies for audio processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy source tree for piper_train install (ort_utils dependency)
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python/ /app/src/python/

# Install piper_plus_g2p (standalone G2P package)
RUN uv pip install --system "/app/src/python/g2p"

# Install piper_train (for ort_utils)
RUN uv pip install --system "/app/src/python[inference]"

# Install wyoming protocol
RUN uv pip install --system "wyoming>=1.5"

# Pre-download NLTK data for g2p-en
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Create model directory
RUN mkdir -p /app/models

# Build-time smoke test
RUN python --version && \
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}')" && \
    python -c "import wyoming; print('wyoming installed')" && \
    python -c "import piper_train.ort_utils; print('ort_utils available')"

# Run as non-root
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /app/models
USER piper

EXPOSE 10200

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 10200)); s.close()" || exit 1

ENTRYPOINT ["python", "-m", "piper_wyoming"]
CMD ["--model", "/app/models/model.onnx", "--uri", "tcp://0.0.0.0:10200"]
