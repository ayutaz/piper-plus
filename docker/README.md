# Piper TTS Docker Environments

This directory contains Docker configurations for different Piper TTS environments.

## Available Environments

### 1. Python Training Environment (`python-train`)
- **Purpose**: Training new TTS models with Piper
- **Base**: NVIDIA CUDA 12.1 with cuDNN 8
- **Python**: 3.11
- **Includes**: PyTorch, TensorFlow, training utilities
- **Ports**: 6006 (TensorBoard), 8888 (Jupyter)

### 2. Python Inference Environment (`python-inference`)
- **Purpose**: Running inference with trained models
- **Base**: NVIDIA CUDA 12.4 runtime
- **Python**: 3.11
- **Includes**: Minimal dependencies for inference
- **Ports**: 8000 (API server)

### 3. C++ Development Environment (`cpp-train`)
- **Purpose**: Building and developing Piper C++ components
- **Base**: NVIDIA CUDA 12.4 with development tools
- **Includes**: CMake, Ninja, compilers, debugging tools
- **Features**: ccache for faster rebuilds

### 4. C++ Inference Environment (`cpp-inference`)
- **Purpose**: Running Piper C++ binary for inference
- **Base**: NVIDIA CUDA 12.4 runtime (minimal)
- **Includes**: Runtime libraries only
- **Size**: Optimized for production deployment

## Quick Start

### Building Docker Images

Build images from the project root directory:

```bash
# Python training environment
docker build -t piper-train -f docker/python-train/Dockerfile .

# Python inference environment
docker build -t piper-inference -f docker/python-inference/Dockerfile .

# C++ development environment
docker build -t piper-cpp-dev -f docker/cpp-train/Dockerfile .

# C++ inference environment (requires piper binary)
docker build -t piper-cpp -f docker/cpp-inference/Dockerfile .
```

### Running Containers

#### Python Training Environment
```bash
# With GPU support
docker run -it --gpus all \
  -v $(pwd):/workspace \
  -p 6006:6006 \
  -p 8888:8888 \
  piper-train

# Without GPU
docker run -it \
  -v $(pwd):/workspace \
  -p 6006:6006 \
  -p 8888:8888 \
  piper-train
```

#### Python Inference Environment
```bash
# Start API server with GPU
docker run -it --gpus all \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  -p 8000:8000 \
  piper-inference \
  python inference.py --server --model /app/models/en_US-amy-low.onnx

# Command-line inference
docker run --gpus all \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  piper-inference \
  python inference.py --model /app/models/en_US-amy-low.onnx --text "Hello world"
```

#### C++ Development Environment
```bash
# Interactive development
docker run -it --gpus all \
  -v $(pwd):/workspace \
  -v piper-ccache:/workspace/.ccache \
  piper-cpp-dev

# Build Piper
docker run --rm \
  -v $(pwd):/workspace \
  -v piper-ccache:/workspace/.ccache \
  piper-cpp-dev \
  /workspace/docker/cpp-train/build.sh
```

#### C++ Inference Environment
```bash
# Run inference
docker run --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/build/piper:/usr/local/bin/piper:ro \
  piper-cpp \
  piper --model /app/models/en_US-amy-low.onnx --output_file /app/output/test.wav < input.txt
```

## Training a Model

1. Start the training environment:
```bash
docker run -it --gpus all \
  -v $(pwd):/workspace \
  -v $(pwd)/datasets:/workspace/datasets \
  -v $(pwd)/checkpoints:/workspace/checkpoints \
  -p 6006:6006 \
  piper-train
```

2. Inside the container:
```bash
# Prepare dataset
python -m piper_train.preprocess \
  --dataset-dir /workspace/datasets/my_dataset \
  --output-dir /workspace/datasets/processed

# Start training
python -m piper_train \
  --dataset-dir /workspace/datasets/processed \
  --output-dir /workspace/checkpoints \
  --quality medium \
  --validation-split 0.1 \
  --batch-size 16
```

3. Monitor with TensorBoard:
```bash
tensorboard --logdir /workspace/logs --host 0.0.0.0
```
Access TensorBoard at http://localhost:6006

## Running Inference

### Python Inference

1. Start the API server:
```bash
docker run -d --gpus all \
  --name piper-api \
  -v $(pwd)/models:/app/models:ro \
  -p 8000:8000 \
  piper-inference \
  python inference.py --server --model /app/models/en_US-amy-low.onnx
```

2. Send requests:
```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!", "speaker_id": 0}' \
  --output output.wav
```

