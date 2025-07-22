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
