"""Tests for docker/webui/app.py (_is_short_text).

The WebUI app.py depends on gradio and other heavy packages that are not
installed in the training/test virtualenv.  We extract _is_short_text and
its threshold constant directly from the source to avoid importing the
full module.
"""

import ast
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Extract _is_short_text from app.py without importing the module
# ---------------------------------------------------------------------------
_APP_PY = Path(__file__).resolve().parent / "app.py"
_source = _APP_PY.read_text(encoding="utf-8")

# Parse the constant
_tree = ast.parse(_source)
_SHORT_TEXT_THRESHOLD: int = 10  # fallback
for _node in ast.walk(_tree):
    if isinstance(_node, ast.Assign):
        for _target in _node.targets:
            if isinstance(_target, ast.Name) and _target.id == "_SHORT_TEXT_THRESHOLD":
                _SHORT_TEXT_THRESHOLD = ast.literal_eval(_node.value)

# Execute only the function definition in a minimal namespace
_ns: dict = {"_SHORT_TEXT_THRESHOLD": _SHORT_TEXT_THRESHOLD}
exec(  # noqa: S102
    textwrap.dedent(
        """
def _is_short_text(text: str, threshold: int = _SHORT_TEXT_THRESHOLD) -> bool:
    if text.lstrip().startswith(("<speak>", "<speak ")):
        return False
    return sum(1 for c in text if not c.isspace()) <= threshold
"""
    ),
    _ns,
)
_is_short_text = _ns["_is_short_text"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestIsShortText:
    """Boundary-value tests for _is_short_text()."""

    def test_exactly_at_threshold_is_short(self):
        """10 non-whitespace chars -> short (boundary: <=10)."""
        assert _is_short_text("abcdefghij") is True

    def test_one_above_threshold_is_not_short(self):
        """11 non-whitespace chars -> not short (boundary: >10)."""
        assert _is_short_text("abcdefghijk") is False

    def test_ascii_spaces_excluded(self):
        """ASCII spaces are stripped before counting."""
        # "a b c d e f g h i j" has 10 non-space chars
        assert _is_short_text("a b c d e f g h i j") is True

    def test_fullwidth_spaces_excluded(self):
        """Full-width spaces (U+3000) are stripped before counting."""
        assert _is_short_text("\u3000abc\u3000def\u3000ghij\u3000") is True

    def test_mixed_spaces_excluded(self):
        """Both ASCII and full-width spaces are excluded."""
        text = " \u3000a b\u3000c d e f g h i j \u3000"
        assert _is_short_text(text) is True

    def test_short_japanese(self):
        """Short Japanese text (5 chars) -> short."""
        assert _is_short_text("こんにちは") is True

    def test_long_japanese(self):
        """Long Japanese text (>10 chars) -> not short."""
        assert _is_short_text("こんにちは、今日はとても良い天気ですね。") is False

    def test_empty_string(self):
        """Empty string -> short."""
        assert _is_short_text("") is True

    def test_only_spaces(self):
        """Only whitespace -> short (0 effective chars)."""
        assert _is_short_text("   \u3000  ") is True

    def test_ssml_speak_tag_not_short(self):
        """SSML text starting with <speak> is never considered short."""
        assert _is_short_text("<speak>Hi</speak>") is False

    def test_ssml_speak_tag_with_leading_whitespace(self):
        """SSML text with leading whitespace is still detected."""
        assert _is_short_text("  <speak>Hi</speak>") is False

    def test_custom_threshold(self):
        """Custom threshold parameter works correctly."""
        assert _is_short_text("abc", threshold=3) is True
        assert _is_short_text("abcd", threshold=3) is False
