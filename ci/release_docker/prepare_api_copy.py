"""Fail closed before copying the already verified immutable release image."""

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from resolve_docker_release_images import public_fetcher, resolve_image


assert os.environ.get("GITHUB_ACTIONS") == "true", "Hosted runner execution only"
image = resolve_image(
    "ayutaz/piper-plus/python-inference",
    "2.0.0",
    "71acf30c8e23e17b639fd40a8117415c3df55c0a",
    {"amd64"},
    public_fetcher("ayutaz/piper-plus/python-inference"),
)
assert (
    image["digest"]
    == "sha256:90674b00ba5b8f2c93f561b3229193a9591d6a8d4cea6c6139dc4efe270aca5b"
)
proof = Path("public-docker-copy-proof")
proof.mkdir()
(proof / "source.json").write_text(json.dumps(image, indent=2) + "\n")
print(image["reference"])
