# OpenJTalk Support for Windows

This document describes how to use OpenJTalk (Japanese text-to-speech) functionality with Piper on Windows.

## Overview

OpenJTalk is a Japanese text-to-speech system that enables Piper to synthesize Japanese speech. This implementation supports Windows, macOS, and Linux platforms.

## Prerequisites

- Windows 10 or later (Windows 10+ recommended for native tar support)
- Visual Studio 2022 or later (for building from source)
- CMake 3.13 or later

## Building from Source

1. Clone the repository:
```bash
git clone https://github.com/rhasspy/piper.git
cd piper
```

2. Build with CMake:
```bash
mkdir build
cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

The build process will automatically:
- Build OpenJTalk and its dependencies
- Create the `open_jtalk.exe` binary
- Include it in the distribution package

## Using OpenJTalk with Piper

### Basic Usage

To synthesize Japanese text:
```bash
echo "こんにちは、世界" | piper --model ja_JP-test-medium.onnx --output_file hello.wav
```

### Auto-Download Feature

On first use, Piper will automatically download:
- OpenJTalk dictionary (約10MB)
- HTS voice file (約2MB)

These files are downloaded to:
- Windows: `%APPDATA%\piper\`
- Linux/macOS: `~/.local/share/piper/`

## Environment Variables

### OPENJTALK_DICTIONARY_PATH
- **Purpose**: Specify custom dictionary location
- **Default**: Auto-detected or auto-downloaded
- **Example**: 
  ```bash
  set OPENJTALK_DICTIONARY_PATH=C:\custom\path\to\dictionary
  ```

### OPENJTALK_VOICE
- **Purpose**: Specify custom HTS voice file
- **Default**: Auto-downloaded nitech_jp_atr503_m001.htsvoice
- **Example**:
  ```bash
  set OPENJTALK_VOICE=C:\custom\path\to\voice.htsvoice
  ```

### PIPER_AUTO_DOWNLOAD_DICT
- **Purpose**: Control automatic dictionary download
- **Values**: 
  - `1` (default): Enable auto-download
  - `0`: Disable auto-download
- **Example**:
  ```bash
  set PIPER_AUTO_DOWNLOAD_DICT=0
  ```

### PIPER_OFFLINE_MODE
- **Purpose**: Disable all network downloads
- **Values**:
  - `1`: Enable offline mode
  - `0` (default): Allow downloads
- **Example**:
  ```bash
  set PIPER_OFFLINE_MODE=1
  ```

### OPENJTALK_DATA_DIR
- **Purpose**: Override the data directory location
- **Default**: `%APPDATA%\piper` on Windows
- **Example**:
  ```bash
  set OPENJTALK_DATA_DIR=D:\piper-data
  ```

## Troubleshooting

### Issue: "OpenJTalk is not available"

**Cause**: OpenJTalk binary not found or not in PATH

**Solution**:
1. Ensure the build completed successfully
2. Check that `open_jtalk.exe` exists in the piper/bin directory
3. Add the bin directory to your PATH:
   ```bash
   set PATH=%PATH%;C:\path\to\piper\bin
   ```

### Issue: "Failed to download dictionary"

**Cause**: Network issues or offline mode enabled

**Solution**:
1. Check internet connection
2. Disable offline mode:
   ```bash
   set PIPER_OFFLINE_MODE=0
   ```
3. Manually download from: https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz
4. Extract to `%APPDATA%\piper\`

### Issue: "The filename, directory name, or volume label syntax is incorrect"

**Cause**: Path handling issue with special characters or spaces

**Solution**:
1. Use paths without spaces or special characters
2. Ensure all paths use proper Windows backslashes
3. Quote paths with spaces:
   ```bash
   set OPENJTALK_DICTIONARY_PATH="C:\Program Files\dictionary"
   ```

### Issue: "UnicodeEncodeError" when processing Japanese text

**Cause**: Console encoding issue

**Solution**:
1. Set console to UTF-8:
   ```bash
   chcp 65001
   ```
2. Use PowerShell instead of Command Prompt
3. Redirect output to file instead of console

### Issue: "Checksum verification failed"

**Cause**: Corrupted download or network issue

**Solution**:
1. Delete the corrupted file from `%APPDATA%\piper\`
2. Re-run piper to trigger fresh download
3. If persistent, manually download and verify checksum

### Issue: HTS voice extraction fails

**Cause**: Missing tar command or PowerShell restrictions

**Solution**:
1. Update to Windows 10+ for native tar support
2. Use PowerShell as administrator
3. Manually extract the .tar.gz file to the data directory

## Manual Installation

If auto-download is disabled or fails:

1. **Dictionary**:
   - Download: https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz
   - Extract to: `%APPDATA%\piper\open_jtalk_dic_utf_8-1.11\`

2. **HTS Voice**:
   - Download: https://sourceforge.net/projects/open-jtalk/files/HTS%20voice/hts_voice_nitech_jp_atr503_m001-1.05/hts_voice_nitech_jp_atr503_m001-1.05.tar.gz
   - Extract to: `%APPDATA%\piper\hts_voice_nitech_jp_atr503_m001-1.05\`

## Performance Tips

1. **First run**: Allow extra time for initial dictionary/voice download
2. **Offline usage**: After first run, no internet connection required
3. **Custom models**: Use `--model` to specify different Japanese TTS models

## Known Limitations

- Long text may require more memory (current buffer: 4KB)
- Paths with non-ASCII characters may cause issues
- Some special Japanese characters might not be pronounced correctly

## Further Information

- OpenJTalk project: http://open-jtalk.sourceforge.net/
- Piper documentation: https://github.com/rhasspy/piper
- Japanese TTS models: https://github.com/rhasspy/piper/blob/master/MODELS.md