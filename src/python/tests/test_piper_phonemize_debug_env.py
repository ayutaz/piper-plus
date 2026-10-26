"""The bundled piper_phonemize module reads the v2.0 env name for debug output.

v2.0 renamed the public env vars from ``PIPER_*`` to ``PIPER_PLUS_*`` with no
fallback to the old names (docs/migration/v1.12-to-v2.0.md). The bundled
module still read ``PIPER_PHONEMIZE_DEBUG`` while
docs/getting-started/environment-variables.md documents
``PIPER_PLUS_PHONEMIZE_DEBUG``.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parents[2] / "piper_phonemize_bundled"

# Imports the bundled module from its source directory. The C++ extension is
# usually absent, which the module handles; the debug block runs either way.
_IMPORT = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "import piper_phonemize; print('imported', piper_phonemize.__file__)"
)


def _import_with_env(extra_env: dict[str, str]) -> str:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("PIPER_PHONEMIZE_DEBUG", "PIPER_PLUS_PHONEMIZE_DEBUG")
    }
    env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT, str(MODULE_DIR)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    # The module must be the bundled source, not an installed copy.
    assert str(MODULE_DIR) in result.stdout
    return result.stdout


@pytest.mark.unit
def test_plus_name_enables_debug_output():
    out = _import_with_env({"PIPER_PLUS_PHONEMIZE_DEBUG": "1"})
    assert "piper_phonemize version:" in out


@pytest.mark.unit
def test_legacy_name_is_not_read():
    out = _import_with_env({"PIPER_PHONEMIZE_DEBUG": "1"})
    assert "piper_phonemize version:" not in out


@pytest.mark.unit
def test_no_debug_output_by_default():
    out = _import_with_env({})
    assert "piper_phonemize version:" not in out
