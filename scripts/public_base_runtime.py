"""Verify the pinned public base with real CAM++ conditioning in CI."""

import argparse
import hashlib
import json
import math
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path


BASE_REPO = "ayousanz/piper-plus-base"
BASE_REVISION = "3620ed788667cb76f08bd6cf2db8152c1f4c8bd1"
REFERENCE_REVISION = "36b59c825c36bd386b8960cf3f604382f52f2a87"
FILES = {
    "base.onnx": "e9860701a941db02149c7cfbe19cfb578c235c5e25020f1f592131d9b3b30f84",
    "base.onnx.json": "d085681edaa5029c54ea8329f3f23ed347ba46ca15cd80e766de9a6a643dafc0",
    "campplus.onnx": "a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73",
}
REFERENCE_SHA256 = "b934863e39a6053e638784b516e859c047df55b4186b0bdf48019a1e4f6bf7fa"
RUNTIMES = ("python", "rust", "go", "csharp", "cpp", "wasm")
TEXTS = [
    ("ja-1", "ja", "こんにちは。今日は良い天気ですね。"),
    ("ja-2", "ja", "これは公開モデルの音声を確認するための文章です。"),
    ("ja-3", "ja", "駅まで歩いてから、電車で会社に向かいます。"),
    ("en", "en", "Hello, today is a beautiful day."),
    ("zh", "zh", "你好，今天天气很好。"),
    ("es", "es", "Hola, hoy hace buen tiempo."),  # codespell:ignore hace
    ("fr", "fr", "Bonjour, le soleil brille."),
    ("pt", "pt", "Olá, hoje está um belo dia."),
]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def write_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def download(url, path, expected):
    # urllib does not consult HF tokens or netrc; fixed public resolve URLs only.
    with (
        urllib.request.urlopen(url, timeout=120) as response,
        path.open("wb") as output,
    ):
        while block := response.read(1024 * 1024):
            output.write(block)
    require(digest(path) == expected, f"Downloaded hash mismatch: {path.name}")


def verify_files(workspace):
    for name, expected in {**FILES, "reference.wav": REFERENCE_SHA256}.items():
        require(digest(workspace / name) == expected, f"Input hash mismatch: {name}")
    record = json.loads((workspace / "inputs.json").read_text(encoding="utf-8"))
    require(record["base_revision"] == BASE_REVISION, "Unexpected base revision")
    require(record["reference_revision"] == REFERENCE_REVISION, "Unexpected reference")
    for name, expected in record["generated_hashes"].items():
        require(name in {"embedding.npy", "cases.json"}, "Unexpected generated input")
        require(
            digest(workspace / name) == expected,
            f"Generated input hash mismatch: {name}",
        )
    require(
        set(record["generated_hashes"]) == {"embedding.npy", "cases.json"},
        "Missing input hash",
    )
    return record


