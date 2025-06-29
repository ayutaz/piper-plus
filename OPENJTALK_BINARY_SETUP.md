# OpenJTalk Binary Setup Guide

This guide explains how to configure the project to use OpenJTalk binaries from your own repository.

## Files to Update

When forking this project, you need to update the following files to point to your own repository for OpenJTalk binaries:

### 1. CMakeLists.txt (line ~271)

Replace:
```cmake
set(OPENJTALK_WINDOWS_URL "https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe")
```

With:
```cmake
set(OPENJTALK_WINDOWS_URL "https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe")
```

### 2. scripts/download_openjtalk_windows.ps1 (line ~30)

Replace:
```powershell
"https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPO_NAME/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe",
```

With:
```powershell
"https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe",
```

### 3. docs/WINDOWS_OPENJTALK.md

Update the documentation URLs to point to your repository.

## Setting Up OpenJTalk Binary Builds

1. The repository includes a GitHub Actions workflow (`.github/workflows/build-openjtalk-binaries.yml`) that automatically builds OpenJTalk binaries for all platforms.

2. This workflow will:
   - Build OpenJTalk for Windows (cross-compiled on Linux)
   - Build OpenJTalk for macOS
   - Build OpenJTalk for Linux
   - Create a release with tag `openjtalk-binaries-latest`

3. To trigger the build:
   - Push to the `master` branch, or
   - Manually run the workflow from the Actions tab

## Environment Variable Override

You can also override the download URL using an environment variable:

```bash
export OPENJTALK_WINDOWS_URL="https://github.com/YOUR_USERNAME/YOUR_REPO/releases/download/openjtalk-binaries-latest/open_jtalk_windows_x64.exe"
```

This is useful for testing or CI/CD environments.

## Binary Release Contents

The automated release will contain:
- `open_jtalk_windows_x64.exe` - Windows 64-bit binary
- `open_jtalk_macos_x64` - macOS 64-bit binary
- `open_jtalk_linux_x64` - Linux 64-bit binary
- `SHA256SUMS` - Checksums for verification

## Notes

- The binaries are built with HTSEngine API 1.10 and OpenJTalk 1.11
- UTF-8 charset support is enabled
- The Windows binary is statically linked to avoid DLL dependencies