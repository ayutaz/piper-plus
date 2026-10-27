# Piper-Plus Troubleshooting Guide

This guide helps resolve common issues when using piper-plus, especially with Japanese text-to-speech functionality.

## Table of Contents

- [General Issues](#general-issues)
- [Japanese TTS Issues](#japanese-tts-issues)
- [Platform-Specific Issues](#platform-specific-issues)
- [Build Issues](#build-issues)
- [Performance Issues](#performance-issues)
- [Security Audit CI Issues](#security-audit-ci-issues)
- [Training Troubleshooting](#training-troubleshooting)
- [C# CLI (PiperPlus) のトラブルシューティング](#c-cli-piperplus-のトラブルシューティング)

## General Issues

### "Model not found" Error

**Symptoms**:

```text
Error: Model file not found: model.onnx
```

**Solutions**:

1. Verify the model file path is correct
2. Use absolute paths to avoid confusion
3. Check file permissions
4. Download models from official sources

### "Model config doesn't exist" エラー

**症状**:

```text
Model config doesn't exist
```

**設定ファイルの検索順序**: C++ CLI では明示的な `--config`、`PIPER_PLUS_DEFAULT_CONFIG` を優先し、未指定なら以下を検索します。ランタイムごとの差は [モデル解決](../reference/model-resolution.md) を参照してください。

1. `<モデル名>.onnx.json`（例: `model.onnx` → `model.onnx.json`）
2. モデルと同じディレクトリ内の `config.json`（フォールバック）

このフォールバックにより、多くの場合 `--config` の指定は不要です。

**原因**: 上記のどちらも見つからない場合にこのエラーが発生します。

**解決方法**:

1. モデルと同じディレクトリに `config.json` または `<モデル名>.onnx.json` を配置する
2. `--config` オプションで明示的に指定:

   ```bash
   piper-plus --model models/model.onnx --config /path/to/config.json --output_file out.wav
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
4. Supply nonempty text through stdin or `--text`. Writing a WAV file does not require an audio playback device.

## Japanese TTS Issues

### "OpenJTalk is not available" Error

**Symptoms**:

```text
[error] OpenJTalk is not available or failed to process Japanese text
```

**Common Causes & Solutions**:

1. **Dictionary not found**

   ```bash
   # Enable auto-download
   export PIPER_PLUS_AUTO_DOWNLOAD_DICT=1

   # Or specify manually
   export OPENJTALK_DICTIONARY_PATH=/path/to/dictionary
   ```

2. **Using wrong model type**
   - Ensure you're using a Japanese model (ja_JP-*.onnx)
   - For Python inference (`infer_onnx`), the Phonemizer registry selects the G2P backend via `--language` (ja→pyopenjtalk, en→the bundled `g2p-en` backend)
   - For the C++ CLI and preprocessing, `phoneme_type` in `config.json` is still used to choose how text is phonemized
   - Ensure config.json has the correct `"phoneme_type"`: `"openjtalk"` for Japanese models, `"multilingual"` for multilingual models

### "Failed to download dictionary" Error

**Symptoms**:

```text
Error: Failed to download dictionary
Auto-download is disabled. Please download and install the dictionary manually.
```

**Solutions**:

1. **Enable auto-download**:

   ```bash
   unset PIPER_PLUS_AUTO_DOWNLOAD_DICT  # Remove if set to 0
   unset PIPER_PLUS_OFFLINE_MODE        # Remove if set to 1
   ```

2. **Manual download**:

   ```bash
   # Download dictionary
   wget https://github.com/r9y9/open_jtalk/releases/download/v1.11.1/open_jtalk_dic_utf_8-1.11.tar.gz

   # Extract to data directory
   # Windows: %APPDATA%\piper-plus\
   # Linux/macOS: ~/.local/share/piper-plus/
   tar -xzf open_jtalk_dic_utf_8-1.11.tar.gz
   ```

3. **Check network**:
   - Verify internet connection
   - Check proxy settings
   - Try different download method (curl vs wget)

### "Checksum verification failed" Error

**Symptoms**:

```text
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

Use UTF-8 for the terminal and for text passed to native processes. In
Windows PowerShell 5.1, changing the console code page alone does not set
the encoding of native-process pipeline input.

#### Windows で日本語テキストが文字化けする（No phoneme エラー）

PowerShell では、パイプ出力を明示的に UTF-8 に設定します。

```powershell
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
"こんにちは。" | .\bin\piper-plus.exe --model .\models\model.onnx --language ja --output_file out.wav
```

cmd では `chcp 65001` の後に UTF-8 ファイルを `type` で渡せます。
具体的な配置と手順は [Windows セットアップ](windows-setup.md#日本語が文字化けする) を参照してください。

#### "The filename, directory name, or volume label syntax is incorrect"

**Solutions**:

1. Use short paths without spaces
2. Quote all paths: `"C:\Program Files\piper-plus\bin\piper-plus.exe"`
3. Use forward slashes: `C:/piper-plus/bin/piper-plus.exe`

#### PowerShell Execution Policy

**If scripts are blocked**:

```powershell
# Set the policy for the current user if local policy allows it
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

#### `GLIBC_2.xx not found` on ARM64

The published v2.0.1 `piper-plus-cpp-linux-arm64.tar.gz` requires glibc
2.38 and does not start on Debian Bullseye (2.31) or Bookworm (2.36).
Use the v2.0.2 archive, built on Bullseye with a glibc 2.31 ABI ceiling.
CI checks startup and Japanese synthesis on Bullseye, Bookworm and Trixie
under QEMU. Raspberry Pi hardware and Raspberry Pi OS remain untested. See [binary selection](binary-selection.md).
Do not replace an operating system's libc with a copied shared library.

#### Permission Denied

**Solutions**:

```bash
# Make executable
chmod +x piper-plus/bin/piper-plus

# Check SELinux (if applicable)
# If SELinux reports a denial, inspect its audit log and the target file context.
```

## Build Issues

### CMake Cannot Find ONNX Runtime

**Solution**:

```bash
# Specify ONNX Runtime location
cmake -S . -B build -DONNXRUNTIME_DIR=/path/to/onnxruntime
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
3. Monitor with: `piper-plus --debug`

### Slow Synthesis

**Solutions**:

1. Use faster models (small/medium vs large)
2. Enable GPU acceleration if available
3. Reduce audio quality if acceptable

## Debug Mode

Enable debug output for more information:

```bash
piper-plus --debug --model model.onnx < input.txt
```

## Getting Help

If issues persist:

1. **Check logs**: Look for error messages and warnings
2. **Version info**: Include `piper-plus --version` output
3. **System info**: Include OS, architecture, installation method
4. **Reproduction steps**: Provide minimal example
5. **Report issue**: <https://github.com/ayutaz/piper-plus/issues>

## Common Error Messages Reference

| Error | Cause | Solution |
|-------|-------|----------|
| "OpenJTalk is not available" | Dictionary missing | Download/specify dictionary |
| "Failed to initialize OpenJTalk" | Dictionary missing | Download/specify dictionary |
| "Unknown multi-character phoneme" | Wrong phoneme format | Update to latest version |
| "Checksum verification failed" | Corrupt download | Re-download files |
| "UnicodeEncodeError" (Windows) | Console encoding | Use chcp 65001 |

## Security Audit CI Issues

### `Security Audit / pip-audit` fails on a transitive dependency CVE

**Symptoms**: The `Audit src/python_run` step of the
`Security Audit / pip-audit (Python)` job fails on a `push` to `dev` / `main`
(it is `continue-on-error` on pull requests, so PRs only warn), reporting a
CVE / PYSEC advisory against a package that is **not** listed directly in
`requirements.txt` — for example, the historical `g2p-en` → `nltk` → `joblib`
transitive dependency that was present before the English backend was bundled.
Current source packages do not install external `g2p-en` or `Distance`.
The *same commit* may pass in a later `schedule` run.

> The sibling `Audit root requirements` step never fails the job on any event —
> it is unconditionally `continue-on-error: true` because it audits the
> workspace-meta dev/train closure, which piper-plus does not distribute. Its
> findings are reported in the log for information only. See the tier rationale
> in `.github/workflows/security-audit.yml`.

**Diagnosis and resolution**:

1. Record the failing step, resolved package version, advisory ID and fixed
   versions. A transitive dependency is still part of the installed runtime;
   do not assume the report is a false positive.
2. Inspect the linked advisory and the dependency chain. Compare the resolved
   version with the advisory's affected range. If advisory data was corrected
   upstream, retain that evidence before rerunning the audit.
3. Update the appropriate requirement/lockfile and run the relevant tests.
   A successful rerun alone does not explain why the earlier finding vanished.
4. An advisory suppression requires a documented reason and a removal
   condition; it must not replace checking the affected version range.

See the [official pip-audit documentation](https://github.com/pypa/pip-audit#troubleshooting)
for tool errors and vulnerability-service behavior. The workflow file remains
the source of truth for this repository's blocking/informational policy.

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

1. Confirm which process and device exhausted memory. NCCL transport overrides are not a general fix for GPU out-of-memory errors.

2. Reduce `batch_size` and `samples_per_speaker`:

   ```bash
   --batch-size 12 --samples-per-speaker 2
   ```

3. Check the model configuration, WavLM setting and other GPU processes. Batch size may be changed for a new run; distinguish a new fine-tune from full optimizer-state resume. See the [training guide](../guides/training/training-guide.md).

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

**解決策**: ソースから実行・ビルドする場合は .NET 10 SDK をインストールしてください。セルフコンテインドの配布 CLI には別途 SDK/ランタイムは不要です:

- <https://dotnet.microsoft.com/download>

### DotNetG2P パッケージエラー

**問題**: 日本語の G2P でエラーが発生

C# CLI で外部パッケージ `DotNetG2P` / `DotNetG2P.MeCab` を使うのは日本語だけです。英語・中国語・スペイン語・フランス語・ポルトガル語の G2P は `PiperPlus.Core` に移行済みで、外部パッケージを使いません。

**解決策**: NuGet パッケージの復元を実行:

```bash
dotnet restore src/csharp/PiperPlus.sln
```

### ONNX Runtime エラー

**問題**: モデル読み込み時に ONNX Runtime エラー

**解決策**:

- Microsoft.ML.OnnxRuntime.Managed v1.24.3 が必要
- ネイティブ ONNX Runtime と選択プロバイダーを一致させてください。NuGet の Managed パッケージだけでは CUDA/DirectML は有効になりません。[C# CLI](../../src/csharp/PiperPlus.Cli/README.md) の配布・プロバイダー設定を参照してください。
