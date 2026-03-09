# Piper Environment Variables Reference

This document lists all environment variables that can be used to configure Piper's behavior.

## OpenJTalk Configuration

### OPENJTALK_DICTIONARY_PATH
- **Description**: Path to OpenJTalk dictionary directory
- **Default**: Auto-downloaded to user data directory
- **Platform defaults**:
  - Windows: `%APPDATA%\piper\open_jtalk_dic_utf_8-1.11`
  - Linux: `~/.local/share/piper/open_jtalk_dic_utf_8-1.11`
  - macOS: `~/.local/share/piper/open_jtalk_dic_utf_8-1.11`
- **Example**:
  ```bash
  # Windows
  set OPENJTALK_DICTIONARY_PATH=C:\openjtalk\dictionary

  # Linux/macOS
  export OPENJTALK_DICTIONARY_PATH=/usr/share/open_jtalk/dic
  ```

### OPENJTALK_VOICE
- **Description**: Path to HTS voice file (.htsvoice)
- **Default**: Auto-downloaded nitech_jp_atr503_m001.htsvoice
- **Note**: HTS voice functionality is currently disabled. Piper operates in phonemizer-only mode, so this variable has no effect at present.
- **Example**:
  ```bash
  # Windows
  set OPENJTALK_VOICE=C:\voices\mei_normal.htsvoice

  # Linux/macOS
  export OPENJTALK_VOICE=/usr/share/hts-voice/mei_normal.htsvoice
  ```

### OPENJTALK_DATA_DIR
- **Description**: Override the base directory for OpenJTalk data files
- **Default**: Platform-specific user data directory
- **Example**:
  ```bash
  # Windows
  set OPENJTALK_DATA_DIR=D:\piper-data
  
  # Linux/macOS
  export OPENJTALK_DATA_DIR=/opt/piper-data
  ```

## Download Control

### PIPER_AUTO_DOWNLOAD_DICT
- **Description**: Control automatic download of OpenJTalk dictionary and voice files
- **Values**:
  - `1` (default): Enable automatic download
  - `0`: Disable automatic download
- **Example**:
  ```bash
  # Disable auto-download
  export PIPER_AUTO_DOWNLOAD_DICT=0
  ```

### PIPER_OFFLINE_MODE
- **Description**: Enable offline mode (no network access)
- **Values**:
  - `0` (default): Allow network access
  - `1`: Offline mode - prevent all downloads
- **Example**:
  ```bash
  # Enable offline mode
  export PIPER_OFFLINE_MODE=1
  ```

## Runtime Configuration

### ESPEAK_DATA_PATH
- **Description**: Path to espeak-ng data directory
- **Default**: Varies by installation method
- **Typical locations**:
  - Bundled: `piper/share/espeak-ng-data`
  - System: `/usr/share/espeak-ng-data`
- **Example**:
  ```bash
  export ESPEAK_DATA_PATH=/usr/local/share/espeak-ng-data
  ```

### LD_LIBRARY_PATH (Linux)
- **Description**: Library search path for shared libraries
- **Usage**: May need to include piper/lib directory
- **Example**:
  ```bash
  export LD_LIBRARY_PATH=/path/to/piper/lib:$LD_LIBRARY_PATH
  ```

### DYLD_LIBRARY_PATH (macOS)
- **Description**: Library search path for dynamic libraries
- **Usage**: May need to include piper/lib directory
- **Example**:
  ```bash
  export DYLD_LIBRARY_PATH=/path/to/piper/lib:$DYLD_LIBRARY_PATH
  ```

## Usage Examples

### Basic Japanese TTS (auto-download enabled)
```bash
# No environment variables needed - will auto-download on first use
echo "こんにちは" | piper --model ja_JP-model.onnx --output_file hello.wav
```

### Custom dictionary location
```bash
# Windows
set OPENJTALK_DICTIONARY_PATH=C:\my-dictionary
set OPENJTALK_VOICE=C:\my-voice.htsvoice
echo "テスト" | piper --model ja_JP-model.onnx --output_file test.wav

# Linux/macOS
export OPENJTALK_DICTIONARY_PATH=/opt/my-dictionary
export OPENJTALK_VOICE=/opt/my-voice.htsvoice
echo "テスト" | piper --model ja_JP-model.onnx --output_file test.wav
```

### Offline mode (no downloads)
```bash
# Must have dictionary and voice files already installed
export PIPER_OFFLINE_MODE=1
export OPENJTALK_DICTIONARY_PATH=/path/to/existing/dictionary
export OPENJTALK_VOICE=/path/to/existing/voice.htsvoice
echo "オフライン" | piper --model ja_JP-model.onnx --output_file offline.wav
```

## Precedence Order

Environment variables are checked in the following order:
1. User-specified paths (OPENJTALK_DICTIONARY_PATH, OPENJTALK_VOICE)
2. System-installed locations (/usr/share/*, /usr/local/share/*)
3. Auto-download to user data directory (if enabled)

## Troubleshooting

### Dictionary not found
1. Check if `PIPER_AUTO_DOWNLOAD_DICT=0` is set
2. Verify `OPENJTALK_DICTIONARY_PATH` points to valid directory
3. Ensure dictionary files exist (sys.dic, unk.dic, etc.)

### Download failures
1. Check internet connection
2. Verify `PIPER_OFFLINE_MODE` is not set to 1
3. Check write permissions to data directory
4. Look for proxy/firewall issues

### Wrong character encoding
1. Ensure terminal/console supports UTF-8
2. On Windows, use `chcp 65001` for UTF-8 support
3. Check file encoding when reading from files