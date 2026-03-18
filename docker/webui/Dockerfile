# WebUI Docker image for piper-plus
FROM python:3.11-slim

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
RUN uv pip install --system "/app/src/python[inference,multilingual]" && \
    uv pip install --system -r /app/requirements_webui.txt

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
