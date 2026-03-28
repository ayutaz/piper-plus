from importlib.metadata import PackageNotFoundError, version

from .voice import PiperVoice


try:
    __version__ = version("piper-plus")
except PackageNotFoundError:
    # Fallback for development (running from source tree)
    from pathlib import Path

    _VERSION_FILE = Path(__file__).parent.parent.parent.parent / "VERSION"
    __version__ = (
        _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "unknown"
    )

__all__ = [
    "PiperVoice",
    "__version__",
]
