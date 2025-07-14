#!/bin/bash
# Script to preprocess multilingual datasets for VITS training

set -e  # Exit on error

# Default values
OUTPUT_DIR="multilingual_dataset"
SAMPLE_RATE=22050
MAX_WORKERS=4
DATASET_FORMAT="ljspeech"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Function to check if directory exists
check_directory() {
    if [ ! -d "$1" ]; then
        print_error "Directory not found: $1"
        return 1
    fi
    return 0
}

# Function to show usage
usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Preprocess multilingual datasets for VITS training.

OPTIONS:
    -o, --output-dir DIR        Output directory (default: multilingual_dataset)
    -c, --config FILE          Configuration file with dataset paths
    -j, --japanese-dir DIR     Japanese dataset directory (LJSpeech format)
    -e, --english-dir DIR      English dataset directory (LJSpeech format)
    -s, --sample-rate RATE     Sample rate (default: 22050)
    -w, --workers NUM          Number of workers (default: 4)
    -f, --format FORMAT        Dataset format: ljspeech or mycroft (default: ljspeech)
    -h, --help                 Show this help message

EXAMPLES:
    # Using config file
    $0 -c config/multilingual_dataset_config.json -o my_dataset

    # Using directory arguments
    $0 -j /path/to/japanese -e /path/to/english -o my_dataset

    # With custom settings
    $0 -c config.json -o my_dataset -s 16000 -w 8

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -o|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -c|--config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        -j|--japanese-dir)
            JAPANESE_DIR="$2"
            shift 2
            ;;
        -e|--english-dir)
            ENGLISH_DIR="$2"
            shift 2
            ;;
        -s|--sample-rate)
            SAMPLE_RATE="$2"
            shift 2
            ;;
        -w|--workers)
            MAX_WORKERS="$2"
            shift 2
            ;;
        -f|--format)
            DATASET_FORMAT="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Check if we have dataset specifications
if [ -z "$CONFIG_FILE" ] && [ -z "$JAPANESE_DIR" ] && [ -z "$ENGLISH_DIR" ]; then
    print_error "No datasets specified. Use -c for config file or -j/-e for directories."
    usage
    exit 1
fi

# Print configuration
print_info "Multilingual Dataset Preprocessing"
print_info "================================="
print_info "Output directory: $OUTPUT_DIR"
print_info "Sample rate: $SAMPLE_RATE Hz"
print_info "Workers: $MAX_WORKERS"
print_info "Format: $DATASET_FORMAT"

# Build command
CMD="python scripts/preprocess_multilingual_dataset.py"
CMD="$CMD --output-dir $OUTPUT_DIR"
CMD="$CMD --sample-rate $SAMPLE_RATE"
CMD="$CMD --max-workers $MAX_WORKERS"
CMD="$CMD --dataset-format $DATASET_FORMAT"

if [ ! -z "$CONFIG_FILE" ]; then
    if [ ! -f "$CONFIG_FILE" ]; then
        print_error "Config file not found: $CONFIG_FILE"
        exit 1
    fi
    print_info "Using config file: $CONFIG_FILE"
    CMD="$CMD --config-file $CONFIG_FILE"
else
    if [ ! -z "$JAPANESE_DIR" ]; then
        check_directory "$JAPANESE_DIR" || exit 1
        print_info "Japanese dataset: $JAPANESE_DIR"
        CMD="$CMD --japanese-dir $JAPANESE_DIR"
    fi
    
    if [ ! -z "$ENGLISH_DIR" ]; then
        check_directory "$ENGLISH_DIR" || exit 1
        print_info "English dataset: $ENGLISH_DIR"
        CMD="$CMD --english-dir $ENGLISH_DIR"
    fi
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Run preprocessing
print_info ""
print_info "Starting preprocessing..."
print_info "Command: $CMD"
print_info ""

# Execute the command
if $CMD; then
    print_info ""
    print_info "Preprocessing completed successfully!"
    print_info "Dataset created at: $OUTPUT_DIR"
    
    # Show dataset statistics if available
    if [ -f "$OUTPUT_DIR/config.json" ]; then
        print_info ""
        print_info "Dataset Statistics:"
        python -c "
import json
with open('$OUTPUT_DIR/config.json') as f:
    config = json.load(f)
    print(f'  Languages: {config.get(\"languages\", [])}')
    print(f'  Speakers: {config.get(\"num_speakers\", 0)}')
    counts = config.get('utterance_counts', {})
    print(f'  Training utterances: {counts.get(\"train\", 0)}')
    print(f'  Validation utterances: {counts.get(\"validation\", 0)}')
"
    fi
    
    print_info ""
    print_info "Next steps:"
    print_info "1. Verify the dataset:"
    print_info "   ls -la $OUTPUT_DIR/"
    print_info ""
    print_info "2. Train the model:"
    print_info "   python -m piper_train.train_multilingual \\"
    print_info "     --dataset-dir $OUTPUT_DIR \\"
    print_info "     --max_epochs 1000 \\"
    print_info "     --batch-size 16"
else
    print_error "Preprocessing failed!"
    exit 1
fi