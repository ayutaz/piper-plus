# WebUI Docker image for piper-plus
FROM python:3.11-slim-trixie

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install --no-cache-dir uv

# Set working directory
WORKDIR /app

# Copy source for piper_train installation
COPY VERSION /app/VERSION
COPY pyproject.toml /app/pyproject.toml
COPY src/python /app/src/python
COPY src/python_run/requirements_webui.txt /app/requirements_webui.txt

# Install piper_train with inference extras + gradio + multilingual
RUN uv pip install --system "/app/src/python[inference]" && \
    uv pip install --system -r /app/requirements_webui.txt

# Download NLTK data required by g2p-en (English phonemizer)
# Use a shared path so data is accessible after USER switch to non-root
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "import nltk; nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Copy WebUI application and entrypoint
COPY docker/webui/app.py /app/app.py
COPY docker/webui/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Create models directory
RUN mkdir -p /models /output

# Expose Gradio default port
EXPOSE 7860

# Set environment variables
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Run as non-root user for security
RUN useradd -m -u 1000 piper && \
    chown -R piper:piper /models /output /app
USER piper

ENTRYPOINT ["/app/entrypoint.sh"]
