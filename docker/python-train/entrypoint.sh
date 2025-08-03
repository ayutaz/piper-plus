#!/bin/bash
set -e

# Activate virtual environment if exists
if [ -d "/workspace/venv" ]; then
    source /workspace/venv/bin/activate
fi

# Set up CUDA paths
export CUDA_HOME=/usr/local/cuda
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# Check CUDA availability
echo "=== CUDA Information ==="
nvidia-smi
echo ""
echo "CUDA Version: $(nvcc --version | grep release | awk '{print $5}' | sed 's/,//')"
echo ""

# Check PyTorch CUDA availability
python -c "import torch; print(f'PyTorch version: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'CUDA device count: {torch.cuda.device_count()}')"
echo ""

# Execute command
exec "$@"