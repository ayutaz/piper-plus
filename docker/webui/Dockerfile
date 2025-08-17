# WebUI Docker image for Piper TTS
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY src/python_run/requirements.txt /tmp/requirements.txt
COPY src/python_run/requirements_webui.txt /tmp/requirements_webui.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements_webui.txt

# Copy the application code
COPY src/python_run /app/python_run

# Create models directory
RUN mkdir -p /models

# Expose Gradio default port
EXPOSE 7860

# Set environment variables
ENV PYTHONPATH=/app
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Run the WebUI
CMD ["python", "-m", "python_run.piper.webui", "--data-dir", "/models", "--host", "0.0.0.0"]