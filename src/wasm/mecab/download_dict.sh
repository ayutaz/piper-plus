#!/bin/bash
# Download and prepare mecab-naist-jdic dictionary for WebAssembly integration

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Configuration
DICT_VERSION="1.11"
DICT_NAME="open_jtalk_dic_utf_8-${DICT_VERSION}"
DOWNLOAD_URL="https://sourceforge.net/projects/open-jtalk/files/Dictionary/open_jtalk_dic-${DICT_VERSION}/${DICT_NAME}.tar.gz"
DICT_DIR="dict"
NAIST_JDIC_DIR="${DICT_DIR}/naist-jdic"
TEMP_DIR="temp_dict_download"

echo "=== MeCab NAIST-JDIC Dictionary Download Script ==="
echo "Dictionary version: ${DICT_VERSION}"
echo ""

# Create directories
echo "Creating directories..."
mkdir -p "${DICT_DIR}"
mkdir -p "${NAIST_JDIC_DIR}"
mkdir -p "${TEMP_DIR}"

# Download dictionary
echo "Downloading dictionary from OpenJTalk..."
if [ ! -f "${TEMP_DIR}/${DICT_NAME}.tar.gz" ]; then
    echo "Downloading ${DICT_NAME}.tar.gz..."
    curl -L -o "${TEMP_DIR}/${DICT_NAME}.tar.gz" "${DOWNLOAD_URL}"
    echo "Download complete!"
else
    echo "Dictionary archive already exists, skipping download."
fi

# Extract dictionary
echo "Extracting dictionary..."
cd "${TEMP_DIR}"
tar -xzf "${DICT_NAME}.tar.gz"
cd ..

# Copy dictionary files to target directory
echo "Copying dictionary files..."
cp -r "${TEMP_DIR}/${DICT_NAME}"/* "${NAIST_JDIC_DIR}/"

# List the contents to verify
echo ""
echo "Dictionary files extracted to ${NAIST_JDIC_DIR}:"
ls -la "${NAIST_JDIC_DIR}" | head -20
echo ""

# Create a configuration file for the dictionary
echo "Creating dictionary configuration..."
cat > "${NAIST_JDIC_DIR}/dicrc" << EOF
; Configuration file for MeCab with NAIST-JDIC
cost-factor = 700
bos-feature = BOS/EOS,*,*,*,*,*,*,*,*
eval-size = 4
unk-eval-size = 2
EOF

# Create mecabrc configuration for NAIST-JDIC
cat > "${DICT_DIR}/mecabrc-naist-jdic" << EOF
; Configuration file for MeCab WebAssembly with NAIST-JDIC
dicdir = /dict/naist-jdic
userdic = 
; output-format-type = wakati
; input-buffer-size = 8192
; node-format = %m\t%H\n
; bos-format = 
; eos-format = EOS\n
; unk-format = %m\t%H\n
; unk-feature = UNKNOWN
EOF

# Create a preparation script for the compression tool
cat > "${DICT_DIR}/prepare_for_compression.sh" << 'EOF'
#!/bin/bash
# Prepare NAIST-JDIC dictionary files for compression tool

set -e

DICT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAIST_JDIC_DIR="${DICT_DIR}/naist-jdic"
PREPARED_DIR="${DICT_DIR}/naist-jdic-prepared"

echo "Preparing NAIST-JDIC dictionary for compression..."

# Create prepared directory
rm -rf "${PREPARED_DIR}"
mkdir -p "${PREPARED_DIR}"

# Copy essential files
echo "Copying essential dictionary files..."
cp "${NAIST_JDIC_DIR}/char.def" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/unk.def" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/dicrc" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/left-id.def" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/right-id.def" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/rewrite.def" "${PREPARED_DIR}/"
cp "${NAIST_JDIC_DIR}/pos-id.def" "${PREPARED_DIR}/"

# Combine all .csv files into a single dictionary file
echo "Combining CSV files..."
cat "${NAIST_JDIC_DIR}"/*.csv > "${PREPARED_DIR}/dict.csv"

# Create matrix files list
echo "Creating matrix files list..."
ls "${NAIST_JDIC_DIR}"/matrix.def* > "${PREPARED_DIR}/matrix_files.txt" 2>/dev/null || true

# Copy matrix files
echo "Copying matrix files..."
cp "${NAIST_JDIC_DIR}"/matrix.def* "${PREPARED_DIR}/" 2>/dev/null || true

echo ""
echo "Dictionary prepared in: ${PREPARED_DIR}"
echo "Files:"
ls -lh "${PREPARED_DIR}"

echo ""
echo "Next steps:"
echo "1. Use the dictionary compression tool on these files"
echo "2. The compressed output can be loaded in WebAssembly"
EOF

chmod +x "${DICT_DIR}/prepare_for_compression.sh"

# Clean up temporary files
echo "Cleaning up temporary files..."
rm -rf "${TEMP_DIR}"

echo ""
echo "=== Download Complete ==="
echo ""
echo "Dictionary downloaded to: ${NAIST_JDIC_DIR}"
echo "Configuration file: ${DICT_DIR}/mecabrc-naist-jdic"
echo ""
echo "To prepare the dictionary for compression, run:"
echo "  cd ${DICT_DIR} && ./prepare_for_compression.sh"
echo ""
echo "Then use the dictionary compression tool:"
echo "  ../../build-tools/dict_compressor -i naist-jdic-prepared -o naist-jdic.compressed"