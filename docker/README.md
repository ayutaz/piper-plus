# Piper TTS Docker Environments

This directory contains Docker configurations for different Piper TTS environments.

## Available Environments

### 1. Python Training Environment (`python-train`)
- **Purpose**: Training new TTS models with Piper
- **Base**: NVIDIA CUDA 12.4 with cuDNN 8
- **Python**: 3.11.8
- **Includes**: PyTorch, TensorFlow, training utilities
- **Ports**: 6006 (TensorBoard), 8888 (Jupyter)

### 2. Python Inference Environment (`python-inference`)
- **Purpose**: Running inference with trained models
- **Base**: NVIDIA CUDA 12.4 runtime
- **Python**: 3.11.8
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

### Using Docker Compose

1. Build all images:
```bash
docker-compose build
```

2. Start specific service:
```bash
# Python training environment
docker-compose run --rm python-train

# Python inference API server
docker-compose up python-inference

# C++ development
docker-compose run --rm cpp-train

# C++ inference
docker-compose run --rm cpp-inference
```

### Using Individual Dockerfiles

1. Build an image:
```bash
cd docker/python-train
docker build -t piper-python-train .
```

2. Run container:
```bash
# With GPU support
docker run --gpus all -it -v $(pwd):/workspace piper-python-train

# Without GPU
docker run -it -v $(pwd):/workspace piper-python-train
```

## Training a Model

1. Start the training environment:
```bash
docker-compose run --rm python-train
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

## Running Inference

### Python Inference

1. Start the API server:
```bash
docker-compose up python-inference
```

2. Send requests:
```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello, world!", "speaker_id": 0}' \
  --output output.wav
```

### C++ Inference

1. Build the C++ binary first:
```bash
docker-compose run --rm cpp-train /workspace/docker/cpp-train/build.sh
```

2. Run inference:
```bash
docker-compose run --rm cpp-inference \
  piper --model /app/models/en_US-amy-low.onnx \
  --output_file /app/output/test.wav < input.txt
```

## Environment Variables

- `NVIDIA_VISIBLE_DEVICES`: GPU device selection (default: all)
- `WANDB_API_KEY`: Weights & Biases API key for training
- `MODEL_PATH`: Default model path for inference
- `BUILD_TYPE`: CMake build type (Release/Debug)
- `RUN_TESTS`: Run tests after build (0/1)
- `COVERAGE`: Generate coverage report (0/1)

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

To run without GPU, remove the `--gpus all` flag or `runtime: nvidia` from docker-compose.yml.

## Building for Production

1. Build optimized inference image:
```bash
docker build -t piper-inference:prod \
  --build-arg BUILD_TYPE=Release \
  -f docker/cpp-inference/Dockerfile .
```

2. Push to registry:
```bash
docker tag piper-inference:prod myregistry.com/piper-inference:latest
docker push myregistry.com/piper-inference:latest
```

## Troubleshooting

### CUDA Out of Memory
- Reduce batch size in training
- Use gradient accumulation
- Enable mixed precision training

### Permission Denied
- Ensure proper permissions on mounted volumes
- Run with appropriate user ID: `--user $(id -u):$(id -g)`

### Build Failures
- Check CUDA compatibility
- Verify all dependencies are available
- Review build logs in detail

## CI/CD Integration

GitHub Actions workflows are configured to:
- Build and test all Docker images
- Push to GitHub Container Registry
- Run automated tests in containers
- Deploy to production on tagged releases

See `.github/workflows/` for detailed configuration.