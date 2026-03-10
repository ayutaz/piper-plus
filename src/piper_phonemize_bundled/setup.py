"""
Setup script for piper-phonemize-bundled
Cross-platform build of piper-phonemize with bundled espeak-ng
"""

import os
import platform
import sys
from pathlib import Path

from setuptools import find_packages, setup


# Check for pybind11
try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
except ImportError:
    print("Error: pybind11 is required. Install it with: pip install pybind11")
    sys.exit(1)

# Version
__version__ = "1.2.0"

# Platform detection
system = platform.system()
machine = platform.machine()

# Paths
_DIR = Path(__file__).parent
_CPP_DIR = _DIR / "piper_phonemize" / "cpp" / "src"
_BUILD_DIR = _DIR / "build" / system.lower()
_ESPEAK_DIR = _BUILD_DIR / "espeak-ng"
_ONNXRUNTIME_DIR = _BUILD_DIR / "onnxruntime"

# Check if we're in cibuildwheel environment
IS_CIBUILDWHEEL = os.environ.get("CIBUILDWHEEL", "0") == "1"

# Platform-specific settings
extra_compile_args = []
extra_link_args = []
libraries = []
include_dirs = []
library_dirs = []

if system == "Windows":
    extra_compile_args = ["/utf-8", "/EHsc", "/std:c++17"]
    # Use static runtime to avoid dependency issues
    extra_compile_args.append(
        "/MT" if os.environ.get("CMAKE_BUILD_TYPE", "Release") == "Release" else "/MTd"
    )
    libraries = ["espeak-ng", "onnxruntime", "ws2_32", "winmm"]
    include_dirs = [
        str(_ESPEAK_DIR / "include"),
        str(_ONNXRUNTIME_DIR / "include"),
    ]
    library_dirs = [
        str(_ESPEAK_DIR / "lib"),
        str(_ONNXRUNTIME_DIR / "lib"),
    ]
elif system == "Darwin":  # macOS
    extra_compile_args = ["-std=c++17", "-stdlib=libc++"]
    libraries = ["espeak-ng", "onnxruntime"]
    include_dirs = [
        str(_ESPEAK_DIR / "include"),
        str(_ONNXRUNTIME_DIR / "include"),
    ]
    library_dirs = [
        str(_ESPEAK_DIR / "lib"),
        str(_ONNXRUNTIME_DIR / "lib"),
    ]
    # Add rpath for bundled libraries
    extra_link_args = [
        "-Wl,-rpath,@loader_path",
        "-framework",
        "CoreFoundation",
        "-framework",
        "CoreServices",
    ]
else:  # Linux
    extra_compile_args = ["-std=c++17"]
    libraries = ["espeak-ng", "onnxruntime"]
    include_dirs = [
        str(_ESPEAK_DIR / "include"),
        str(_ONNXRUNTIME_DIR / "include"),
    ]
    library_dirs = [
        str(_ESPEAK_DIR / "lib"),
        str(_ONNXRUNTIME_DIR / "lib"),
    ]
    # Add rpath for bundled libraries
    extra_link_args = ["-Wl,-rpath,$ORIGIN"]

# Source files
sources = [
    str(_CPP_DIR / "python.cpp"),
    str(_CPP_DIR / "phonemize.cpp"),
    str(_CPP_DIR / "phoneme_ids.cpp"),
    str(_CPP_DIR / "tashkeel.cpp"),
]

# Check if source files exist (for development)
if not IS_CIBUILDWHEEL and not all(Path(src).exists() for src in sources):
    print("Warning: C++ source files not found. They will be copied during CI build.")
    sources = []  # Empty sources for now

# Define extension module
ext_modules = []
if sources:  # Only create extension if we have sources
    ext_modules = [
        Pybind11Extension(
            "piper_phonemize._cpp",
            sources=sources,
            include_dirs=include_dirs,
            library_dirs=library_dirs,
            libraries=libraries,
            extra_compile_args=extra_compile_args,
            extra_link_args=extra_link_args,
            define_macros=[
                ("VERSION_INFO", __version__),
                ("_USE_MATH_DEFINES", None),  # Windows math constants
            ],
            language="c++",
            cxx_std=17,
        ),
    ]

# Package data
package_data = {
    "piper_phonemize": [
        "data/espeak-ng-data/**/*",
    ]
}

# Add platform-specific libraries to package
if system == "Windows":
    package_data["piper_phonemize"].extend(["*.dll", "*.pyd"])
elif system == "Darwin":
    package_data["piper_phonemize"].extend(["*.dylib", "*.so"])
else:
    package_data["piper_phonemize"].extend(["*.so", "*.so.*"])

setup(
    name="piper-phonemize",
    version=__version__,
    author="Piper-Plus Contributors",
    author_email="",
    url="https://github.com/ayutaz/piper-plus",
    description="Phonemization library for piper-plus with bundled espeak-ng (Windows/macOS/Linux)",
    long_description=open("README.md", encoding="utf-8").read()
    if Path("README.md").exists()
    else "",
    long_description_content_type="text/markdown",
    packages=find_packages(),
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext} if ext_modules else {},
    package_data=package_data,
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "pybind11>=2.10.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "wheel",
            "build",
        ],
    },
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
        "Operating System :: MacOS",
        "Operating System :: POSIX :: Linux",
    ],
    keywords="tts speech phonemization espeak piper",
)
