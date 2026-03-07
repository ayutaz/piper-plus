# Python Inference Environment for Piper TTS (CPU, GPL-free)
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# System dependencies (libsndfile for soundfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy source tree for piper_train install
# setup.py reads ../../VERSION relative to src/python/
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python/ /app/src/python/

# Install piper_train with inference extras
RUN uv pip install --system "/app/src/python[inference]"

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
    python -c "import onnxruntime as ort; print(f'ONNX Runtime: {ort.__version__}')" && \
    python -c "import piper_train; print('piper_train installed')"

CMD ["echo", "Container started successfully"]
