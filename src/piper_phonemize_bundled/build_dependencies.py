#!/usr/bin/env python3
"""
Build dependencies for piper-phonemize-bundled
Downloads and builds espeak-ng and onnxruntime for the target platform
"""

import argparse
import hashlib
import platform
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path


def download_file(url, dest_path):
    """Download a file with progress indicator and SSL verification"""

    print(f"Downloading {url}...")

    # Create SSL context with verification
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = True
    ssl_context.verify_mode = ssl.CERT_REQUIRED

    req = urllib.request.Request(
        url, headers={"User-Agent": "piper-phonemize-bundled/1.2.0"}
    )

    with urllib.request.urlopen(req, context=ssl_context) as response:
        total_size = int(response.headers.get("Content-Length", 0))
        block_size = 8192
        downloaded = 0
        hasher = hashlib.sha256()

        with open(dest_path, "wb") as f:
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                downloaded += len(buffer)
                hasher.update(buffer)
                f.write(buffer)

                if total_size > 0:
                    progress = (downloaded / total_size) * 100
                    print(f"Progress: {progress:.1f}%", end="\r")

    print(f"\nDownload complete! SHA256: {hasher.hexdigest()[:16]}...")


def extract_archive(archive_path, extract_to):
    """Extract zip or tar.gz archive"""
    print(f"Extracting {archive_path}...")
    archive_path_str = str(archive_path)
    if archive_path_str.endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as z:
            z.extractall(extract_to)
    elif archive_path_str.endswith(".tar.gz") or archive_path_str.endswith(".tgz"):
        with tarfile.open(archive_path, "r:gz") as t:
            t.extractall(extract_to)
    else:
        raise ValueError(f"Unknown archive format: {archive_path}")


def build_espeak_ng_windows(build_dir):
    """Build espeak-ng for Windows"""
    print("Building espeak-ng for Windows...")

    espeak_dir = build_dir / "espeak-ng"
    espeak_dir.mkdir(parents=True, exist_ok=True)

    # Download espeak-ng source (pinned to specific commit for reproducibility)
    # Using rhasspy's fork which has the necessary patches for Piper
    espeak_commit = "0f65aa301e0d6bae5e172cc74197d32a6182200f"
    espeak_url = f"https://github.com/rhasspy/espeak-ng/archive/{espeak_commit}.zip"
    espeak_zip = build_dir / "espeak-ng.zip"

    if not espeak_zip.exists():
        download_file(espeak_url, espeak_zip)

    # Extract
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_archive(espeak_zip, tmpdir)
        src_dir = Path(tmpdir) / f"espeak-ng-{espeak_commit}"

        # Build with CMake
        build_path = src_dir / "build"
        build_path.mkdir(exist_ok=True)

        # Configure
        subprocess.run(
            [
                "cmake",
                "..",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=" + str(espeak_dir),
                "-DBUILD_SHARED_LIBS=ON",
                "-DUSE_ASYNC=OFF",
                "-DUSE_MBROLA=OFF",
                "-DUSE_LIBSONIC=OFF",
                "-DUSE_LIBPCAUDIO=OFF",
                "-DEXTRA_cmn=OFF",
                "-DEXTRA_ru=OFF",
            ],
            cwd=build_path,
            check=True,
        )

        # Build
        subprocess.run(
            ["cmake", "--build", ".", "--config", "Release"], cwd=build_path, check=True
        )

        # Install
        subprocess.run(
            ["cmake", "--install", ".", "--config", "Release"],
            cwd=build_path,
            check=True,
        )

        # Copy espeak-ng-data
        data_src = src_dir / "espeak-ng-data"
        data_dst = espeak_dir / "share" / "espeak-ng-data"
        if data_src.exists():
            shutil.copytree(data_src, data_dst, dirs_exist_ok=True)


