"""Exercise installed wheels in isolated Python, including pinned real-model TTS."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.metadata
import json
import sys
import tomllib
import urllib.request
import wave
from dataclasses import asdict
from pathlib import Path


class RejectExternalEnglish(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"g2p_en", "distance"}:
            raise ImportError(f"External dependency forbidden: {fullname}")


def download_base(manifest_path: Path, output: Path) -> Path:
    manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    model = next(m for m in manifest["models"] if m["name"] == "zero-shot-base-zs-v1")
    for artifact in model["artifacts"]:
        filename = artifact["filename"]
        if filename not in {"base.onnx", "base.onnx.json"}:
            continue
        target = output / filename
        url = model["hf_mirror_url"].rsplit("/", 1)[0] + "/" + filename
        if not target.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                target.write_bytes(response.read())
        raw = target.read_bytes()
        if (
            len(raw) != artifact["bytes"]
            or hashlib.sha256(raw).hexdigest() != artifact["sha256"]
        ):
            raise ValueError(f"Public model checksum mismatch: {filename}")
    return output / "base.onnx"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-base-manifest", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    names = {
        d.metadata["Name"].lower().replace("_", "-")
        for d in importlib.metadata.distributions()
    }
    if names & {"distance", "g2p-en"}:
        raise RuntimeError("Old English distributions are still installed")
    sys.meta_path.insert(0, RejectExternalEnglish())

    import nltk

    for resource in (
        "averaged_perceptron_tagger",
        "averaged_perceptron_tagger_eng",
        "cmudict",
    ):
        nltk.download(resource, quiet=True, raise_on_error=True)

    import piper_plus
    import piper_plus_g2p
    from piper_plus._vendor.g2p_en import G2p as RuntimeG2p
    from piper_plus.phonemize.english import phonemize_english
    from piper_plus.phonemize.multilingual import MultilingualPhonemizer as RuntimeMulti
    from piper_plus_g2p._vendor.g2p_en import G2p
    from piper_plus_g2p.english import phonemize_english_with_prosody
    from piper_plus_g2p.multilingual import MultilingualPhonemizer

    # -I plus this check prevents an editable source checkout from proving a wheel.
    for module in (piper_plus, piper_plus_g2p):
        if (
            not Path(module.__file__)
            .resolve()
            .is_relative_to(Path(sys.prefix).resolve())
        ):
            raise RuntimeError(
                f"Source checkout imported instead of wheel: {module.__file__}"
            )
        # Verify notices and data in the installed wheel as well as the source.
        bundle = Path(module.__file__).parent / "_vendor/g2p_en"
        reference = (
            Path(__file__).resolve().parents[1]
            / "src/python_run/piper_plus/_vendor/g2p_en"
        )
        expected = json.loads(
            (reference / "provenance.json").read_text(encoding="utf-8")
        )
        installed = json.loads((bundle / "provenance.json").read_text(encoding="utf-8"))
        if installed != expected:
            raise ValueError(f"Installed bundle provenance mismatch: {module.__name__}")
        for name, checksum in expected["files"].items():
            if hashlib.sha256((bundle / name).read_bytes()).hexdigest() != checksum:
                raise ValueError(
                    f"Installed bundle asset mismatch: {module.__name__}/{name}"
                )
        if (bundle / "NOTICE.txt").read_bytes() != (
            reference / "NOTICE.txt"
        ).read_bytes():
            raise ValueError(
                f"Installed bundle attribution mismatch: {module.__name__}"
            )
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    engine, runtime_engine = G2p(), RuntimeG2p()
    for case in fixture["cases"]:
        assert engine(case["text"]) == case["arpabet"], case["text"]
        assert runtime_engine(case["text"]) == case["arpabet"], case["text"]
        ipa, prosody = phonemize_english_with_prosody(case["text"])
        assert ipa == case["ipa"], case["text"]
        assert [asdict(p) if p else None for p in prosody] == case["prosody"], case[
            "text"
        ]
        assert phonemize_english(case["text"]) == case["runtime"], case["text"]
    for case in fixture["mixed_cases"]:
        ipa, prosody = MultilingualPhonemizer(case["languages"]).phonemize_with_prosody(
            case["text"]
        )
        assert ipa == case["ipa"], case["text"]
        assert [asdict(p) if p else None for p in prosody] == case["prosody"], case[
            "text"
        ]
        assert (
            RuntimeMulti(case["languages"]).phonemize(case["text"]) == case["runtime"]
        ), case["text"]
    result = {
        "english_cases": len(fixture["cases"]),
        "mixed_cases": len(fixture["mixed_cases"]),
        "wav": [],
    }
    if args.public_base_manifest:
        import numpy as np

        from piper_plus import PiperVoice

        model = download_base(args.public_base_manifest, args.output)
        voice = PiperVoice.load(model)
        embedding = np.zeros(192, dtype=np.float32)
        embedding[0] = 1
        cases = [
            ("en", 1, "I have $250 in my pocket."),
            ("en-oov", 1, "I'm an activationist."),
            ("ja-en", 0, "こんにちは、Hello worldです。"),
            ("zh-en", 2, "让我用 ChatGPT 写代码。"),
        ]
        for label, language, text in cases:
            # The released base omits punctuation/space tokens. Preserve its
            # established text API behavior, but reject missing speech tokens.
            separators = set(" \t\r\n.,!?;:、。，！？")
            absent = {
                p
                for sentence in voice.phonemize(text)
                for p in sentence
                if p not in voice.config.phoneme_id_map
            }
            missing = absent - separators
            if missing:
                raise ValueError(f"Missing public-model phonemes: {label}: {missing}")
            target = args.output / f"{label}.wav"
            with wave.open(str(target), "wb") as wav:
                voice.synthesize(
                    text, wav, language_id=language, speaker_embedding=embedding
                )
            with wave.open(str(target), "rb") as wav:
                frames = wav.getnframes()
                samples = np.frombuffer(wav.readframes(frames), dtype="<i2")
                assert (
                    frames > 0
                    and samples.size
                    and np.isfinite(samples).all()
                    and np.any(samples)
                )
                result["wav"].append(
                    {
                        "file": target.name,
                        "frames": frames,
                        "rate": wav.getframerate(),
                        "omitted_separators": sorted(absent & separators),
                    }
                )
    (args.output / "consumer-report.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
