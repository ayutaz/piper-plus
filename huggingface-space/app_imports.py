"""Optional imports for text-to-phoneme conversion"""

# These imports are optional and loaded dynamically
# to allow the app to work with fallback methods
try:
    import importlib.util

    if importlib.util.find_spec("pyopenjtalk") is not None:
        PYOPENJTALK_AVAILABLE = True
    else:
        PYOPENJTALK_AVAILABLE = False
except ImportError:
    PYOPENJTALK_AVAILABLE = False

try:
    import importlib.util

    if importlib.util.find_spec("espeak_phonemizer") is not None:
        ESPEAK_AVAILABLE = True
    else:
        ESPEAK_AVAILABLE = False
except ImportError:
    ESPEAK_AVAILABLE = False

try:
    import pypinyin  # noqa: F401

    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False

try:
    import g2pk2  # noqa: F401

    HAS_G2PK2 = True
except ImportError:
    HAS_G2PK2 = False
