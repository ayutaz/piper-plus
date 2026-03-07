# WebUI Docker image for Piper TTS
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy source for piper_train installation
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python /app/src/python

# Install piper_train and dependencies
RUN cd /app/src/python && pip install --no-cache-dir . && \
    pip install --no-cache-dir \
    "onnxruntime>=1.17" \
    "pyopenjtalk-plus" \
    "g2p-en>=2.1.0" \
    "gradio>=4.0" \
    "soundfile>=0.12"

# Copy WebUI application
COPY docker/webui/app.py /app/app.py

# Create models directory
RUN mkdir -p /models /output

# Expose Gradio default port
EXPOSE 7860

# Set environment variables
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Run the WebUI
CMD ["python", "/app/app.py", "--model-dir", "/models", "--output-dir", "/output"]
