"""
Setup script for piper-phonemize on Windows
Based on Marc56K's piper-phonemize-win32 implementation
"""

import platform
import shutil
import sys
from pathlib import Path

from setuptools import find_packages, setup


try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
except ImportError:
    print("Error: pybind11 is required. Install it with: pip install pybind11")
    sys.exit(1)

# Version
__version__ = "1.2.0"

# Only proceed if on Windows
if platform.system() != "Windows":
    print(
        "This setup is for Windows only. Use pip install piper-phonemize for other platforms."
    )
    sys.exit(1)

# Paths
_DIR = Path(__file__).parent
_CPP_DIR = _DIR / "piper_phonemize" / "cpp" / "src"
_BUILD_DIR = _DIR / "build" / "windows"
_ESPEAK_DIR = _BUILD_DIR / "espeak-ng"
_ONNXRUNTIME_DIR = _BUILD_DIR / "onnxruntime"

# Ensure build directories exist
_BUILD_DIR.mkdir(parents=True, exist_ok=True)

# Windows-specific compiler flags
extra_compile_args = [
    "/utf-8",  # UTF-8 source encoding
    "/EHsc",  # Enable C++ exceptions
    "/std:c++17",  # C++17 standard
    "/O2",  # Optimize for speed
    "/MT",  # Static runtime library
    "/D_USE_MATH_DEFINES",  # Math constants
    "/DNOMINMAX",  # Prevent Windows.h min/max macros
]

# Libraries to link
libraries = [
    "espeak-ng",
    "onnxruntime",
    "ws2_32",  # Windows sockets
    "winmm",  # Windows multimedia
]

# Include directories
include_dirs = [
    str(_CPP_DIR),
    str(_ESPEAK_DIR / "include"),
    str(_ONNXRUNTIME_DIR / "include"),
]

# Library directories
library_dirs = [
    str(_ESPEAK_DIR / "lib"),
    str(_ONNXRUNTIME_DIR / "lib"),
]

# Source files - use relative paths for setuptools
sources = [
    "piper_phonemize/cpp/src/python.cpp",
    "piper_phonemize/cpp/src/phonemize.cpp",
    "piper_phonemize/cpp/src/phoneme_ids.cpp",
    "piper_phonemize/cpp/src/tashkeel.cpp",
]

# Check if sources exist
missing_sources = [src for src in sources if not (_DIR / src).exists()]
if missing_sources:
    print(f"Warning: Missing source files: {missing_sources}")
    print("Run prepare_sources.py to download them.")

# Define extension module
ext_modules = []
if not missing_sources:
    ext_modules = [
        Pybind11Extension(
            "piper_phonemize_cpp",
            sources=sources,
            include_dirs=include_dirs,
            library_dirs=library_dirs,
            libraries=libraries,
            extra_compile_args=extra_compile_args,
            define_macros=[
                ("VERSION_INFO", __version__),
            ],
            language="c++",
            cxx_std=17,
        ),
    ]

# Package data - include DLLs and data files
package_data = {
    "piper_phonemize": [
        "*.dll",
        "*.pyd",
        "data/espeak-ng-data/**/*",
    ]
}


# Custom build_ext to handle DLL copying
class BuildExtWindows(build_ext):
    def build_extensions(self):
        # Build C++ extension
        super().build_extensions()

        # Copy required DLLs to package directory
        package_dir = Path(self.build_lib) / "piper_phonemize"
        package_dir.mkdir(parents=True, exist_ok=True)

        # Copy espeak-ng DLL
        espeak_dll = _ESPEAK_DIR / "bin" / "espeak-ng.dll"
        if espeak_dll.exists():
            shutil.copy2(espeak_dll, package_dir)
            print(f"Copied {espeak_dll} to package")

        # Copy ONNX Runtime DLLs
        onnx_dlls = list((_ONNXRUNTIME_DIR / "lib").glob("*.dll"))
        for dll in onnx_dlls:
            shutil.copy2(dll, package_dir)
            print(f"Copied {dll} to package")

        # Copy espeak-ng-data directory
        espeak_data_src = _ESPEAK_DIR / "share" / "espeak-ng-data"
        espeak_data_dst = package_dir / "data" / "espeak-ng-data"
        if espeak_data_src.exists():
            if espeak_data_dst.exists():
                shutil.rmtree(espeak_data_dst)
            shutil.copytree(espeak_data_src, espeak_data_dst)
            print("Copied espeak-ng-data to package")


setup(
    name="piper-phonemize",
    version=__version__,
    author="Piper-Plus Contributors",
    author_email="",
    url="https://github.com/ayutaz/piper-plus",
    description="Phonemization library for piper-plus (Windows build)",
    long_description=open("README.md", encoding="utf-8").read()
    if Path("README.md").exists()
    else "",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    ext_modules=ext_modules,
    cmdclass={"build_ext": BuildExtWindows} if ext_modules else {},
    package_data=package_data,
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "pybind11>=2.10.0",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: C++",
        "Operating System :: Microsoft :: Windows",
    ],
    keywords="tts speech phonemization espeak piper windows",
)
