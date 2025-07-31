# GPU Configuration Guide

This guide explains how to configure and use GPU acceleration in Piper TTS, including multi-GPU support.

## GPU Device Selection (v1.5.0+)

Piper now supports selecting specific GPU devices for inference, which is useful in multi-GPU environments.

### Command Line Usage

Use the `--gpu-device-id` parameter to select a specific GPU:

```bash
# Use default GPU (device 0)
echo "Hello world" | piper --model en_US-lessac-medium.onnx --use-cuda -f output.wav

# Use GPU device 1
echo "Hello world" | piper --model en_US-lessac-medium.onnx --use-cuda --gpu-device-id 1 -f output.wav

# Use GPU device 2 for Japanese synthesis
echo "こんにちは" | piper --model ja_JP-test-medium.onnx --use-cuda --gpu-device-id 2 -f output.wav
```

### Environment Variable

Set the `PIPER_GPU_DEVICE_ID` environment variable for persistent configuration:

```bash
# Linux/macOS
export PIPER_GPU_DEVICE_ID=1
echo "Hello world" | piper --model en_US-lessac-medium.onnx --use-cuda -f output.wav

# Windows (PowerShell)
$env:PIPER_GPU_DEVICE_ID = "1"
echo "Hello world" | piper --model en_US-lessac-medium.onnx --use-cuda -f output.wav

# Windows (Command Prompt)
set PIPER_GPU_DEVICE_ID=1
echo "Hello world" | piper --model en_US-lessac-medium.onnx --use-cuda -f output.wav
```

### Priority Order

When both CLI argument and environment variable are set, the CLI argument takes precedence:

1. `--gpu-device-id` command line argument (highest priority)
2. `PIPER_GPU_DEVICE_ID` environment variable
3. Default device 0 (if neither is specified)

## Checking Available GPUs

### Linux

```bash
# Using nvidia-smi
nvidia-smi -L

# Example output:
# GPU 0: NVIDIA GeForce RTX 3090 (UUID: GPU-abc123...)
# GPU 1: NVIDIA GeForce RTX 3080 (UUID: GPU-def456...)
```

### Windows

```powershell
# Using nvidia-smi
nvidia-smi -L

# Or using WMIC
wmic path win32_VideoController get name,DeviceID
```

### Python

```python
import piper

# Check CUDA availability
if piper.cuda_available():
    print("CUDA is available")
    # Device selection is handled via CLI or environment variable
```

## Multi-GPU Deployment

### Parallel Processing

Process multiple files using different GPUs:

```bash
# Process on GPU 0
piper --model en_US-lessac-medium.onnx --use-cuda --gpu-device-id 0 --input-file text1.txt -f output1.wav &

# Process on GPU 1
piper --model en_US-lessac-medium.onnx --use-cuda --gpu-device-id 1 --input-file text2.txt -f output2.wav &

# Wait for all processes
wait
```

### Docker with GPU

```dockerfile
# Dockerfile example
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

# Install Piper
RUN apt-get update && apt-get install -y wget
RUN wget https://github.com/rhasspy/piper/releases/download/v1.5.0/piper_linux_x86_64.tar.gz
RUN tar -xzf piper_linux_x86_64.tar.gz

# Set default GPU device
ENV PIPER_GPU_DEVICE_ID=0

# Run with specific GPU
CMD ["./piper", "--use-cuda", "--model", "model.onnx"]
```

Run with specific GPU:

```bash
# Use GPU 0
docker run --gpus '"device=0"' -e PIPER_GPU_DEVICE_ID=0 piper-gpu

# Use GPU 1
docker run --gpus '"device=1"' -e PIPER_GPU_DEVICE_ID=1 piper-gpu
```

## Performance Considerations

### GPU Memory Usage

Different models require different amounts of GPU memory:

- Small models: ~500MB
- Medium models: ~1-2GB
- Large models: ~3-4GB

### Benchmarking

Compare GPU performance:

```bash
# Benchmark on GPU 0
time echo "This is a test of GPU performance" | \
  piper --model en_US-lessac-medium.onnx --use-cuda --gpu-device-id 0 -f /dev/null

# Benchmark on GPU 1
time echo "This is a test of GPU performance" | \
  piper --model en_US-lessac-medium.onnx --use-cuda --gpu-device-id 1 -f /dev/null
```

## Troubleshooting

### Common Issues

1. **"Invalid GPU device ID" error**
   - Check available GPUs with `nvidia-smi -L`
   - Ensure the device ID exists (0-indexed)

2. **"CUDA out of memory" error**
   - Try a smaller model
   - Check GPU memory usage with `nvidia-smi`
   - Close other GPU-using applications

3. **"CUDA not available" error**
   - Ensure NVIDIA drivers are installed
   - Check CUDA installation
   - Verify Piper was built with CUDA support

### Debug Information

Enable debug logging to see GPU selection:

```bash
# Linux/macOS
export PIPER_LOG_LEVEL=DEBUG
piper --model model.onnx --use-cuda --gpu-device-id 1 "test"

# Look for:
# [DEBUG] Using CUDA execution provider with GPU device ID: 1
```

## Integration Examples

### Python Script with GPU Selection

```python
import os
import subprocess

def synthesize_with_gpu(text, model_path, gpu_id, output_file):
    """Synthesize text using specific GPU."""
    env = os.environ.copy()
    env['PIPER_GPU_DEVICE_ID'] = str(gpu_id)
    
    cmd = [
        'piper',
        '--model', model_path,
        '--use-cuda',
        '-f', output_file
    ]
    
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        env=env
    )
    process.communicate(text.encode())
    
# Use GPU 0 for English
synthesize_with_gpu(
    "Hello world",
    "en_US-lessac-medium.onnx",
    gpu_id=0,
    output_file="english.wav"
)

# Use GPU 1 for Japanese
synthesize_with_gpu(
    "こんにちは",
    "ja_JP-test-medium.onnx", 
    gpu_id=1,
    output_file="japanese.wav"
)
```

### Batch Processing Script

```bash
#!/bin/bash
# batch_synthesize.sh - Process files across multiple GPUs

# Define GPU assignments
declare -A gpu_assignments=(
    ["en_US"]=0
    ["ja_JP"]=1
    ["de_DE"]=2
    ["fr_FR"]=3
)

# Process files based on language
for file in texts/*.txt; do
    basename=$(basename "$file" .txt)
    lang=$(echo "$basename" | cut -d'-' -f1-2)
    gpu_id=${gpu_assignments[$lang]:-0}
    
    echo "Processing $file on GPU $gpu_id"
    piper --model "models/${lang}-medium.onnx" \
          --use-cuda \
          --gpu-device-id "$gpu_id" \
          --input-file "$file" \
          -f "output/${basename}.wav" &
done

wait
echo "All files processed"
```

## Best Practices

1. **Load Balancing**: Distribute work evenly across available GPUs
2. **Model Placement**: Keep frequently used models on faster GPUs
3. **Memory Management**: Monitor GPU memory usage to avoid OOM errors
4. **Error Handling**: Implement fallback to CPU if GPU fails

## Related Documentation

- [CLI Enhancements](CLI_ENHANCEMENTS.md) - Other command line features
- [Multi-GPU Training Guide](MULTI_GPU_TRAINING.md) - For model training
- [Performance Optimization](performance-optimization.md) - General optimization tips