3. Stop the server:
```bash
docker stop piper-api
docker rm piper-api
```

### C++ Inference

1. Build the C++ binary first:
```bash
docker run --rm \
  -v $(pwd):/workspace \
  -v piper-ccache:/workspace/.ccache \
  piper-cpp-dev \
  /workspace/docker/cpp-train/build.sh
```

2. Run inference:
```bash
echo "Hello, world!" | docker run -i --rm \
  -v $(pwd)/models:/app/models:ro \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/build/piper:/usr/local/bin/piper:ro \
  piper-cpp \
  piper --model /app/models/en_US-amy-low.onnx --output_file /app/output/test.wav
```

## Environment Variables

- `NVIDIA_VISIBLE_DEVICES`: GPU device selection (default: all)
- `WANDB_API_KEY`: Weights & Biases API key for training
- `MODEL_PATH`: Default model path for inference
- `BUILD_TYPE`: CMake build type (Release/Debug)
- `RUN_TESTS`: Run tests after build (0/1)
- `COVERAGE`: Generate coverage report (0/1)

Example:
```bash
docker run -it --gpus all \
  -e WANDB_API_KEY=your_api_key_here \
  -e NVIDIA_VISIBLE_DEVICES=0,1 \
  -v $(pwd):/workspace \
  piper-train
```

## Volume Mounts

### Training Environments
- `/workspace`: Main working directory
- `/workspace/datasets`: Training datasets
- `/workspace/checkpoints`: Model checkpoints
- `/workspace/logs`: Training logs

### Inference Environments
- `/app/models`: Model files (read-only)
- `/app/output`: Generated audio files

## GPU Support

All environments support NVIDIA GPUs. Requirements:
- NVIDIA Driver >= 525.60.13
- NVIDIA Container Toolkit
- Docker >= 19.03

To run without GPU:
- Remove the `--gpus all` flag from docker run commands
- The containers will automatically fall back to CPU mode

## Building for Production

1. Build optimized inference image:
```bash
# Build multi-stage optimized image
docker build -t piper-inference:prod \
  --build-arg BUILD_TYPE=Release \
  -f docker/cpp-inference/Dockerfile .
```

2. Create minimal runtime image:
```bash
# Export only the binary
docker create --name temp piper-cpp-dev
docker cp temp:/workspace/build/piper ./piper
docker rm temp

# Build minimal image
docker build -t piper-minimal -f - . <<EOF
FROM debian:bullseye-slim
RUN apt-get update && apt-get install -y libgomp1 libsndfile1 && rm -rf /var/lib/apt/lists/*
COPY piper /usr/local/bin/
ENTRYPOINT ["piper"]
EOF
```

3. Push to registry:
```bash
docker tag piper-inference:prod myregistry.com/piper-inference:latest
docker push myregistry.com/piper-inference:latest
```

## Troubleshooting

### CUDA Out of Memory
- Reduce batch size in training
- Use gradient accumulation
- Enable mixed precision training:
  ```bash
  python -m piper_train --batch-size 8 --accumulate-grad-batches 4 --precision 16
  ```

### Permission Denied
- Ensure proper permissions on mounted volumes
- Run with appropriate user ID:
  ```bash
  docker run -it --user $(id -u):$(id -g) -v $(pwd):/workspace piper-train
  ```

### Build Failures
- Check CUDA compatibility
- Verify all dependencies are available
- Review build logs in detail:
  ```bash
  docker build --no-cache -t piper-cpp-dev -f docker/cpp-train/Dockerfile . 2>&1 | tee build.log
  ```

### Container Networking
- Use host network for better performance:
  ```bash
  docker run --network host piper-inference
  ```

## Docker Volume for ccache

Create a named volume for ccache to speed up rebuilds:
```bash
# Create volume
docker volume create piper-ccache

# Use in builds
docker run -v piper-ccache:/workspace/.ccache piper-cpp-dev

# Clean ccache if needed
docker run -v piper-ccache:/workspace/.ccache piper-cpp-dev ccache -C
```

## CI/CD Integration

GitHub Actions workflows are configured to:
- Build and test all Docker images
- Push to GitHub Container Registry
- Run automated tests in containers
- Deploy to production on tagged releases

See `.github/workflows/` for detailed configuration.

## Security Notes

- Always use read-only mounts (`:ro`) for model directories in production
- Don't run containers as root in production
- Use specific image tags instead of `latest` in production
- Regularly update base images for security patches