def build_espeak_ng_unix(build_dir, platform_name):
    """Build espeak-ng for Unix-like systems (macOS/Linux)"""
    print(f"Building espeak-ng for {platform_name}...")

    espeak_dir = build_dir / "espeak-ng"
    espeak_dir.mkdir(parents=True, exist_ok=True)

    # Download espeak-ng source (pinned to specific commit for reproducibility)
    espeak_commit = "0f65aa301e0d6bae5e172cc74197d32a6182200f"
    espeak_url = f"https://github.com/rhasspy/espeak-ng/archive/{espeak_commit}.tar.gz"
    espeak_tar = build_dir / "espeak-ng.tar.gz"

    if not espeak_tar.exists():
        download_file(espeak_url, espeak_tar)

    # Extract and build
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_archive(espeak_tar, tmpdir)
        src_dir = Path(tmpdir) / f"espeak-ng-{espeak_commit}"

        # Run autogen.sh if it exists
        autogen = src_dir / "autogen.sh"
        if autogen.exists():
            subprocess.run(["sh", "autogen.sh"], cwd=src_dir, check=True)

        # Configure
        configure_args = [
            "./configure",
            f"--prefix={espeak_dir}",
            "--without-async",
            "--without-mbrola",
            "--without-sonic",
            "--without-pcaudiolib",
        ]

        if platform_name == "macos":
            configure_args.append("--without-klatt")

        subprocess.run(configure_args, cwd=src_dir, check=True)

        # Build and install
        subprocess.run(["make", "-j4"], cwd=src_dir, check=True)
        subprocess.run(["make", "install"], cwd=src_dir, check=True)

        # Copy espeak-ng-data
        data_src = src_dir / "espeak-ng-data"
        data_dst = espeak_dir / "share" / "espeak-ng-data"
        if data_src.exists():
            shutil.copytree(data_src, data_dst, dirs_exist_ok=True)


def download_onnxruntime(build_dir, platform_name):
    """Download pre-built ONNX Runtime"""
    print(f"Downloading ONNX Runtime for {platform_name}...")

    onnx_dir = build_dir / "onnxruntime"
    onnx_dir.mkdir(parents=True, exist_ok=True)

    # ONNX Runtime version
    onnx_version = "1.16.3"

    # Platform-specific URLs
    urls = {
        "windows": f"https://github.com/microsoft/onnxruntime/releases/download/v{onnx_version}/onnxruntime-win-x64-{onnx_version}.zip",
        "macos": f"https://github.com/microsoft/onnxruntime/releases/download/v{onnx_version}/onnxruntime-osx-x86_64-{onnx_version}.tgz",
        "macos-arm64": f"https://github.com/microsoft/onnxruntime/releases/download/v{onnx_version}/onnxruntime-osx-arm64-{onnx_version}.tgz",
        "linux": f"https://github.com/microsoft/onnxruntime/releases/download/v{onnx_version}/onnxruntime-linux-x64-{onnx_version}.tgz",
        "linux-aarch64": f"https://github.com/microsoft/onnxruntime/releases/download/v{onnx_version}/onnxruntime-linux-aarch64-{onnx_version}.tgz",
    }

    # Determine URL based on platform and architecture
    machine = platform.machine().lower()
    if platform_name == "windows":
        url = urls["windows"]
        archive_name = "onnxruntime.zip"
    elif platform_name == "macos":
        if machine in ["arm64", "aarch64"]:
            url = urls["macos-arm64"]
        else:
            url = urls["macos"]
        archive_name = "onnxruntime.tgz"
    else:  # linux
        if machine in ["arm64", "aarch64"]:
            url = urls["linux-aarch64"]
        else:
            url = urls["linux"]
        archive_name = "onnxruntime.tgz"

    # Download
    archive_path = build_dir / archive_name
    if not archive_path.exists():
        download_file(url, archive_path)

    # Extract
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_archive(archive_path, tmpdir)

        # Find the extracted directory
        extracted = list(Path(tmpdir).glob("onnxruntime-*"))
        if not extracted:
            raise RuntimeError("Failed to find extracted ONNX Runtime")

        onnx_src = extracted[0]

        # Copy files
        for src_dir in ["include", "lib"]:
            src = onnx_src / src_dir
            if src.exists():
                dst = onnx_dir / src_dir
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)


