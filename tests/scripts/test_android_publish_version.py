"""Android publications take their version from android/gradle.properties only.

Both modules read ``VERSION_NAME`` (gradle.properties, or
``ORG_GRADLE_PROJECT_VERSION_NAME`` in release-kotlin-g2p.yml) and fell back to
a literal when it was missing: ``0.1.0`` in ``:piper-plus`` and ``1.0.0`` in
``:piper-plus-g2p``, while gradle.properties says ``1.0.1``. The literals never
matched the real version, so a build without the property would publish a
stale one instead of failing.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANDROID = ROOT / "android"
BUILD_SCRIPTS = sorted(ANDROID.glob("*/build.gradle.kts"))

VERSION_READ = re.compile(r'findProperty\(\s*"VERSION_NAME"\s*\)[^\n]*')
LITERAL_FALLBACK = re.compile(r'\?:\s*"[^"]*"')


def test_gradle_properties_defines_version_name():
    text = (ANDROID / "gradle.properties").read_text(encoding="utf-8")
    assert re.search(r"^VERSION_NAME=\d+\.\d+\.\d+\s*$", text, re.MULTILINE)


def test_both_modules_are_checked():
    names = {path.parent.name for path in BUILD_SCRIPTS}
    assert {"piper-plus", "piper-plus-g2p"} <= names


def test_publish_version_has_no_literal_fallback():
    offenders = []
    for path in BUILD_SCRIPTS:
        text = path.read_text(encoding="utf-8")
        for match in VERSION_READ.finditer(text):
            if LITERAL_FALLBACK.search(match.group(0)):
                offenders.append(f"{path.relative_to(ROOT)}: {match.group(0).strip()}")
    assert not offenders, offenders


def test_each_module_reads_version_name():
    for path in BUILD_SCRIPTS:
        text = path.read_text(encoding="utf-8")
        if "publishing" in text or "mavenPublishing" in text:
            assert '"VERSION_NAME"' in text, path
