"""Check a fresh anonymous download, or rehearse the same consumer on local copies."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import requests
from huggingface_hub import HfApi

from scripts.tsukuyomi_release.publish_bundle import REPO, ROOT, metadata


DEFAULT_WORKSPACE = ROOT
sys.stdout.reconfigure(encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def anonymous_metadata(session, repo, revision):
    response = session.get(
        f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true",
        timeout=30,
    )
    response.raise_for_status()
    if not "Authorization" not in response.request.headers:
        raise ValueError("release verification failed")
    value = response.json()
    if not value["sha"] == revision:
        raise ValueError("release verification failed")
    return value


def verify_retention(session, revision, workspace):
    before = read_json(workspace / "publication-before-state.json")
    target = anonymous_metadata(session, REPO, revision)
    if not (target["private"] is False and target["gated"] is False):
        raise ValueError("release verification failed")
    after_files = {file["rfilename"]: file for file in target["siblings"]}
    for name, old in before["target"]["files"].items():
        if name == "README.md":
            continue
        after = after_files[name]
        if not (after["size"] == old["bytes"] and after["blobId"] == old["blob_id"]):
            raise ValueError(name)
        if not (after.get("lfs") or {}).get("sha256") == old["lfs_sha256"]:
            raise ValueError(name)
    api = HfApi()
    retained = []
    for old in before["preserved_repositories"]:
        if not metadata(api.model_info(old["repo"], files_metadata=True)) == old:
            raise ValueError(old["repo"])
        retained.append(old["repo"])
    return {
        "legacy_files_unchanged": True,
        "research_and_base_repositories_unchanged": retained,
    }


def run_consumer(target):
    consumer = (
        Path(__file__).resolve().parents[2]
        / "output/public-base-release-20261010/consumer-env/Scripts/python.exe"
    )
    code = "import importlib.metadata\nimport json\nimport sys\nimport wave\nfrom pathlib import Path\nfrom piper_plus.voice import PiperVoice\nif not importlib.metadata.version('piper-plus') == '2.0.0':\n    raise ValueError('release verification failed')\nroot = Path(sys.argv[1])\nrelease = root / 'releases/zs-v1'\nvoice = PiperVoice.load(release / 'tsukuyomi.onnx', config_path=release / 'tsukuyomi.onnx.json')\nif not 'speaker_embedding' not in {value.name for value in voice.session.get_inputs()}:\n    raise ValueError('release verification failed')\nwith wave.open(str(root / 'normal-api.wav'), 'wb') as wav:\n    voice.synthesize('こんにちは。今日は良い天気ですね。', wav, noise_scale=0.4, noise_w=0.5, length_scale=1.0)\nwith wave.open(str(root / 'normal-api.wav'), 'rb') as wav:\n    pcm = wav.readframes(wav.getnframes())\n    if not (wav.getframerate() == 22050 and wav.getnchannels() == 1 and (wav.getsampwidth() == 2)):\n        raise ValueError('release verification failed')\n    if not (wav.getnframes() > 0 and any(pcm)):\n        raise ValueError('release verification failed')\nprint(json.dumps({'pypi_consumer': 'piper-plus==2.0.0', 'reference_required': False, 'normal_text_api_generated': True}))\n"
    result = subprocess.run(
        [str(consumer), "-c", code, str(target)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    (target / "normal-api.log").write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    release = target / "releases/zs-v1"
    example = subprocess.run(
        [
            str(consumer),
            str(release / "examples/synthesize.py"),
            "--model",
            str(release / "tsukuyomi.onnx"),
            "--config",
            str(release / "tsukuyomi.onnx.json"),
            "--language",
            "ja",
            "--text",
            "これは公開モデルの確認です。",
            "--output",
            str(target / "example.wav"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    (target / "example.log").write_text(
        example.stdout + example.stderr, encoding="utf-8"
    )
    with __import__("wave").open(str(target / "example.wav"), "rb") as wav:
        if not (wav.getnframes() > 0 and any(wav.readframes(wav.getnframes()))):
            raise ValueError("release verification failed")
    checkpoint_code = "import json\nimport sys\nimport torch\nfrom piper_train.vits.lightning import VitsModel\npath = sys.argv[1]\nif not torch.serialization.get_unsafe_globals_in_checkpoint(path) == []:\n    raise ValueError('release verification failed')\ncheckpoint = torch.load(path, map_location='cpu', weights_only=True)\nmodel = VitsModel.load_from_checkpoint(path, map_location='cpu', weights_only=True, strict=True)\nif not (model is not None and checkpoint['hyper_parameters']['num_symbols'] == 173):\n    raise ValueError('release verification failed')\nprint(json.dumps({'weights_only_load': True, 'strict_training_model_load': True}))\n"
    checkpoint = subprocess.run(
        [sys.executable, "-c", checkpoint_code, str(release / "tsukuyomi.ckpt")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    (target / "checkpoint-load.log").write_text(
        checkpoint.stdout + checkpoint.stderr, encoding="utf-8"
    )
    return {
        "normal_reference_free_generation": True,
        "bundled_example_generated": True,
        "weights_only_strict_checkpoint_load": True,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate",
        action="store_true",
        help="Rehearse locally; does not claim a public download",
    )
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    bundle = workspace / "bundle"
    record = read_json(
        workspace
        / ("upload-dry-run.json" if args.candidate else "publication-receipt.json")
    )
    if not record["repo"] == REPO:
        raise ValueError("release verification failed")
    target = Path(
        tempfile.mkdtemp(
            prefix="candidate-" if args.candidate else "anonymous-", dir=workspace
        )
    )
    session = requests.Session()
    session.trust_env = False
    session.headers["User-Agent"] = (
        "piper-plus-tsukuyomi-zs-v1-anonymous-verification/1"
    )
    if not args.candidate:
        revision = record["commit"]
        value = anonymous_metadata(session, REPO, revision)
        if not (value["private"] is False and value["gated"] is False):
            raise ValueError("release verification failed")
    files = []
    for expected in record["files"]:
        name = expected["path"]
        if not (name == "README.md" or name.startswith("releases/zs-v1/")):
            raise ValueError("release verification failed")
        path = target / name
        if not path.resolve().is_relative_to(target.resolve()):
            raise ValueError("release verification failed")
        path.parent.mkdir(parents=True, exist_ok=True)
        if args.candidate:
            shutil.copyfile(bundle / name, path)
        else:
            with session.get(
                f"https://huggingface.co/{REPO}/resolve/{revision}/{quote(name, safe='/')}",
                stream=True,
                timeout=(15, 90),
            ) as response:
                response.raise_for_status()
                if not "Authorization" not in response.request.headers:
                    raise ValueError("release verification failed")
                with path.open("wb") as stream:
                    for chunk in response.iter_content(chunk_size=2**20):
                        stream.write(chunk)
        if not (
            path.stat().st_size == expected["bytes"]
            and digest(path) == expected["sha256"]
        ):
            raise ValueError(name)
        files.append(expected)
    release = target / "releases/zs-v1"
    manifest = read_json(release / "manifest.json")
    for entry in manifest["files"]:
        path = release / entry["path"]
        if not (
            path.stat().st_size == entry["bytes"] and digest(path) == entry["sha256"]
        ):
            raise ValueError("release verification failed")
    for line in (release / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        expected, name = line.split("  ", 1)
        if not digest(release / name) == expected:
            raise ValueError("release verification failed")
    retention = {} if args.candidate else verify_retention(session, revision, workspace)
    consumer = run_consumer(target)
    report = {
        "mode": "candidate_rehearsal"
        if args.candidate
        else "anonymous_public_verification",
        "public_verification_claimed": not args.candidate,
        "revision": None if args.candidate else revision,
        "authorization_header_used_for_download": False,
        "target": str(target),
        "files_verified": len(files),
        "manifest_entries_verified": len(manifest["files"]),
        "consumer": consumer,
        "retention": retention,
    }
    output = workspace / (
        "candidate-rehearsal.json"
        if args.candidate
        else "anonymous-public-verification.json"
    )
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
