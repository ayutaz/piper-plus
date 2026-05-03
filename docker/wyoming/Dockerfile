# Wyoming Protocol TTS adapter for piper-plus
# CPU-only, multi-stage build for Home Assistant integration
#
# Build (from project root):
#   docker build -t wyoming-piper-plus -f docker/wyoming/Dockerfile .
#
# Run:
#   docker run -p 10200:10200 wyoming-piper-plus

# ============================================================
# Stage 1: Builder -- compile C extensions (pyopenjtalk, etc.)
# ============================================================
FROM python:3.11-slim-trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies for pyopenjtalk (cmake, g++) and audio libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    g++ \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

# Pin uv to a known-good major version (workspace editable handling is uv version-sensitive)
RUN pip install --no-cache-dir "uv>=0.9,<1"

WORKDIR /build

# Copy source tree
COPY VERSION /build/VERSION
COPY pyproject.toml /build/pyproject.toml
COPY src/python/ /build/src/python/

# Build wheels first to guarantee non-editable installs.
# `uv pip install /path[extras]` can resolve to .pth-style editable links when uv
# detects the workspace pyproject.toml (root pyproject.toml has
# `[tool.uv.sources] piper-plus-g2p = { workspace = true, editable = true }`).
# Editable installs would leave `/build/...` references in site-packages, which
# break in stage-2 because `/build/` is not copied to the runtime image.
# Building wheels first sidesteps this entirely (archive_info instead of dir_info
# in dist-info/direct_url.json).
RUN uv build /build/src/python/g2p --wheel --out-dir /tmp/wheels/ \
 && uv build /build/src/python      --wheel --out-dir /tmp/wheels/

# Install piper_plus_g2p (standalone G2P -- all languages)
RUN uv pip install --system "$(ls /tmp/wheels/piper_plus_g2p-*.whl)[all]"

# Install piper_train with inference extras (onnxruntime CPU, soundfile, etc.)
RUN uv pip install --system "$(ls /tmp/wheels/piper_train-*.whl)[inference]"

# Install wyoming protocol library.
# >=1.5.1 added Artifact.version field; 1.5.0 raises TypeError on
# `TtsVoice(version=...)`.  We follow the rhasspy/wyoming-piper upstream pin
# (`wyoming>=1.7,<2`) for HA 2026.x compatibility.
RUN uv pip install --system "wyoming>=1.7,<2"

# Install huggingface-hub for model auto-download
RUN uv pip install --system "huggingface-hub>=0.22"

# Pre-download NLTK data for g2p-en (English phonemizer)
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "\
import nltk; \
nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); \
nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); \
nltk.download('cmudict', download_dir='/usr/share/nltk_data')"


# ============================================================
# Stage 2: Runtime -- minimal image
# ============================================================
FROM python:3.11-slim-trixie

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Runtime-only system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy NLTK data
COPY --from=builder /usr/share/nltk_data /usr/share/nltk_data
ENV NLTK_DATA=/usr/share/nltk_data

# Copy piper_plus and piper_wyoming source (not included in piper_train package)
COPY src/python/piper_plus/ /app/piper_plus/
COPY src/python/piper_wyoming/ /app/piper_wyoming/

# Add /app to PYTHONPATH so piper_plus and piper_wyoming are importable
ENV PYTHONPATH=/app

# Create directories
RUN mkdir -p /app/models /home/piper/.cache/piper-plus/models

# Environment variables for configuration
ENV PIPER_MODEL=tsukuyomi
ENV PIPER_LANGUAGE=ja
ENV PIPER_SPEAKER_ID=0
ENV PIPER_NOISE_SCALE=0.667
ENV PIPER_LENGTH_SCALE=1.0
ENV PIPER_NOISE_W=0.8
ENV PIPER_DEVICE=cpu
ENV PIPER_PORT=10200

# Build-time smoke test
RUN python --version && \
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}')" && \
    python -c "import wyoming; print('wyoming installed')" && \
    python -c "import piper_plus; print('piper_plus importable')" && \
    python -c "import piper_wyoming; print('piper_wyoming importable')" && \
    python -c "import piper_plus_g2p; print('piper_plus_g2p importable')" && \
    python -c "from huggingface_hub import hf_hub_download; print('huggingface_hub available')"

# Run as non-root user
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /app/models /home/piper
USER piper

# Wyoming standard port
EXPOSE 10200

# Healthcheck: TCP connection to the Wyoming server
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 10200)); s.close()" || exit 1

ENTRYPOINT ["python", "-m", "piper_wyoming"]
CMD ["--model", "tsukuyomi", "--uri", "tcp://0.0.0.0:10200"]
