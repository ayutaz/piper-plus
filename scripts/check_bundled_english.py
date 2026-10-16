"""Verify/reproduce the Apache-2.0 English backend from a pinned PyPI wheel.

Run without arguments to verify both independently distributable packages.
To reproduce the import, pass --wheel g2p_en-2.1.0-py3-none-any.whl.
No upstream code is executed by this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WHEEL_SHA256 = "2a7aabf1fc7f270fcc3349881407988c9245173c2413debbe5432f4a4f31319f"
WHEEL_URL = "https://files.pythonhosted.org/packages/d7/d9/b77dc634a7a0c0c97716ba97dd0a28cbfa6267c96f359c4f27ed71cbd284/g2p_en-2.1.0-py3-none-any.whl"
TARGETS = (
    "src/python/g2p/piper_plus_g2p/_vendor/g2p_en",
    "src/python_run/piper_plus/_vendor/g2p_en",
)
MEMBERS = {
    name: f"g2p_en/{name}"
    for name in (
        "__init__.py",
        "g2p.py",
        "expand.py",
        "checkpoint20.npz",
        "homographs.en",
    )
}
MEMBERS["LICENSE.txt"] = "g2p_en-2.1.0.dist-info/LICENSE.txt"
UPSTREAM_SHA256 = {
    "__init__.py": "36ffae3e8f2cad9d285131c78963f690327f5046b5273dfecc52707659be949d",
    "g2p.py": "fc2548b855e102f774506a6afe4f4bc88424229b69701ab6040aa16710ddff3a",
    "expand.py": "b31f9f2173280f4479de1272d57540382d64496662ef127cf4d05af5a49d70db",
    "checkpoint20.npz": "b8af35e4596d8dd5836dfd3fe9b2ba4f97b9c311efe8879544cbcfcbd566d8c6",
    "homographs.en": "0403edcc6aefe8945f8987be398279fd98bf6b767e54b741331d3bc99a307071",
    "LICENSE.txt": "b40930bbcf80744c86c46a12bc9da056641d722716c378f5659b9e555ef833e1",
}
TACOTRON_LICENSE = 'Copyright (c) 2017 Keith Ito\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the "Software"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in\nall copies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN\nTHE SOFTWARE.\n'
TACOTRON_LICENSE_URL = "https://raw.githubusercontent.com/keithito/tacotron/d26c763342518d4e432e9c4036a1aff3b4fdaa1e/LICENSE"
NOTICE = """Bundled g2p-en 2.1.0 (Kyubyong Park and Jongseok Kim).
Upstream: https://github.com/Kyubyong/g2p
License: Apache-2.0; see LICENSE.txt.

piper-plus bundles the original inference source, checkpoint and homograph
table under private package namespaces. Data and license are byte-identical
to the pinned PyPI wheel. g2p.py uses a raw regex literal to avoid Python's
invalid-escape SyntaxWarning; its regex value and pronunciation are unchanged.
Distance and its GPL code are not included. The
upstream distribution's unused Distance requirement is not adopted.
NumPy, NLTK and inflect remain explicit dependencies. NLTK corpus data is
not bundled here; its existing installation and licensing still apply.
expand.py derives from Keith Ito's MIT-licensed Tacotron number normalizer.
Its original copyright/permission notice is retained in TACOTRON-LICENSE.txt.
"""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def import_wheel(wheel: Path) -> None:
    if digest(wheel.read_bytes()) != WHEEL_SHA256:
        raise ValueError("Untrusted g2p-en wheel: SHA256 mismatch")
    with zipfile.ZipFile(wheel) as archive:
        payload = {name: archive.read(member) for name, member in MEMBERS.items()}
    if {name: digest(data) for name, data in payload.items()} != UPSTREAM_SHA256:
        raise ValueError("Upstream file hashes differ")
    payload["g2p.py"] = payload["g2p.py"].replace(
        b're.sub("[^ a-z\'.,?!\\-]",', b're.sub(r"[^ a-z\'.,?!\\-]",'
    )
    payload["TACOTRON-LICENSE.txt"] = TACOTRON_LICENSE.encode("utf-8")
    manifest = {
        "upstream": "g2p-en",
        "version": "2.1.0",
        "license": "Apache-2.0",
        "wheel_sha256": WHEEL_SHA256,
        "wheel_url": WHEEL_URL,
        "additional_license_url": TACOTRON_LICENSE_URL,
        "upstream_files": UPSTREAM_SHA256,
        "files": {name: digest(data) for name, data in payload.items()},
    }
    for relative in TARGETS:
        target = ROOT / relative
        target.mkdir(parents=True, exist_ok=True)
        (target.parent / "__init__.py").write_text(
            '"""Private third-party implementations; see their license and provenance."""\n',
            encoding="utf-8",
            newline="\n",
        )
        for name, data in payload.items():
            (target / name).write_bytes(data)
        (target / "NOTICE.txt").write_text(NOTICE, encoding="utf-8", newline="\n")
        (target / "provenance.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )


def check(root: Path = ROOT) -> None:
    reference = None
    for relative in TARGETS:
        target = root / relative
        manifest = json.loads((target / "provenance.json").read_text(encoding="utf-8"))
        expected = dict(UPSTREAM_SHA256)
        expected["TACOTRON-LICENSE.txt"] = (
            "f89accd9d66f6a011f19997d7a21cf71a35ffe2e2d0911b5460cbd0cab52a581"
        )
        expected["g2p.py"] = (
            "429862b36b7d6d1068257250aa40ff92d97fd68324af03e9bf12eb05edc60509"
        )
        if (
            manifest.get("upstream") != "g2p-en"
            or manifest.get("version") != "2.1.0"
            or manifest.get("license") != "Apache-2.0"
            or manifest.get("wheel_url") != WHEEL_URL
            or manifest.get("additional_license_url") != TACOTRON_LICENSE_URL
            or manifest["wheel_sha256"] != WHEEL_SHA256
            or manifest["upstream_files"] != UPSTREAM_SHA256
            or manifest["files"] != expected
        ):
            raise ValueError(f"Unexpected provenance: {relative}")
        for name, expected in manifest["files"].items():
            if digest((target / name).read_bytes()) != expected:
                raise ValueError(f"Bundled English asset changed: {relative}/{name}")
        if (target / "NOTICE.txt").read_text(encoding="utf-8") != NOTICE:
            raise ValueError(f"Missing attribution: {relative}")
        payload = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
        if set(payload) != {
            *MEMBERS,
            "TACOTRON-LICENSE.txt",
            "NOTICE.txt",
            "provenance.json",
        }:
            raise ValueError(f"Unexpected bundled files: {relative}")
        if reference is not None and payload != reference:
            raise ValueError("Training/runtime English bundles differ")
        reference = payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    if args.wheel:
        import_wheel(args.wheel)
    check()
    print(
        "Bundled English: pinned hashes, Apache license, attribution and mirrors verified"
    )


if __name__ == "__main__":
    main()