def prepare(workspace):
    import numpy as np
    import onnxruntime as ort
    import soundfile as sf
    import soxr
    import torch
    import torchaudio

    from piper_plus.phonemize.multilingual import MultilingualPhonemizer
    from piper_plus.voice import PiperVoice

    workspace.mkdir(parents=True, exist_ok=False)
    for name, expected in FILES.items():
        download(
            f"https://huggingface.co/{BASE_REPO}/resolve/{BASE_REVISION}/releases/zs-v1/{name}",
            workspace / name,
            expected,
        )
    download(
        "https://huggingface.co/ayousanz/piper-plus-tsukuyomi-chan/resolve/"
        f"{REFERENCE_REVISION}/samples/sample_ja.wav",
        workspace / "reference.wav",
        REFERENCE_SHA256,
    )
    audio, rate = sf.read(workspace / "reference.wav", dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)
    if rate != 16000:
        audio = soxr.resample(audio, rate, 16000, quality="HQ")
    features = torchaudio.compliance.kaldi.fbank(
        torch.from_numpy(audio).unsqueeze(0),
        sample_frequency=16000,
        num_mel_bins=80,
        frame_length=25,
        frame_shift=10,
        dither=0.0,
    )
    features -= features.mean(dim=0, keepdim=True)
    encoder = ort.InferenceSession(
        str(workspace / "campplus.onnx"), providers=["CPUExecutionProvider"]
    )
    embedding = encoder.run(None, {"input": features.unsqueeze(0).numpy()})[0].reshape(
        -1
    )
    require(
        embedding.shape == (192,) and np.isfinite(embedding).all(),
        "Invalid CAM++ embedding",
    )
    norm = float(np.linalg.norm(embedding))
    require(norm > 0, "Zero CAM++ embedding")
    embedding = (embedding / norm).astype(np.float32)
    np.save(workspace / "embedding.npy", embedding, allow_pickle=False)
    voice = PiperVoice.load(
        str(workspace / "base.onnx"), config_path=str(workspace / "base.onnx.json")
    )
    names = {item.name for item in voice.session.get_inputs()}
    require(
        "speaker_embedding" in names and "speaker_embedding_mask" not in names,
        "Unexpected base inputs",
    )
    cases = []
    for key, language, text in TEXTS:
        phonemizer = MultilingualPhonemizer(
            languages=["ja", "en", "zh", "es", "fr", "pt"],
            default_latin_language=language
            if language in {"en", "es", "fr", "pt"}
            else "en",
        )
        phones = phonemizer.phonemize(text)
        phones = [p for p in phones if not p.isspace() and p not in ",.;:!¡¿…—–-«»"]
        missing = set(phones) - set(voice.config.phoneme_id_map)
        require(not missing, f"Untrained phonemes in {key}: {missing}")
        ids = voice.phonemes_to_ids(phones)
        cases.append(
            {
                "key": key,
                "text": text,
                "language": language,
                "language_id": voice.config.language_id_map[language],
                "phoneme_ids": ids,
                "speaker_embedding": embedding.tolist(),
                "prosody_features": [[0, 0, 0] for _ in ids],
            }
        )
    # Functional conditioning check, not a plausible voice or quality comparison.
    cases.append(dict(cases[0], key="ja-conditioning-repeat"))
    cases.append(
        dict(
            cases[0],
            key="ja-conditioning-negative",
            speaker_embedding=(-embedding).tolist(),
        )
    )
    write_json(workspace / "cases.json", cases)
    record = {
        "base_repo": BASE_REPO,
        "base_revision": BASE_REVISION,
        "model_sha256": FILES["base.onnx"],
        "reference_revision": REFERENCE_REVISION,
        "reference_sha256": REFERENCE_SHA256,
        "reference_kind": "public synthesized legacy sample; not an original corpus recording",
        "embedding_dimension": 192,
        "embedding_norm": float(np.linalg.norm(embedding)),
        "generated_hashes": {
            name: digest(workspace / name) for name in ["embedding.npy", "cases.json"]
        },
        "scope": "six-language inference from shared Python phoneme IDs; native G2P and listening quality excluded",
    }
    write_json(workspace / "inputs.json", record)
    verify_files(workspace)
    print(json.dumps(record, ensure_ascii=False))


