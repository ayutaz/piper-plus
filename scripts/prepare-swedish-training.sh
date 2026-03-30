#!/bin/bash
# Prepare Swedish TTS training on DANNESBURK
# Prerequisites: conda env piper (Python 3.11), CUDA/RTX 4080
set -e

WORKDIR=~/piper-training/swedish
mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "=== Step 1: Clone piper-plus with Swedish support ==="
if [ ! -d piper-plus ]; then
    git clone https://github.com/yeager/piper-plus.git
    cd piper-plus
    git checkout dev
else
    cd piper-plus
    git pull origin dev
fi

echo "=== Step 2: Install dependencies ==="
pip install -e ".[train]"
cd src/python && bash build_monotonic_align.sh && cd ../..
pip install espeak-ng  # also need: sudo apt-get install espeak-ng

echo "=== Step 3: Download NST Swedish TTS dataset ==="
cd "$WORKDIR"
if [ ! -d nst-swedish ]; then
    # Option A: From HuggingFace
    pip install datasets
    python3 -c "
from datasets import load_dataset
ds = load_dataset('jimregan/nst_swedish_tts', split='train')
print(f'Dataset loaded: {len(ds)} samples')
ds.save_to_disk('nst-swedish')
"
fi

echo "=== Step 4: Download KBLab pretrained checkpoint ==="
cd "$WORKDIR"
if [ ! -d kblab-checkpoint ]; then
    git clone https://huggingface.co/KBLab/piper-tts-nst-swedish kblab-checkpoint
fi

echo "=== Step 5: Prepare dataset for piper-plus ==="
cd "$WORKDIR/piper-plus"
# Preprocess with our Swedish phonemizer
python3 -m piper_train.preprocess \
    --language sv \
    --input-dir "$WORKDIR/nst-swedish" \
    --output-dir "$WORKDIR/preprocessed" \
    --sample-rate 22050

echo "=== Step 6: Start training ==="
echo "Fine-tune from KBLab checkpoint for best results:"
echo ""
echo "python3 -m piper_train fit \\"
echo "  --config configs/medium.yaml \\"
echo "  --data.root_dir $WORKDIR/preprocessed \\"
echo "  --trainer.max_epochs 1000 \\"
echo "  --trainer.accelerator gpu \\"
echo "  --trainer.devices 1 \\"
echo "  --model.learning_rate 1e-4"
echo ""
echo "Or train from scratch:"
echo ""
echo "python3 -m piper_train fit \\"
echo "  --config configs/medium.yaml \\"
echo "  --data.root_dir $WORKDIR/preprocessed \\"
echo "  --trainer.max_epochs 5000 \\"
echo "  --trainer.accelerator gpu \\"
echo "  --trainer.devices 1"
echo ""
echo "=== Setup complete! ==="
