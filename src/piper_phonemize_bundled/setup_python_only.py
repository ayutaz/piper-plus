"""
Python-only setup for piper-phonemize (for CI testing)
Provides stub implementations of required functions
"""

from setuptools import find_packages, setup


__version__ = "1.2.0"

setup(
    name="piper-phonemize",
    version=__version__,
    description="Phonemization library for piper-plus (Python-only stub)",
    packages=find_packages(),
    package_data={
        "piper_phonemize": ["*.py"],
    },
    include_package_data=True,
    python_requires=">=3.11",
    install_requires=[],
)
