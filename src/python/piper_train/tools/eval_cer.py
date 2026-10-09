"""合成音声の明瞭度 (CER) 評価 — ASR 転写と参照テキストの文字誤り率。

v11 の教訓 (2026-08-25): SECS / comb-HNR / seen-ID はどれも「発話として
読めているか」を測らず、日本語として聞き取れないモデル (v11 ep9/19、学習量
不足) が指標上は良好に見えた。本ツールは ASR (transformers whisper、既存
依存のみ) の転写と参照テキストの CER を測り、v11b では gate に昇格する。

使い方 (listen_texts.txt 形式 = `tid<TAB>text` の tsv):

    python -m piper_train.tools.eval_cer \\
        --clips-dir <wav ディレクトリ (tid.wav)> \\
        --texts <texts.tsv> --json-out <out.json> \\
        [--asr-model openai/whisper-small] [--language ja]

CER は NFKC 正規化 + 句読点/空白除去後の文字編集距離 / 参照長。1.0 超は
clip しない (参照より長い出鱈目転写の検出力を残す)。
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import unicodedata
from collections.abc import Callable
from pathlib import Path

import numpy as np

from ..embedding_cache import atomic_write, file_sha256
from ..evaluation_manifest import load_manifest


_LOGGER = logging.getLogger(__name__)

# 句読点・記号・空白 (NFKC 後に除去)。ASR の表記揺れを CER に数えない。
_STRIP_CATEGORIES = ("P", "Z", "S")  # punctuation / separator / symbol


def normalize_text(text: str) -> str:
    """NFKC 正規化 + 句読点/空白/記号の除去。"""
    text = unicodedata.normalize("NFKC", text)
    return "".join(
        ch for ch in text if unicodedata.category(ch)[0] not in _STRIP_CATEGORIES
    )


def _levenshtein(a: str, b: str) -> int:
    """文字単位の編集距離 (挿入/削除/置換 = 1)。"""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(
                min(
                    prev[j] + 1,  # 削除
                    cur[j - 1] + 1,  # 挿入
                    prev[j - 1] + (ca != cb),  # 置換
                )
            )
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    """正規化後の文字誤り率 = 編集距離 / 参照長。参照が空なら ValueError。"""
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        raise ValueError("reference text is empty after normalization")
    return _levenshtein(ref, hyp) / len(ref)


def evaluate_clips(
    pairs: list[tuple[Path, str]],
    transcribe_fn: Callable[[Path], str],
) -> dict:
    """(wav, 参照テキスト) のリストを転写して CER を集計する。

    ``transcribe_fn`` は wav パス → 転写文字列。テストではここを差し替えて
    ASR 非依存に検証する (score_utmos の torch.hub monkeypatch と同じ流儀)。
    """
    per_file: dict[str, dict] = {}
    values: list[float] = []
    for wav, ref in pairs:
        hyp = transcribe_fn(wav)
        c = cer(ref, hyp)
        per_file[Path(wav).stem] = {"cer": c, "transcript": hyp, "reference": ref}
        values.append(c)
    return {
        "per_file": per_file,
        "cer_median": statistics.median(values),
        "cer_mean": statistics.fmean(values),
        "n_clips": len(values),
    }


def build_whisper_transcribe_fn(
    model_name: str = "openai/whisper-small",
    language: str = "ja",
    revision: str | None = None,
) -> Callable[[Path], str]:
    """transformers の whisper pipeline で transcribe_fn を作る (CPU)。

    追加依存なし (transformers は train extras に既存)。モデルは初回に
    HF Hub から自動 DL される。
    """
    from transformers import pipeline  # noqa: PLC0415

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model_name,
        device=-1,
        **({"revision": revision} if revision is not None else {}),
    )

    def transcribe(wav: Path) -> str:
        out = pipe(
            str(wav),
            generate_kwargs={"language": language, "task": "transcribe"},
        )
        return out["text"]

    return transcribe


def _read_texts(path: Path) -> dict[str, str]:
    refs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        tid, text = line.split("\t", 1)
        if tid in refs:
            raise ValueError(f"duplicate text ID: {tid}")
        refs[tid] = text
    return refs


def _strict_inputs(args) -> tuple[dict, dict, list[tuple[Path, str]]]:
    manifest = load_manifest(Path(args.manifest))
    asr = manifest["asr"]
    for name, expected in [
        ("asr_model", asr["model"]),
        ("asr_revision", asr["revision"]),
        ("language", asr["language"]),
    ]:
        provided = getattr(args, name)
        if provided is not None and provided != expected:
            raise ValueError(f"Pinned {name} mismatch")
    refs = {clip["id"]: clip["text"] for clip in manifest["clips"]}
    if len(refs) < 3:
        raise ValueError("strict CER requires at least 3 clips")
    if any(not normalize_text(text) for text in refs.values()):
        raise ValueError("reference text is empty after normalization")
    if args.texts and _read_texts(Path(args.texts)) != refs:
        raise ValueError("texts must exactly match the pinned manifest")
    directory = Path(args.clips_dir)
    wavs = list(directory.glob("*.wav"))
    if {wav.stem for wav in wavs} != set(refs) or len(wavs) != len(refs):
        raise ValueError("WAV IDs must exactly match expected IDs (missing/extra)")
    generation = json.loads((directory / "generation.json").read_text(encoding="utf-8"))
    if generation["version"] != 1:
        raise ValueError("Unsupported generation report version")
    if (
        generation["manifest_sha256"] != file_sha256(Path(args.manifest))
        or generation["conditions_sha256"] != manifest["conditions_sha256"]
    ):
        raise ValueError("generation manifest/conditions hash mismatch")
    if (
        generation["model_sha256"]
        != manifest["models"][generation["backend"]]["sha256"]
    ):
        raise ValueError("generation model hash mismatch")
    for field in ("sample_rate", "scales", "seed"):
        if generation[field] != manifest[field]:
            raise ValueError(f"generation {field} mismatch")
    if (
        generation["ground_truth_f0_or_duration"] is not False
        or generation["audio_encoding"] != "float32-raw"
    ):
        raise ValueError("strict CER requires predicted inference and raw audio")
    if (
        manifest.get("training_epoch") is not None
        and generation.get("training_epoch") != manifest["training_epoch"]
    ):
        raise ValueError("generation training epoch mismatch")
    generated = generation["clips"]
    if len(generated) != len(refs) or {clip["id"] for clip in generated} != set(refs):
        raise ValueError("generation clip IDs missing/extra/duplicate")
    hashes = {clip["id"]: clip["wav_sha256"] for clip in generated}
    expected_clips = {clip["id"]: clip for clip in manifest["clips"]}
    expected_ordinals = {clip["id"]: i for i, clip in enumerate(manifest["clips"])}
    for clip in generated:
        expected = expected_clips[clip["id"]]
        for field in ("text_sha256", "speaker_embedding_sha256", "reference_audio"):
            if clip[field] != expected[field]:
                raise ValueError(f"generation {field} mismatch for {clip['id']}")
        if clip["seed"] != manifest["seed"] + expected_ordinals[clip["id"]]:
            raise ValueError(f"generation seed mismatch for {clip['id']}")
    if any(file_sha256(wav) != hashes[wav.stem] for wav in wavs):
        raise ValueError("generated WAV hash mismatch")
    from scipy.io.wavfile import read  # noqa: PLC0415

    for wav in wavs:
        sample_rate, audio = read(wav)
        if (
            sample_rate != manifest["sample_rate"]
            or audio.dtype != np.float32
            or audio.ndim != 1
            or not audio.size
            or not np.isfinite(audio).all()
        ):
            raise ValueError(f"Invalid raw float32 evaluation waveform: {wav.name}")
    return (
        manifest,
        generation,
        [(directory / (tid + ".wav"), ref) for tid, ref in refs.items()],
    )


def _evaluate_strict(args) -> tuple[dict, int]:
    pairs = []
    result = {
        "mode": "strict",
        "gate_passed": False,
        "cer_median": None,
        "cer_mean": None,
        "n_clips": 0,
        "failed_clips": [],
    }
    try:
        manifest, generation, pairs = _strict_inputs(args)
        asr = manifest["asr"]
        result.update(
            {
                "manifest_sha256": file_sha256(Path(args.manifest)),
                "conditions_sha256": manifest["conditions_sha256"],
                "asr_model": asr["model"],
                "asr_revision": asr["revision"],
                "language": asr["language"],
                "normalization": asr["normalization"],
                "training_epoch": generation.get("training_epoch"),
                "n_expected": len(pairs),
                "per_file": {},
            }
        )
        transcribe = build_whisper_transcribe_fn(
            asr["model"], asr["language"], revision=asr["revision"]
        )
        scores = []
        for wav, ref in pairs:
            try:
                hypothesis = transcribe(wav)
                if not isinstance(hypothesis, str):
                    raise ValueError("ASR transcript must be a string")
                score = cer(ref, hypothesis)
                result["per_file"][wav.stem] = {
                    "cer": score,
                    "transcript": hypothesis,
                    "reference": ref,
                }
                scores.append(score)
            except Exception as exc:
                result["failed_clips"].append({"id": wav.stem, "error": str(exc)})
        result["n_clips"] = len(scores)
        if not result["failed_clips"]:
            result["cer_median"] = statistics.median(scores)
            result["cer_mean"] = statistics.fmean(scores)
            epoch = result["training_epoch"]
            result["eligible_for_promotion"] = type(epoch) is int and epoch >= 40
            result["gate_passed"] = (
                result["eligible_for_promotion"] and result["cer_median"] <= 0.30
            )
        return result, 0 if result["gate_passed"] else 1
    except Exception as exc:
        result["error"] = str(exc)
        if pairs and not result["failed_clips"]:
            result["failed_clips"] = [
                {"id": wav.stem, "error": str(exc)} for wav, _ref in pairs
            ]
        return result, 2


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clips-dir", required=True, help="tid.wav のディレクトリ")
    ap.add_argument(
        "--texts", help="参照テキスト tsv (tid<TAB>text、listen_texts 形式)"
    )
    ap.add_argument("--json-out", help="集計 JSON の出力先")
    ap.add_argument(
        "--manifest", help="Pinned evaluation manifest; enables strict promotion gate"
    )
    ap.add_argument("--asr-model")
    ap.add_argument("--asr-revision")
    ap.add_argument("--language")
    args = ap.parse_args()

    if args.manifest:
        result, exit_code = _evaluate_strict(args)
        if args.json_out:
            atomic_write(
                Path(args.json_out),
                lambda target: target.write(
                    json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8")
                ),
            )
        print(json.dumps(result, ensure_ascii=False))
        return exit_code
    if not args.texts:
        ap.error("diagnostic mode requires --texts; strict mode uses --manifest")
    args.asr_model = args.asr_model or "openai/whisper-small"
    args.language = args.language or "ja"

    refs = _read_texts(Path(args.texts))

    pairs = []
    for wav in sorted(Path(args.clips_dir).glob("*.wav")):
        if wav.stem not in refs:
            _LOGGER.warning("参照テキストが無い wav をスキップ: %s", wav.name)
            continue
        pairs.append((wav, refs[wav.stem]))
    if not pairs:
        raise SystemExit(f"評価対象なし: {args.clips_dir}")

    transcribe = build_whisper_transcribe_fn(
        args.asr_model, args.language, revision=args.asr_revision
    )
    result = evaluate_clips(pairs, transcribe)
    result["mode"] = "diagnostic"
    result["gate_passed"] = None
    result["asr_model"] = args.asr_model
    result["asr_revision"] = args.asr_revision
    result["language"] = args.language

    for tid, r in result["per_file"].items():
        _LOGGER.info("%s: CER %.3f | %s", tid, r["cer"], r["transcript"])
    print(
        f"cer median: {result['cer_median']:.3f} / mean: {result['cer_mean']:.3f} "
        f"(n={result['n_clips']}, asr={args.asr_model})"
    )

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
