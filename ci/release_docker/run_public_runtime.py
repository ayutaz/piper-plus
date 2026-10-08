"""Verify published release bytes and actual consumers on a hosted runner."""

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from resolve_docker_release_images import (
    ACCEPT,
    expected_architectures,
    public_fetcher,
    resolve_image,
)


SOURCE = "71acf30c8e23e17b639fd40a8117415c3df55c0a"
VERSION = "2.0.0"
HUB_NAMES = {
    "python-inference": "piper-plus-api",
    "webui": "piper-plus-webui",
    "wyoming": "wyoming-piper-plus",
}
PROOF = Path("public-docker-proof").resolve()
MODEL = Path(os.environ["RUNNER_TEMP"]) / "release-model"
SCRIPTS = Path(__file__).resolve().parent


def command(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=180, **kwargs)


def hub_fetcher(repository):
    query = urllib.parse.urlencode(
        {"service": "registry.docker.io", "scope": f"repository:{repository}:pull"}
    )
    with urllib.request.urlopen(
        f"https://auth.docker.io/token?{query}", timeout=30
    ) as response:
        token = json.load(response)["token"]

    def fetch(path):
        request = urllib.request.Request(
            f"https://registry-1.docker.io/v2/{repository}{path}",
            headers={"Accept": ACCEPT, "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    return fetch


def fetch_model():
    MODEL.mkdir()
    base = "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/36b59c825c36bd386b8960cf3f604382f52f2a87/"
    for remote, local, digest in (
        (
            "tsukuyomi-chan-6lang-fp16.onnx",
            "model.onnx",
            "5289e9b6eaf21080803b7fe1c4dc85b5491d4c216121207a41df18dd5f68e5d7",
        ),
        (
            "config.json",
            "published-hf-config.json",
            "516058f405ec914140f34832a9d8bb5d8272ba62af9bc7ffb29349715a539780",
        ),
    ):
        urllib.request.urlretrieve(base + remote, MODEL / local)
        assert hashlib.sha256((MODEL / local).read_bytes()).hexdigest() == digest
    (MODEL / "model.onnx.json").write_bytes(
        (MODEL / "published-hf-config.json").read_bytes()
    )


def runtime(name, reference, directory):
    directory.mkdir()
    directory.chmod(0o777)
    common = [
        "--network",
        "none",
        "-e",
        "PIPER_PLUS_DISABLE_CACHE=1",
        "-v",
        f"{MODEL}:/models:ro",
        "-v",
        f"{MODEL}:/model:ro",
        "-v",
        f"{directory}:/output",
        "-v",
        f"{SCRIPTS}:/proof:ro",
    ]
    if name == "python-inference":
        command(
            "docker",
            "run",
            "--rm",
            *common,
            "-e",
            "PIPER_EXPECTED_SCRIPT_SHA=f477708cd7f17c2038e18dcc480b36d00eef3b05a9e9bdd7cb3c5c741cad767d",
            "--entrypoint",
            "python",
            reference,
            "-c",
            "import runpy; runpy.run_path('/proof/verify-corrected-gpu-image-cpu-runtime.py', run_name='__main__')",
        )
        return
    if name == "webui":
        command(
            "docker",
            "run",
            "--rm",
            *common,
            "--entrypoint",
            "python",
            reference,
            "-c",
            "import runpy; runpy.run_path('/proof/verify-webui-runtime.py', run_name='__main__')",
        )
        start_args = []
        check_script = "/proof/verify-webui-http-runtime.py"
        port = 7860
    else:
        start_args = [
            "--model",
            "/models/model.onnx",
            "--config",
            "/models/published-hf-config.json",
            "--uri",
            "tcp://0.0.0.0:10200",
        ]
        check_script = "/proof/verify-wyoming-runtime.py"
        port = 10200
    container = command(
        "docker",
        "run",
        "-d",
        *common,
        reference,
        *start_args,
        capture_output=True,
        text=True,
    ).stdout.strip()
    try:
        for _ in range(30):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "python",
                    "-c",
                    f"import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1', {port})); s.close()",
                ],
                capture_output=True,
                check=False,
                timeout=10,
            )
            if ready.returncode == 0:
                break
            time.sleep(2)
        else:
            raise RuntimeError("Published service failed to become ready")
        command("docker", "exec", container, "python", check_script)
    finally:
        logs = subprocess.run(
            ["docker", "logs", container],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        (directory / "service.log").write_text(logs.stdout + logs.stderr)
        subprocess.run(["docker", "rm", "-f", container], check=True, timeout=15)


def main():
    name = sys.argv[1]
    assert name in HUB_NAMES
    assert os.environ.get("GITHUB_ACTIONS") == "true", "Hosted runner execution only"
    PROOF.mkdir()
    arches = expected_architectures(name, False)
    ghcr = resolve_image(
        f"ayutaz/piper-plus/{name}",
        VERSION,
        SOURCE,
        arches,
        public_fetcher(f"ayutaz/piper-plus/{name}"),
    )
    hub_repository = f"ayousanz/{HUB_NAMES[name]}"
    hub_fetch = hub_fetcher(hub_repository)
    hub = resolve_image(hub_repository, VERSION, SOURCE, arches, hub_fetch)
    hub["image"] = f"docker.io/{hub_repository}:{VERSION}"
    hub["reference"] = f"docker.io/{hub_repository}@{hub['digest']}"
    assert (
        "sha256:" + hashlib.sha256(hub_fetch("/manifests/latest")).hexdigest()
        == hub["digest"]
    ), "DockerHub latest differs from release"
    (PROOF / "public-resolution.json").write_text(
        json.dumps([ghcr, hub], indent=2) + "\n"
    )
    fetch_model()
    for registry, image in (("ghcr", ghcr), ("dockerhub", hub)):
        reference = image["reference"]
        # Pull resolves actual public bytes; the Docker engine validates layer digests.
        subprocess.run(
            ["docker", "pull", "--platform", "linux/amd64", reference],
            check=True,
            timeout=600,
        )
        runtime(name, reference, PROOF / registry)
        print(
            json.dumps(
                {
                    "registry": registry,
                    "image": image["image"],
                    "digest": image["digest"],
                    "source": SOURCE,
                    "actual_runtime": "pass",
                }
            )
        )
    (PROOF / "verification.json").write_text(
        json.dumps(
            {
                "images": [ghcr, hub],
                "actual_runtime": "pass",
                "gpu_hardware_tested": False,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
