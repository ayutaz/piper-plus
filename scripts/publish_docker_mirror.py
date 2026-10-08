"""Mirror a built immutable index and independently verify each public tag."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


def publish(source, digest, tags, proof_dir, runner=subprocess.run):
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Invalid source digest")
    if not tags:
        raise ValueError("No Docker Hub tags to publish")
    proof_dir.mkdir(parents=True, exist_ok=True)
    for index, tag in enumerate(tags):
        if not re.fullmatch(r"[a-z0-9_-]+/[a-z0-9_-]+:[A-Za-z0-9_.-]+", tag):
            raise ValueError("Invalid destination tag")
        destination = f"docker://docker.io/{tag}"
        runner(
            [
                "skopeo",
                "copy",
                "--all",
                "--preserve-digests",
                "--authfile",
                str(Path.home() / ".docker/config.json"),
                f"docker://{source}@{digest}",
                destination,
            ],
            check=True,
            timeout=600,
        )
        raw = runner(
            ["skopeo", "inspect", "--raw", destination],
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
        actual = "sha256:" + hashlib.sha256(raw).hexdigest()
        if actual != digest:
            raise ValueError(f"Remote digest differs for {tag}: {actual}")
        (proof_dir / f"mirror-{index}.json").write_text(
            json.dumps(
                {
                    "source": source,
                    "digest": digest,
                    "destination": tag,
                    "remote_digest": actual,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    publish(
        os.environ["SOURCE_IMAGE"],
        os.environ["SOURCE_DIGEST"],
        os.environ["DESTINATION_TAGS"].splitlines(),
        Path("docker-mirror-proof"),
    )
