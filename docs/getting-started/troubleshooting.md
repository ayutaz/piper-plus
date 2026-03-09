# Piper Troubleshooting Guide

This guide helps resolve common issues when using Piper, especially with Japanese text-to-speech functionality.

## Table of Contents
- [General Issues](#general-issues)
- [Japanese TTS Issues](#japanese-tts-issues)
- [Platform-Specific Issues](#platform-specific-issues)
- [Build Issues](#build-issues)
- [Performance Issues](#performance-issues)
- [Training Troubleshooting](#training-troubleshooting)

## General Issues

### "Model not found" Error

**Symptoms**: 
```
Error: Model file not found: model.onnx
```

**Solutions**:
1. Verify the model file path is correct
2. Use absolute paths to avoid confusion
3. Check file permissions
4. Download models from official sources

### "No audio output" Issue

**Symptoms**: Command runs without errors but no audio file is created

**Solutions**:
1. Check output file path has write permissions
2. Verify `--output_file` parameter is specified
3. Try `--output_raw` to test raw audio output
4. Check system audio drivers are working

## Japanese TTS Issues

### "OpenJTalk is not available" Error

**Symptoms**:
```
[error] OpenJTalk is not available or failed to process Japanese text
```

**Common Causes & Solutions**:

1. **OpenJTalk binary not found**
   ```bash
   # Check if open_jtalk is in PATH
   which open_jtalk  # Linux/macOS
   where open_jtalk  # Windows
   
   # Add to PATH if needed
   export PATH=/path/to/piper/bin:$PATH  # Linux/macOS
   set PATH=%PATH%;C:\path\to\piper\bin  # Windows
   ```

2. **Dictionary not found**
   ```bash
   # Enable auto-download
   export PIPER_AUTO_DOWNLOAD_DICT=1
   
   # Or specify manually
   export OPENJTALK_DICTIONARY_DIR=/path/to/dictionary
   ```

3. **Using wrong model type**
   - Ensure you're using a Japanese model (ja_JP-*.onnx)
   - For Python inference (`infer_onnx`), the Phonemizer registry selects the G2P backend via `--language` (ja→pyopenjtalk, en→g2p-en)
   - For the C++ CLI and preprocessing, `phoneme_type` in `config.json` is still used to choose how text is phonemized
   - Ensure config.json has the correct `"phoneme_type"`: `"openjtalk"` for Japanese models, `"espeak"` for other languages

### "Failed to download dictionary" Error

**Symptoms**:
```
Error: Failed to download dictionary
Auto-download is disabled. Please download and install the dictionary manually.
```

**Solutions**:

1. **Enable auto-download**:
   ```bash
   unset PIPER_AUTO_DOWNLOAD_DICT  # Remove if set to 0
   unset PIPER_OFFLINE_MODE        # Remove if set to 1
   ```

2. **Manual download**:
   ```bash
   # Download dictionary
   wget https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz
   
   # Extract to data directory
   # Windows: %APPDATA%\piper\
   # Linux/macOS: ~/.local/share/piper/
   tar -xzf open_jtalk_dic_utf_8-1.11.tar.gz
   ```

3. **Check network**:
   - Verify internet connection
   - Check proxy settings
   - Try different download method (curl vs wget)

### "Checksum verification failed" Error

**Symptoms**:
```
Error: Checksum mismatch! Expected abc123..., got def456...
```

**Solutions**:
1. Delete corrupted download and retry
2. Check disk space
3. Verify network stability
4. Try manual download with checksum verification

### Japanese Text Produces No Sound

**Symptoms**: Command completes but audio is silent or corrupted

**Possible Causes**:
1. **Wrong encoding**: Ensure UTF-8 encoding
   ```bash
   # Windows
   chcp 65001
   
   # Save text as UTF-8
   echo "テスト" > test.txt  # Use UTF-8 editor
   ```

2. **Unsupported characters**: Some special characters may not be supported

3. **Model mismatch**: Ensure model supports Japanese phonemes

## Platform-Specific Issues

### Windows

#### "UnicodeEncodeError" with Japanese Text

**Solution**:
```cmd
REM Set console to UTF-8
chcp 65001

REM Use PowerShell instead
powershell -Command "echo 'こんにちは' | .\piper.exe --model model.onnx --output_file out.wav"
```

#### "The filename, directory name, or volume label syntax is incorrect"

**Solutions**:
1. Use short paths without spaces
2. Quote all paths: `"C:\Program Files\piper\bin\piper.exe"`
3. Use forward slashes: `C:/piper/bin/piper.exe`

#### PowerShell Execution Policy

**If scripts are blocked**:
```powershell
# Allow script execution (run as admin)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### macOS

#### "Library not loaded" Error

**Symptoms**:
```
dyld: Library not loaded: @rpath/libpiper_phonemize.1.dylib
```

**Solutions**:
```bash
# Set library path
export DYLD_LIBRARY_PATH=/path/to/piper/lib:$DYLD_LIBRARY_PATH
export DYLD_FALLBACK_LIBRARY_PATH=/path/to/piper/lib:$DYLD_FALLBACK_LIBRARY_PATH

# Or install to system location
sudo cp piper/lib/*.dylib /usr/local/lib/
```

#### Gatekeeper Warnings

**Solution**:
```bash
# Remove quarantine attribute
xattr -cr /path/to/piper/
```

### Linux

#### "libpiper_phonemize.so.1: cannot open shared object file"

**Solutions**:
```bash
# Add library path
export LD_LIBRARY_PATH=/path/to/piper/lib:$LD_LIBRARY_PATH

# Or add to system
echo "/path/to/piper/lib" | sudo tee /etc/ld.so.conf.d/piper.conf
sudo ldconfig
```

#### Permission Denied

**Solutions**:
```bash
# Make executable
chmod +x piper/bin/piper
chmod +x piper/bin/open_jtalk

# Check SELinux (if applicable)
sudo setenforce 0  # Temporary disable to test
```

## Build Issues

### CMake Cannot Find ONNX Runtime

**Solution**:
```bash
# Specify ONNX Runtime location
cmake .. -DONNXRUNTIME_DIR=/path/to/onnxruntime
```

### OpenJTalk Build Fails

**Common fixes**:
1. Ensure all submodules are initialized:
   ```bash
   git submodule update --init --recursive
   ```

2. Install required build tools:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install build-essential cmake
   
   # macOS
   brew install cmake ninja
   
   # Windows
   # Install Visual Studio with C++ support
   ```

## Performance Issues

### Slow First Run

**Cause**: Downloading dictionary/voice files

**Solutions**:
1. Pre-download files in deployment
2. Use local mirror for downloads
3. Cache downloaded files

### High Memory Usage

**Solutions**:
1. Process text in smaller chunks
2. Use streaming mode for long texts
3. Monitor with: `piper --debug`

### Slow Synthesis

**Solutions**:
1. Use faster models (small/medium vs large)
2. Enable GPU acceleration if available
3. Reduce audio quality if acceptable

## Debug Mode

Enable debug output for more information:
```bash
# Set debug logging
export PIPER_LOG_LEVEL=DEBUG

# Or use debug flag
piper --debug --model model.onnx < input.txt
```

## Getting Help

If issues persist:

1. **Check logs**: Look for error messages and warnings
2. **Version info**: Include `piper --version` output
3. **System info**: Include OS, architecture, installation method
4. **Reproduction steps**: Provide minimal example
5. **Report issue**: https://github.com/ayutaz/piper-plus/issues

## Common Error Messages Reference

| Error | Cause | Solution |
|-------|-------|----------|
| "OpenJTalk is not available" | Binary not found | Check PATH, install OpenJTalk |
| "Failed to initialize OpenJTalk" | Dictionary missing | Download/specify dictionary |
| "Unknown multi-character phoneme" | Wrong phoneme format | Update to latest version |
| "Checksum verification failed" | Corrupt download | Re-download files |
| "HTS voice must be specified" | Voice file missing | Download/specify .htsvoice file |
| "Cannot open shared object" | Missing library | Set LD_LIBRARY_PATH |
| "Library not loaded" (macOS) | Missing dylib | Set DYLD_LIBRARY_PATH |
| "UnicodeEncodeError" (Windows) | Console encoding | Use chcp 65001 |

## Training Troubleshooting

### Duration Predictor Collapse (Audio Becomes a Beep/Tone)

**Symptoms**: Inference audio is a continuous "beep" tone instead of speech. This indicates the Duration Predictor failed to learn properly.

**Solutions**:
1. Use `--samples-per-speaker` to ensure balanced batches across speakers:
   ```bash
   --batch-size 20 --samples-per-speaker 4  # 5 speakers x 4 samples = 20
   ```
2. Disable automatic learning rate scaling:
   ```bash
   --disable_auto_lr_scaling
   ```
3. Lower the learning rate:
   ```bash
   --base_lr 1e-4
   ```

### GPU Out of Memory (OOM)

**Symptoms**: Training crashes with CUDA OOM errors.

**Solutions**:
1. Set NCCL environment variables (required for multi-GPU):
   ```bash
   export NCCL_DEBUG=WARN
   export NCCL_P2P_DISABLE=1
   export NCCL_IB_DISABLE=1
   ```
2. Reduce `batch_size` and `samples_per_speaker`:
   ```bash
   --batch-size 12 --samples-per-speaker 2
   ```
3. Avoid resuming training from a checkpoint that was saved with a different batch size, as this can cause memory allocation issues.

### ONNX Conversion Errors

**Symptoms**: Errors during `export_onnx.py`, especially on GPU machines.

**Solutions**:
1. Run ONNX conversion in CPU mode to avoid GPU-related issues:
   ```bash
   CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
     /path/to/checkpoint.ckpt /path/to/output.onnx
   ```
2. For WavLM-trained models, use `--stochastic` to enable noise-scale sampling:
   ```bash
   CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
     --stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
   ```
3. Use `--no-ema` for baseline models without EMA weights:
   ```bash
   CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
     --no-ema /path/to/checkpoint.ckpt /path/to/output.onnx
   ```