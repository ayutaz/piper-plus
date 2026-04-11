#!/bin/bash
set -eu

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
ASSETS_DIR="$PROJECT_DIR/assets"
DICT_DIR="$ASSETS_DIR/dict"

echo "=== OpenJTalk Dictionary Preparation ==="
echo "Project directory: $PROJECT_DIR"

# Create directories
mkdir -p "$DICT_DIR"

# Dictionary download URL (same as used in main Piper project)
DICT_URL="https://sourceforge.net/projects/open-jtalk/files/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz/download"

echo "Downloading NAIST Japanese Dictionary..."
cd "$ASSETS_DIR"

# Download dictionary
if [ ! -f "dict.tar.gz" ]; then
    curl -L -o dict.tar.gz "$DICT_URL"
else
    echo "Dictionary archive already exists, skipping download"
fi

# Extract to dict directory
echo "Extracting dictionary files..."
tar -xzf dict.tar.gz -C "$DICT_DIR" --strip-components=1

# List extracted files
echo "Dictionary files:"
ls -la "$DICT_DIR/"

# Create metadata file
cat > "$ASSETS_DIR/assets.json" << EOF
{
  "dictionary": {
    "version": "1.11",
    "format": "utf-8",
    "files": [
      "char.bin",
      "matrix.bin",
      "sys.dic",
      "unk.dic",
      "left-id.def",
      "pos-id.def",
      "rewrite.def",
      "right-id.def"
    ]
  }
}
EOF

echo "Assets metadata created at: $ASSETS_DIR/assets.json"
echo "Dictionary preparation complete!"