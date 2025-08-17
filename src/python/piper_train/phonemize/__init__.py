# Mark submodule for phonemizers

from .custom_dict import (  # noqa: F401
    CustomDictionary,
    apply_custom_dictionary,
    create_default_dictionary,
)

# Import Japanese phonemizer only if pyopenjtalk is available
try:
    from .japanese import phonemize_japanese  # noqa: F401
except ImportError:
    # pyopenjtalk not available (e.g., on Windows)
    phonemize_japanese = None
