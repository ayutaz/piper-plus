#!/bin/bash
# Prepare NAIST-JDIC dictionary for web distribution

echo "Preparing NAIST-JDIC dictionary for web..."

# Check if dictionary exists
if [ ! -d "dict/naist-jdic" ]; then
    echo "Error: NAIST-JDIC dictionary not found. Run setup_naist_jdic.sh first."
    exit 1
fi

cd dict/naist-jdic

# Method 1: Create compressed archive
echo "Creating compressed dictionary archive..."
tar -czf ../naist-jdic.tar.gz *.dic *.bin *.def dicrc
echo "Created naist-jdic.tar.gz"

# Method 2: Create individual gzipped files for CDN
echo "Creating individual compressed files..."
for file in *.dic *.bin *.def dicrc; do
    if [ -f "$file" ]; then
        gzip -9 -c "$file" > "../${file}.gz"
        echo "Compressed $file -> ${file}.gz"
    fi
done

# Method 3: Create a single concatenated dictionary file
echo "Creating concatenated dictionary..."
cat char.bin matrix.bin sys.dic unk.dic > ../naist-jdic-combined.dat
gzip -9 ../naist-jdic-combined.dat
echo "Created naist-jdic-combined.dat.gz"

# Show sizes
echo ""
echo "File sizes:"
ls -lh ../*.gz ../*.tar.gz 2>/dev/null | grep -E "(gz|tar)"

# Method 4: Split large files for easier download
echo ""
echo "Splitting sys.dic for chunked download..."
split -b 10M sys.dic ../sys.dic.chunk.
echo "Created sys.dic chunks"

# Create manifest file
cat > ../dict-manifest.json << EOF
{
  "version": "1.0",
  "files": [
    {"name": "char.bin", "size": $(stat -f%z char.bin 2>/dev/null || stat -c%s char.bin), "compressed": "char.bin.gz"},
    {"name": "matrix.bin", "size": $(stat -f%z matrix.bin 2>/dev/null || stat -c%s matrix.bin), "compressed": "matrix.bin.gz"},
    {"name": "sys.dic", "size": $(stat -f%z sys.dic 2>/dev/null || stat -c%s sys.dic), "compressed": "sys.dic.gz"},
    {"name": "unk.dic", "size": $(stat -f%z unk.dic 2>/dev/null || stat -c%s unk.dic), "compressed": "unk.dic.gz"},
    {"name": "dicrc", "size": $(stat -f%z dicrc 2>/dev/null || stat -c%s dicrc), "compressed": "dicrc.gz"},
    {"name": "left-id.def", "size": $(stat -f%z left-id.def 2>/dev/null || stat -c%s left-id.def), "compressed": "left-id.def.gz"},
    {"name": "right-id.def", "size": $(stat -f%z right-id.def 2>/dev/null || stat -c%s right-id.def), "compressed": "right-id.def.gz"},
    {"name": "pos-id.def", "size": $(stat -f%z pos-id.def 2>/dev/null || stat -c%s pos-id.def), "compressed": "pos-id.def.gz"},
    {"name": "rewrite.def", "size": $(stat -f%z rewrite.def 2>/dev/null || stat -c%s rewrite.def), "compressed": "rewrite.def.gz"}
  ],
  "totalSize": $(du -sb . 2>/dev/null | cut -f1 || du -s . | cut -f1),
  "compressedSize": $(ls -l ../*.gz | awk '{s+=$5} END {print s}')
}
EOF

echo ""
echo "Dictionary preparation complete!"
echo "Manifest created at: dict-manifest.json"