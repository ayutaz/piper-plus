# MeCab Dictionary Setup for WebAssembly

This directory contains dictionary files for MeCab WebAssembly integration.

## Quick Start

To download and set up the NAIST-JDIC dictionary:

```bash
cd .. # Go to mecab directory
./setup_naist_jdic.sh
```

This will:
1. Download the open_jtalk_dic_utf_8-1.11 dictionary
2. Extract and prepare the files
3. Build the compression tool
4. Create compressed dictionary for WebAssembly

## Directory Structure

```
dict/
├── README.md                   # This file
├── mecabrc                     # Default configuration
├── mecabrc-naist-jdic         # NAIST-JDIC specific configuration  
├── minimal/                    # Minimal test dictionary
│   ├── char.def
│   ├── dicrc
│   ├── dict.txt
│   └── unk.def
├── naist-jdic/                # Full NAIST-JDIC dictionary (after download)
│   ├── char.def
│   ├── unk.def
│   ├── dicrc
│   ├── *.csv                  # Dictionary entries
│   └── ...
├── naist-jdic-prepared/       # Prepared for compression
│   └── dict.csv              # Combined dictionary
└── naist-jdic.compressed      # Final compressed dictionary
```

## Manual Download

If you need to download the dictionary manually:

1. Download from OpenJTalk SourceForge:
   ```
   https://sourceforge.net/projects/open-jtalk/files/Dictionary/open_jtalk_dic-1.11/open_jtalk_dic_utf_8-1.11.tar.gz
   ```

2. Extract to `naist-jdic/` directory:
   ```bash
   tar -xzf open_jtalk_dic_utf_8-1.11.tar.gz
   cp -r open_jtalk_dic_utf_8-1.11/* naist-jdic/
   ```

3. Prepare for compression:
   ```bash
   ./prepare_for_compression.sh
   ```

4. Compress using the tool:
   ```bash
   ../../build-tools/dict_compressor -i naist-jdic-prepared -o naist-jdic.compressed
   ```

## Dictionary Files

### Minimal Dictionary
- For testing and development
- Very small vocabulary
- Fast loading

### NAIST-JDIC Dictionary
- Full Japanese dictionary
- Based on NAIST Japanese Dictionary
- Used by OpenJTalk
- ~50MB uncompressed, ~15MB compressed

## Configuration Files

### mecabrc
Basic configuration for MeCab. Key settings:
- `dicdir`: Dictionary directory path
- `output-format-type`: Output format (default, wakati, etc.)
- `node-format`: Node output format

### Character Definition (char.def)
Defines character types and their properties:
- DEFAULT: Default character type
- SPACE: Space characters
- KANJI: Chinese characters
- SYMBOL: Symbols
- NUMERIC: Numbers
- ALPHA: Alphabets
- HIRAGANA: Hiragana
- KATAKANA: Katakana

### Unknown Word Definition (unk.def)
Handles unknown words based on character types.

## Integration with WebAssembly

The compressed dictionary format is optimized for:
- Fast loading in browsers
- Reduced memory footprint
- Efficient parsing

## Troubleshooting

If dictionary loading fails:
1. Check file permissions
2. Verify compression was successful
3. Ensure paths in mecabrc are correct
4. Check browser console for detailed errors