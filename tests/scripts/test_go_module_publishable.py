"""``src/go/go.mod`` must stay installable with ``go install ...@version``.

``src/go/v0.3.0`` shipped with ``phonemize v0.0.0`` and
``replace github.com/ayutaz/piper-plus/src/go/phonemize => ./phonemize``.
``go install github.com/ayutaz/piper-plus/src/go/cmd/piper-plus@v0.3.0``
then fails: Go refuses a ``replace`` in the main module of
``go install pkg@version``, and ``v0.0.0`` is not a published version, so
``go get`` users had to pin phonemize by hand as well.

Local development joins both modules through ``src/go/go.work`` instead, so
the published ``go.mod`` can require a real phonemize version. Before tagging
``src/go/v<X.Y.Z>``, raise that requirement to the phonemize version the code
needs (publish phonemize first; see CONTRIBUTING.md, "Release order").
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GO_ROOT = REPO_ROOT / "src" / "go"
PHONEMIZE = "github.com/ayutaz/piper-plus/src/go/phonemize"


def _go_mods() -> list[Path]:
    return sorted(GO_ROOT.rglob("go.mod"))


def _without_comments(text: str) -> str:
    return re.sub(r"//.*", "", text)


@pytest.mark.parametrize("go_mod", _go_mods(), ids=lambda p: p.parent.relative_to(REPO_ROOT).as_posix())
def test_go_mod_has_no_replace(go_mod: Path):
    text = _without_comments(go_mod.read_text(encoding="utf-8"))
    assert not re.search(r"^\s*replace\b", text, re.MULTILINE), (
        f"{go_mod.relative_to(REPO_ROOT)} has a replace directive; "
        "`go install ...@version` refuses it. Use src/go/go.work for local development."
    )


def _required_phonemize() -> str:
    text = _without_comments((GO_ROOT / "go.mod").read_text(encoding="utf-8"))
    match = re.search(rf"^\s*{re.escape(PHONEMIZE)}\s+(v\S+)", text, re.MULTILINE)
    assert match, f"src/go/go.mod does not require {PHONEMIZE}"
    return match.group(1)


def test_src_go_requires_a_released_phonemize_version():
    version = _required_phonemize()
    assert re.fullmatch(r"v\d+\.\d+\.\d+", version), version
    assert version != "v0.0.0", "v0.0.0 is not a published phonemize version"


def test_required_phonemize_version_is_tagged():
    """Checked only when the checkout has the module tags (CI checkouts often do not)."""
    try:
        tags = subprocess.run(
            ["git", "tag", "--list", "src/go/phonemize/v*"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    if not tags:
        pytest.skip("no src/go/phonemize/v* tags in this checkout")
    version = _required_phonemize()
    assert f"src/go/phonemize/{version}" in tags, (
        f"src/go/go.mod requires phonemize {version}, but tag src/go/phonemize/{version} does not exist"
    )
