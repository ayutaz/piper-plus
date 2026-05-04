# Piper Troubleshooting Guide

This guide helps resolve common issues when using Piper, especially with Japanese text-to-speech functionality.

## Table of Contents
- [General Issues](#general-issues)
- [Japanese TTS Issues](#japanese-tts-issues)
- [Platform-Specific Issues](#platform-specific-issues)
- [Build Issues](#build-issues)
- [Performance Issues](#performance-issues)
- [Training Troubleshooting](#training-troubleshooting)
- [C# CLI (PiperPlus) のトラブルシューティング](#c-cli-piperplus-のトラブルシューティング)

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

### "Model config doesn't exist" エラー

**症状**:
```
Model config doesn't exist
```

**設定ファイルの検索順序**: piper は以下の順序で設定ファイルを自動検索します。
1. `<モデル名>.onnx.json`（例: `model.onnx` → `model.onnx.json`）
2. モデルと同じディレクトリ内の `config.json`（フォールバック）

このフォールバックにより、多くの場合 `--config` の指定は不要です。

**原因**: 上記のどちらも見つからない場合にこのエラーが発生します。

**解決方法**:
1. モデルと同じディレクトリに `config.json` または `<モデル名>.onnx.json` を配置する
2. `--config` オプションで明示的に指定:
   ```bash
   piper --model models/model.onnx --config /path/to/config.json --output_file out.wav
   ```
3. 同一ディレクトリに複数モデルがあり `config.json` では区別できない場合、モデルごとにリネーム:
   ```bash
   mv config.json model.onnx.json
   ```

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

1. **Dictionary not found**
   ```bash
   # Enable auto-download
   export PIPER_AUTO_DOWNLOAD_DICT=1
   
   # Or specify manually
   export OPENJTALK_DICTIONARY_PATH=/path/to/dictionary
   ```

3. **Using wrong model type**
   - Ensure you're using a Japanese model (ja_JP-*.onnx)
   - For Python inference (`infer_onnx`), the Phonemizer registry selects the G2P backend via `--language` (ja→pyopenjtalk, en→g2p-en)
   - For the C++ CLI and preprocessing, `phoneme_type` in `config.json` is still used to choose how text is phonemized
   - Ensure config.json has the correct `"phoneme_type"`: `"openjtalk"` for Japanese models, `"multilingual"` for multilingual models

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

#### Windows で日本語テキストが文字化けする（No phoneme エラー）

**症状**: PowerShell から日本語テキストをパイプすると、OpenJTalk が `No phoneme` で失敗する。

**原因**: Windows のコンソールエンコーディングが UTF-8 でないため、パイプ経由で文字化けが発生。

**解決方法**:

1. **cmd で `chcp 65001` を実行してから使用**:
   ```cmd
   chcp 65001
   echo こんにちは | piper.exe --model model.onnx --config config.json --output_file out.wav
   ```

2. **ファイル経由で入力** (最も確実):
   ```cmd
   REM UTF-8 BOMなしでテキストファイルを作成
   powershell -Command "$utf8 = New-Object System.Text.UTF8Encoding($false); [System.IO.File]::WriteAllText('input.txt', 'こんにちは', $utf8)"

   chcp 65001
   type input.txt | piper.exe --model model.onnx --config config.json --output_file out.wav
   ```

3. **v1.5.5以降**: piper.exe 内部で `SetConsoleCP(CP_UTF8)` が呼び出されますが、一部の環境ではパイプ入力に効かない場合があります。その場合は方法2を使用してください。

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

#### Gatekeeper Warnings

**Solution**:
```bash
# Remove quarantine attribute
xattr -cr /path/to/piper/
```

### Linux

#### Permission Denied

**Solutions**:
```bash
# Make executable
chmod +x piper/bin/piper

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
| "OpenJTalk is not available" | Dictionary missing | Download/specify dictionary |
| "Failed to initialize OpenJTalk" | Dictionary missing | Download/specify dictionary |
| "Unknown multi-character phoneme" | Wrong phoneme format | Update to latest version |
| "Checksum verification failed" | Corrupt download | Re-download files |
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
2. Stochastic + EMA are enabled by default. Use `--no-stochastic` for deterministic export:
   ```bash
   CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
     --no-stochastic /path/to/checkpoint.ckpt /path/to/output.onnx
   ```

## C# CLI (PiperPlus) のトラブルシューティング

### .NET ランタイムが見つからない

**問題**: `dotnet` コマンドが認識されない

**解決策**: .NET 10 SDK 以上をインストールしてください:
- https://dotnet.microsoft.com/download

### DotNetG2P パッケージエラー

**問題**: 中国語/スペイン語/フランス語/ポルトガル語の G2P でエラーが発生

**解決策**: NuGet パッケージの復元を実行:
```bash
dotnet restore src/csharp/PiperPlus.sln
```

### ONNX Runtime エラー

**問題**: モデル読み込み時に ONNX Runtime エラー

**解決策**:
- Microsoft.ML.OnnxRuntime.Managed v1.24.3 が必要
- GPU版を使用する場合は Microsoft.ML.OnnxRuntime.Gpu に変更