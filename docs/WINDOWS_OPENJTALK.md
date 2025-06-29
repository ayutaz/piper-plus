# OpenJTalk on Windows

## Overview

OpenJTalk is a Japanese text-to-speech synthesis system that is required for Japanese language support in Piper. Building OpenJTalk on Windows presents unique challenges due to its Unix-oriented build system and dependencies.

## Current Solution

Piper uses a **pre-built binary approach** for OpenJTalk on Windows:

1. **Automated Builds**: GitHub Actions builds OpenJTalk for Windows monthly using MinGW/MSYS2
2. **Automatic Download**: During CMake configuration, the binary is downloaded from GitHub releases
3. **Fallback Wrapper**: If download fails, a minimal wrapper is built that shows informative error messages

## How It Works

When building Piper on Windows:

```cmake
# CMakeLists.txt attempts to download the binary
# This should be updated to point to your own repository
set(OPENJTALK_WINDOWS_URL "https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe")

# Downloads to: build/oj/bin/open_jtalk.exe
```

## Manual Download

If automatic download fails, you can manually download the binary:

```powershell
# Using the provided PowerShell script
.\scripts\download_openjtalk_windows.ps1

# Or manually download from:
# https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe
# Place in: build/oj/bin/open_jtalk.exe
```

## Limitations

- The Windows binary may not have all features of the Unix version
- First-time builders need internet access or must wait for CI builds
- Complex Japanese text may not be processed as accurately as on Unix systems

## Alternative Solutions

### 1. Use WSL2 (Recommended for Development)

For full Japanese TTS functionality:

```bash
# Install WSL2
wsl --install

# Build and run Piper inside WSL2
# This provides full Unix compatibility
```

### 2. Build from Source with MSYS2

Advanced users can build OpenJTalk using MSYS2:

```bash
# Install MSYS2 from https://www.msys2.org/
# In MSYS2 terminal:
pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake make
# Follow the build-openjtalk-windows.yml workflow steps
```

### 3. Use Docker

Run Piper in a Linux container:

```bash
docker run -it ubuntu:latest
# Install dependencies and build Piper
```

## Why Not Native Windows Build?

1. **Complex Dependencies**: OpenJTalk depends on MeCab and multiple processing modules
2. **Build System**: Uses autotools which is Unix-centric
3. **Character Encoding**: Complex UTF-8 handling differences between platforms
4. **Development Effort**: Full Windows port would require significant changes

## Future Improvements

- Cache downloaded binaries locally
- Provide multiple download mirrors
- Create a NuGet package for easier distribution
- Investigate native Windows TTS APIs as alternative

## Troubleshooting

### Binary Download Fails

1. Check internet connectivity
2. Verify GitHub is accessible
3. Check if CI build has completed
4. Download manually using the PowerShell script

### Japanese Text Not Working

1. Ensure the binary downloaded successfully
2. Check that dictionary files are present
3. Verify UTF-8 encoding is used
4. Test with simple Japanese text first

### Build Errors

1. Ensure HTSEngine is built first
2. Check CMake output for download status
3. Look for open_jtalk.exe in build/oj/bin/
4. Try manual download if automatic fails

## Contact

For issues specific to Windows OpenJTalk support, please open an issue on the Piper GitHub repository with:
- CMake configuration output
- Error messages
- Windows version
- Whether manual download succeeded