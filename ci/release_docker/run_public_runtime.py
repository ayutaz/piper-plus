"""Verify published release bytes and actual consumers on a hosted runner."""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
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


SOURCE = os.environ["RELEASE_SOURCE"]
VERSION = os.environ["RELEASE_VERSION"]
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


def verify_and_pull(reference, proof_path, runner=subprocess.run):
    """Verify and execute the same immutable published image."""
    if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", reference):
        raise ValueError("An immutable image digest reference is required")
    repository = os.environ["GITHUB_REPOSITORY"]
    result = runner(
        [
            "cosign",
            "verify",
            "--certificate-identity",
            f"https://github.com/{repository}/.github/workflows/docker-build.yml@refs/tags/docker-v{VERSION}",
            "--certificate-oidc-issuer",
            "https://token.actions.githubusercontent.com",
            "--certificate-github-workflow-sha",
            SOURCE,
            reference,
        ],
        check=True,
        capture_output=True,
        timeout=180,
    )
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_bytes(result.stdout)
    runner(
        ["docker", "pull", "--platform", "linux/amd64", reference],
        check=True,
        timeout=600,
    )


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
        "-e",
        f"RELEASE_SOURCE={SOURCE}",
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
            "PIPER_EXPECTED_SCRIPT_SHA="
            + hashlib.sha256(
                (Path("docker/python-inference/inference.py")).read_bytes()
            ).hexdigest(),
            "--entrypoint",
            "python",
            reference,
            "-c",
            "import runpy; runpy.run_path('/proof/verify-api-runtime.py', run_name='__main__')",
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
    hub_repository = f"{os.environ['DOCKERHUB_OWNER']}/{HUB_NAMES[name]}"
    for attempt in range(24):
        try:
            hub_fetch = hub_fetcher(hub_repository)
            hub = resolve_image(hub_repository, VERSION, SOURCE, arches, hub_fetch)
            break
        except urllib.error.HTTPError as error:
            if error.code not in {401, 404} or attempt == 23:
                raise
            print("Waiting for the public DockerHub release tag", flush=True)
            time.sleep(15)
    hub["image"] = f"docker.io/{hub_repository}:{VERSION}"
    hub["reference"] = f"docker.io/{hub_repository}@{hub['digest']}"
    assert (
        "sha256:" + hashlib.sha256(hub_fetch("/manifests/latest")).hexdigest()
        == hub["digest"]
    ), "DockerHub latest differs from release"
    (PROOF / "public-resolution.json").write_text(
        json.dumps([ghcr, hub], indent=2) + "\n"
    )
    assert ghcr["digest"] == hub["digest"], "Registries contain different image bytes"
    fetch_model()
    for registry, image in (("ghcr", ghcr), ("dockerhub", hub)):
        reference = image["reference"]
        verify_and_pull(reference, Path("signature-proof") / f"{name}-{registry}.json")
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
