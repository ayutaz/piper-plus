"""
Minimal setup script for piper-phonemize
Builds without external espeak-ng/onnxruntime dependencies
"""

import sys
from pathlib import Path

from setuptools import find_packages, setup


try:
    from pybind11.setup_helpers import Pybind11Extension, build_ext
except ImportError:
    print("Error: pybind11 is required. Install it with: pip install pybind11")
    sys.exit(1)

__version__ = "1.2.0"

# Paths
_DIR = Path(__file__).parent
_CPP_DIR = _DIR / "piper_phonemize" / "cpp" / "src"

# Source files - only compile what we have
sources = []
for pattern in ["*.cpp"]:
    sources.extend([str(f) for f in _CPP_DIR.glob(pattern) if f.exists()])

if not sources:
    print("Warning: No C++ source files found. Building without extension.")
    ext_modules = []
else:
    # Create a minimal extension that compiles available sources
    ext_modules = [
        Pybind11Extension(
            "piper_phonemize._cpp",
            sources=sources,
            include_dirs=[str(_CPP_DIR)],
            define_macros=[
                ("VERSION_INFO", __version__),
            ],
            language="c++",
            cxx_std=17,
        ),
    ]

setup(
    name="piper-phonemize",
    version=__version__,
    description="Phonemization library for piper-plus",
    packages=find_packages(),
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext} if ext_modules else {},
    package_data={
        "piper_phonemize": [
            "data/**/*",
        ]
    },
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[
        "pybind11>=2.10.0",
    ],
)