def inspect_wav(path, sample_rate):
    import array

    with wave.open(str(path), "rb") as stream:
        require(
            stream.getnchannels() == 1 and stream.getsampwidth() == 2,
            "Expected mono PCM16 WAV",
        )
        require(stream.getframerate() == sample_rate, "Unexpected sample rate")
        frames = stream.getnframes()
        require(frames >= sample_rate // 10, "Empty or implausibly short audio")
        samples = array.array("h", stream.readframes(frames))
    if sys.byteorder != "little":
        samples.byteswap()
    require(len(samples) == frames, "Truncated audio")
    require(any(samples), "Silent audio")
    return {
        "sha256": digest(path),
        "frames": frames,
        "sample_rate": sample_rate,
        "seconds": frames / sample_rate,
        "rms": math.sqrt(sum(float(x) ** 2 for x in samples) / frames) / 32768,
        "peak": max(abs(x) for x in samples) / 32768,
    }


def command(runtime, executable, workspace, output):
    cmd = [
        executable,
        "--model",
        str(workspace / "base.onnx"),
        "--config",
        str(workspace / "base.onnx.json"),
    ]
    if runtime == "python":
        cmd = [executable, "-m", "piper_plus", *cmd[1:]]
    if runtime == "rust":
        cmd += ["--no-warmup"]
    else:
        cmd += ["--json-input"]
    if runtime == "go":
        cmd += ["--output-dir", str(output.parent)]
    else:
        cmd += ["--output-file", str(output)]
    # Disable random noise for the paired embedding influence check.
    return cmd + ["--noise-scale", "0", "--noise-w", "0", "--length-scale", "1"]


def run(workspace, runtime, executable):
    require(runtime != "wasm", "Use the real ORT Web WASM runner")
    record = verify_files(workspace)
    cases = json.loads((workspace / "cases.json").read_text(encoding="utf-8"))
    rate = json.loads((workspace / "base.onnx.json").read_text(encoding="utf-8"))[
        "audio"
    ]["sample_rate"]
    output_dir = workspace / runtime
    output_dir.mkdir(exist_ok=False)
    results = []
    for case in cases:
        case_dir = output_dir / case["key"]
        case_dir.mkdir()
        output = case_dir / ("line_001.wav" if runtime == "go" else "audio.wav")
        entry = {k: v for k, v in case.items() if k not in {"key", "text", "language"}}
        completed = subprocess.run(
            command(runtime, executable, workspace, output),
            input=json.dumps(entry) + "\n",
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        (case_dir / "stdout.log").write_text(completed.stdout, encoding="utf-8")
        (case_dir / "stderr.log").write_text(completed.stderr, encoding="utf-8")
        require(
            completed.returncode == 0,
            f"{runtime}/{case['key']} failed: {completed.stderr[-2000:]}",
        )
        results.append(
            {
                "key": case["key"],
                "language": case["language"],
                **inspect_wav(output, rate),
            }
        )
    require(
        results[0]["sha256"] == results[-2]["sha256"],
        "Zero-noise inference was not repeatable",
    )
    require(
        results[0]["sha256"] != results[-1]["sha256"],
        "Changing the speaker embedding had no effect",
    )
    report = {
        **record,
        "runtime": runtime,
        "provider": "native CPU",
        "cases": results,
        "conditioning_changes_audio": True,
    }
    write_json(output_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False))


def summarize(reports, output):
    found = {}
    for path in reports.rglob("report.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        runtime = report["runtime"]
        require(
            runtime in RUNTIMES and runtime not in found,
            "Unexpected or duplicate runtime",
        )
        require(
            report["base_revision"] == BASE_REVISION
            and report["model_sha256"] == FILES["base.onnx"],
            "Wrong model",
        )
        require(report["reference_sha256"] == REFERENCE_SHA256, "Wrong reference")
        require(
            report["embedding_dimension"] == 192
            and report["conditioning_changes_audio"],
            "Missing conditioning evidence",
        )
        require(
            [case["key"] for case in report["cases"]]
            == [key for key, _, _ in TEXTS]
            + ["ja-conditioning-repeat", "ja-conditioning-negative"],
            "Missing cases",
        )
        require(
            report["cases"][0]["sha256"] == report["cases"][-2]["sha256"],
            "Non-repeatable inference",
        )
        require(
            report["cases"][0]["sha256"] != report["cases"][-1]["sha256"],
            "Embedding had no effect",
        )
        if runtime == "wasm":
            require(
                report["provider"].startswith("ORT Web WASM"),
                "WASM provider evidence is missing",
            )
        found[runtime] = report
    require(
        set(found) == set(RUNTIMES),
        f"Missing runtime evidence: {set(RUNTIMES) - set(found)}",
    )
    write_json(
        output,
        {"base_revision": BASE_REVISION, "runtimes": found, "quality_approval": False},
    )
    print(f"Verified all {len(found)} runtimes; listening quality remains unapproved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["prepare", "run", "summarize"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--runtime", choices=RUNTIMES)
    parser.add_argument("--executable")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare":
        prepare(args.workspace)
    elif args.mode == "run":
        require(args.runtime and args.executable, "run needs runtime and executable")
        run(args.workspace, args.runtime, args.executable)
    else:
        require(args.output is not None, "summarize needs an output")
        summarize(args.workspace, args.output)


if __name__ == "__main__":
    main()