def copy_source_files():
    """Copy C++ source files from the main build"""
    print("Copying C++ source files...")

    src_dir = Path(__file__).parent
    cpp_dir = src_dir / "piper_phonemize" / "cpp" / "src"
    cpp_dir.mkdir(parents=True, exist_ok=True)

    # Try to copy from build directory
    build_src = (
        src_dir.parent.parent
        / "build"
        / "p"
        / "src"
        / "piper_phonemize_external"
        / "src"
    )

    if build_src.exists():
        for cpp_file in build_src.glob("*.cpp"):
            shutil.copy2(cpp_file, cpp_dir / cpp_file.name)
        for h_file in build_src.glob("*.hpp"):
            shutil.copy2(h_file, cpp_dir / h_file.name)
        print(f"Copied source files from {build_src}")
    else:
        # Download from GitHub as fallback
        print("Build directory not found, downloading from GitHub...")
        url = "https://github.com/rhasspy/piper-phonemize/archive/refs/heads/master.zip"
        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / "piper-phonemize.zip"
            download_file(url, zip_path)
            extract_archive(zip_path, tmpdir)

            src = Path(tmpdir) / "piper-phonemize-master" / "src"
            for cpp_file in src.glob("*.cpp"):
                shutil.copy2(cpp_file, cpp_dir / cpp_file.name)
            for h_file in src.glob("*.hpp"):
                shutil.copy2(h_file, cpp_dir / h_file.name)


def copy_data_files():
    """Copy espeak-ng-data files"""
    print("Copying espeak-ng-data files...")

    src_dir = Path(__file__).parent
    data_dir = src_dir / "piper_phonemize" / "data" / "espeak-ng-data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Try to copy from build directory
    build_data = (
        src_dir.parent.parent
        / "build"
        / "p"
        / "src"
        / "piper_phonemize_external"
        / "espeak-ng"
        / "espeak-ng-data"
    )

    if build_data.exists():
        shutil.copytree(build_data, data_dir, dirs_exist_ok=True)
        print(f"Copied data files from {build_data}")
    else:
        print("Data files will be copied during espeak-ng build")


def main():
    parser = argparse.ArgumentParser(
        description="Build dependencies for piper-phonemize-bundled"
    )
    parser.add_argument(
        "--platform",
        choices=["windows", "macos", "linux"],
        help="Target platform (auto-detect if not specified)",
    )
    parser.add_argument(
        "--skip-source-copy", action="store_true", help="Skip copying source files"
    )
    parser.add_argument(
        "--skip-data-copy", action="store_true", help="Skip copying data files"
    )

    args = parser.parse_args()

    # Detect platform if not specified
    if args.platform:
        platform_name = args.platform
    else:
        system = platform.system()
        if system == "Windows":
            platform_name = "windows"
        elif system == "Darwin":
            platform_name = "macos"
        elif system == "Linux":
            platform_name = "linux"
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

    print(f"Building dependencies for {platform_name}")

    # Setup build directory
    src_dir = Path(__file__).parent
    build_dir = src_dir / "build" / platform_name
    build_dir.mkdir(parents=True, exist_ok=True)

    # Copy source files
    if not args.skip_source_copy:
        copy_source_files()

    # Copy data files
    if not args.skip_data_copy:
        copy_data_files()

    # Build espeak-ng
    if platform_name == "windows":
        build_espeak_ng_windows(build_dir)
    else:
        build_espeak_ng_unix(build_dir, platform_name)

    # Download ONNX Runtime
    download_onnxruntime(build_dir, platform_name)

    print("Build dependencies completed successfully!")


if __name__ == "__main__":
    main()
