from pathlib import Path

from .voice import PiperVoice


# Read version from VERSION file
_VERSION_FILE = Path(__file__).parent.parent.parent.parent / "VERSION"
if _VERSION_FILE.exists():
    __version__ = _VERSION_FILE.read_text().strip()
else:
    __version__ = "unknown"

__all__ = [
    "PiperVoice",
    "__version__",
]
