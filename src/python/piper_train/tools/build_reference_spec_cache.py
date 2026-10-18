#!/usr/bin/env python3
"""参照専用 spec cache を作る (参照融合計画 §8、Ruling R17)。

学習音声の spec cache は言語ごとに別の builder で作られている (ja/en は bilingual
dataset の Silero VAD または energy VAD、zh/es/fr/pt は VAD なしで GPU batch 経路の
こともある)。checkpoint が宣言できる参照 spec の frontend は 1 つなので、G の参照
spec を学習音声の cache からそのまま読むと、言語によって評価と違う作り方の spec を
学習することになり、どこでも検出されない。

この tool は ``build_reference_pairs`` が書いた参照ペア jsonl を読み、参照に使う
発話の **元音声** (``reference_audio_path``) から、閉じた集合の名前付き frontend で
参照 spec を CPU で作り直す::

    uv run python -m piper_train.tools.build_reference_spec_cache \\
        "${DATASET_DIR}/dataset.pairs.jsonl" "${DATASET_DIR}/dataset.refspec.jsonl" \\
        --frontend "no-vad;soxr-mq" --config "${DATASET_DIR}/config.json" \\
        --filter-length 1024 --hop-length 256 --win-length 1024 \\
        --output-dir "${DATASET_DIR}/reference-spec-cache"

* spec は評価と同じ ``reference_frontend.reference_spec_from_file`` で作る (作り方の
  正本は 1 つ)。参照の元音声ごとに 1 回だけ計算する。
* 保存形式は学習 cache の ``.spec.pt`` と同じ (float16 の ``torch.save``、
  ``[filter_length // 2 + 1, frames]``)。dataset はこれを float32 に戻して読む。
* ファイル名は float32 spec の sha256 (``<sha256>.spec.pt``、content-addressed)。
  中身が変われば名前も変わるので、古いファイルが別の spec として読まれることはない。
  書き込みは一時ファイル + rename。
* 出力 jsonl は ``reference_audio_spec_path`` だけを cache へ向け直す (他の field は
  そのまま)。cache が出力 jsonl の dir の下にあれば相対 path、なければ絶対 path。
* cache dir に来歴 sidecar (``reference_spec_cache.json``) を置く: schema・frontend・
  STFT 設定・sample rate・件数と、ファイルごとの spec sha256・frame 数・元音声
  (path と file bytes の sha256)。学習 (``--reference-conditioning ref_spec``) は
  起動時にこの sidecar を照合し、frontend・STFT 設定がモデルと違う、または sidecar に
  載っていない参照 spec を拒否する。sidecar は最後に成功した実行の分だけを載せる。
* sample rate は ``--config`` (dataset の ``config.json``) の ``audio.sample_rate``。
  STFT 設定 (``filter_length`` / ``hop_length`` / ``win_length``) は config の
  ``audio`` にあればそれを使い、無ければ flag で明示する (既定値では作らない)。両方
  あって食い違えば拒否する。

拒否: 未知の frontend、参照の元音声が無い・読めない・frontend が受け付けない行
(全部を行番号つきで報告し、出力も sidecar も書かずに非 0 終了)、STFT 設定と config
の食い違い、別の frontend・STFT 設定で作った cache dir への書き込み。

同じ引数での再実行は同じ出力になる (既存の出力を置き換えるには ``--overwrite``)。
失敗した実行は前回の出力 jsonl と sidecar を変えない (書くのは全行が通ってから。
新しい spec ファイルは content-addressed なので前回のファイルを壊さない)。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from importlib import metadata
from pathlib import Path

from piper_train.reference_spec_contract import (
    REFERENCE_SPEC_CACHE_SCHEMA,
    REFERENCE_SPEC_CACHE_SIDECAR,
    REFERENCE_SPEC_CACHE_STFT_KEYS,
    frontend_steps,
)


SPEC_HASH = "sha256(float32-le C-order spec, before fp16 storage)"
AUDIO_HASH = "sha256(source audio file bytes)"
STORAGE = (
    "torch.save float16 [filter_length // 2 + 1, frames] "
    "(same format as the training .spec.pt)"
)
_STFT_FLAGS = {
    "filter_length": "--filter-length",
    "hop_length": "--hop-length",
    "win_length": "--win-length",
}


class ReferenceSpecCacheError(ValueError):
    """参照の元音声から spec を作れない行がある (全部の行を ``bad_rows`` に持つ)。"""

    def __init__(self, bad_rows: list[str]):
        self.bad_rows = list(bad_rows)
        super().__init__(
            f"{len(self.bad_rows)} row(s) cannot get a reference spec:\n"
            + "\n".join(f"  {line}" for line in self.bad_rows)
        )


def _positive_int(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive int, got {value!r}")
    return value


def resolve_stft(
    config: dict,
    *,
    filter_length: int | None = None,
    hop_length: int | None = None,
    win_length: int | None = None,
) -> dict:
    """config (dataset の ``config.json``) と flag から sample rate と STFT 設定を決める。

    sample rate は config の ``audio.sample_rate`` だけから取る。STFT 設定は config の
    ``audio`` の値、無ければ flag。どちらも無い値と、両方あって食い違う値は
    ``ValueError`` (既定値で黙って作らない)。
    """
    audio = config.get("audio") if isinstance(config, dict) else None
    if not isinstance(audio, dict) or "sample_rate" not in audio:
        raise ValueError("the config has no audio.sample_rate")
    stft = {"sample_rate": _positive_int("audio.sample_rate", audio["sample_rate"])}
    flags = {
        "filter_length": filter_length,
        "hop_length": hop_length,
        "win_length": win_length,
    }
    for key, flag_value in flags.items():
        config_value = audio.get(key)
        if config_value is None and flag_value is None:
            raise ValueError(
                f"{key} is not in the config's audio section and {_STFT_FLAGS[key]} "
                "was not given (no default: use the model's STFT setting)"
            )
        if (
            config_value is not None
            and flag_value is not None
            and config_value != flag_value
        ):
            raise ValueError(
                f"{_STFT_FLAGS[key]} {flag_value} disagrees with the config's "
                f"audio.{key} {config_value!r}"
            )
        value = config_value if config_value is not None else flag_value
        stft[key] = _positive_int(key, value)
    return stft


def file_sha256(path: Path | str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _store_spec(path: Path, spec_fp16) -> None:
    """``spec_fp16`` を ``path`` に置く (同じ中身が既にあれば書かない)。"""
    import torch  # noqa: PLC0415

    from piper_train.norm_audio import _atomic_torch_save  # noqa: PLC0415

    if path.is_file():
        try:
            existing = torch.load(path, map_location="cpu", weights_only=True)
        except Exception:  # noqa: BLE001 - 読めない既存ファイルは書き直す
            existing = None
        if (
            isinstance(existing, torch.Tensor)
            and existing.dtype == spec_fp16.dtype
            and torch.equal(existing, spec_fp16)
        ):
            return
    _atomic_torch_save(spec_fp16, path)


def _jsonl_path(path: Path, jsonl_dir: Path) -> str:
    """出力 jsonl に書く path (jsonl の dir の下なら相対、それ以外は絶対)。"""
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(Path(os.path.abspath(jsonl_dir))).as_posix()
    except ValueError:
        return str(absolute)


def build_reference_spec_cache(
    rows: list[dict],
    *,
    base_dir: Path,
    cache_dir: Path,
    jsonl_dir: Path,
    frontend: str,
    stft: dict,
) -> tuple[list[dict], dict]:
    """参照の元音声から名前付き frontend で spec を作り、cache に置く。

    Args:
        rows: 参照ペア jsonl の行 (``reference_audio_path`` が要る)。入力は変更しない。
        base_dir: 行の相対 path の基準 (入力 jsonl の dir)。
        cache_dir: spec ファイルを置く dir (無ければ作る)。
        jsonl_dir: 出力 jsonl の dir (書き直す ``reference_audio_spec_path`` の基準)。
        frontend: ``reference_spec_contract`` の閉じた集合の名前。
        stft: ``resolve_stft`` の戻り値 (sample_rate と STFT 設定)。

    Returns:
        ``(rewritten_rows, sidecar)``。``rewritten_rows`` は
        ``reference_audio_spec_path`` だけを cache へ向け直した行のコピー、
        ``sidecar`` は来歴 (``main`` が入力の情報を足して書く)。

    Raises:
        ValueError: 未知の frontend。
        ReferenceSpecCacheError: spec を作れない行がある (全部の行を報告する)。
            このとき出力は返さない (cache dir に新しい spec ファイルが残ることは
            あるが、content-addressed なので既存のファイルを壊さない)。
    """
    from piper_train import reference_frontend  # noqa: PLC0415

    steps = frontend_steps(frontend)
    stft = {key: stft[key] for key in REFERENCE_SPEC_CACHE_STFT_KEYS}
    bad: list[tuple[int, str]] = []
    rows_of_source: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        raw = row.get("reference_audio_path")
        if not raw or not isinstance(raw, str):
            bad.append(
                (
                    index,
                    "no reference_audio_path (rebuild the pairs with "
                    "build_reference_pairs from a dataset whose rows have audio_path)",
                )
            )
            continue
        path = Path(raw)
        if not path.is_absolute():
            path = base_dir / path
        rows_of_source.setdefault(os.path.abspath(path), []).append(index)

    cache_dir.mkdir(parents=True, exist_ok=True)
    computed: dict[str, dict] = {}
    for source in sorted(rows_of_source):
        try:
            audio_sha256 = file_sha256(source)
            spec, info = reference_frontend.reference_spec_from_file(
                source,
                target_sample_rate=stft["sample_rate"],
                filter_length=stft["filter_length"],
                hop_length=stft["hop_length"],
                win_length=stft["win_length"],
                frontend=frontend,
            )
        except Exception as exc:  # noqa: BLE001 - 壊れた音声は種類を問わず行ごとに報告する
            for index in rows_of_source[source]:
                bad.append(
                    (
                        index,
                        f"reference audio {rows[index]['reference_audio_path']} "
                        f"({source}): {type(exc).__name__}: {exc}",
                    )
                )
            continue
        spec_sha256 = reference_frontend.reference_spec_sha256(spec)
        name = f"{spec_sha256}.spec.pt"
        _store_spec(cache_dir / name, spec.half())
        computed[source] = {
            "name": name,
            "spec_sha256": spec_sha256,
            "frames": int(info["frames"]),
            "audio_sha256": audio_sha256,
        }
    if bad:
        raise ReferenceSpecCacheError(
            [f"line {index + 1}: {reason}" for index, reason in sorted(bad)]
        )

    files: dict[str, dict] = {}
    for source in sorted(computed):
        result = computed[source]
        entry = files.setdefault(
            result["name"],
            {
                "spec_sha256": result["spec_sha256"],
                "frames": result["frames"],
                "sources": [],
            },
        )
        entry["sources"].append(
            {"audio_path": source, "audio_sha256": result["audio_sha256"]}
        )

    rewritten: list[dict] = []
    source_of_row = {
        index: source for source, indices in rows_of_source.items() for index in indices
    }
    for index, row in enumerate(rows):
        out = copy.deepcopy(row)
        name = computed[source_of_row[index]]["name"]
        out["reference_audio_spec_path"] = _jsonl_path(cache_dir / name, jsonl_dir)
        rewritten.append(out)

    sidecar = {
        "schema": REFERENCE_SPEC_CACHE_SCHEMA,
        "frontend": frontend,
        "frontend_builder": steps["builder"],
        **stft,
        "center": False,
        "spec_channels": stft["filter_length"] // 2 + 1,
        "storage": STORAGE,
        "spec_hash": SPEC_HASH,
        "audio_hash": AUDIO_HASH,
        "count": len(files),
        "files": dict(sorted(files.items())),
    }
    return rewritten, sidecar


def _versions() -> dict:
    versions = {}
    for package in ("torch", "soxr", "numpy", "soundfile"):
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def _check_existing_cache(sidecar_path: Path, frontend: str, stft: dict) -> None:
    """cache dir に別の作り方の sidecar があれば拒否する (1 dir = 1 つの作り方)。"""
    if not sidecar_path.exists():
        return
    try:
        existing = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"cannot read the existing sidecar {sidecar_path}: {exc}; remove it or "
            "use another --output-dir"
        ) from exc
    recipe = {"schema": REFERENCE_SPEC_CACHE_SCHEMA, "frontend": frontend, **stft}
    differ = [
        f"{key}: existing {existing.get(key)!r} != requested {value!r}"
        for key, value in recipe.items()
        if not isinstance(existing, dict) or existing.get(key) != value
    ]
    if differ:
        raise SystemExit(
            f"{sidecar_path.parent} already holds a reference spec cache made "
            f"another way ({'; '.join(differ)}); use another --output-dir"
        )


def _has_relative_paths(rows: list[dict]) -> bool:
    return any(
        isinstance(value, str) and value and not Path(value).is_absolute()
        for row in rows
        for key, value in row.items()
        if key.endswith("_path") or key == "reference_utterance_id"
    )


def main(argv: list[str] | None = None) -> int:
    from piper_train.tools.build_reference_pairs import (  # noqa: PLC0415
        _write_atomically,
    )

    parser = argparse.ArgumentParser(
        description="Rebuild the generator's reference specs from the reference "
        "utterances' source audio with one named frontend (reference-only spec "
        "cache, Ruling R17) and point reference_audio_spec_path at it."
    )
    parser.add_argument("input", type=Path, help="reference pairs jsonl")
    parser.add_argument(
        "output", type=Path, help="new jsonl with reference_audio_spec_path rewritten"
    )
    parser.add_argument(
        "--frontend",
        required=True,
        help="reference spec frontend (closed set in reference_spec_contract)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="the dataset's config.json (audio.sample_rate, optional STFT settings)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="cache dir for the reference specs and the provenance sidecar",
    )
    for key, flag in _STFT_FLAGS.items():
        parser.add_argument(
            flag,
            type=int,
            default=None,
            help=f"STFT {key} (required unless the config's audio section has it)",
        )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output jsonl / sidecar (never the input)",
    )
    args = parser.parse_args(argv)

    try:
        frontend_steps(args.frontend)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    input_path: Path = args.input
    output_path: Path = args.output
    cache_dir: Path = args.output_dir
    sidecar_path = cache_dir / REFERENCE_SPEC_CACHE_SIDECAR
    if not input_path.is_file():
        raise SystemExit(f"input jsonl not found: {input_path}")
    for path in (output_path, sidecar_path):
        if path.resolve() == input_path.resolve():
            raise SystemExit(f"refusing to overwrite the input jsonl: {input_path}")

    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        stft = resolve_stft(
            config,
            filter_length=args.filter_length,
            hop_length=args.hop_length,
            win_length=args.win_length,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"config {args.config}: {exc}") from exc
    _check_existing_cache(sidecar_path, args.frontend, stft)
    for path in (output_path, sidecar_path):
        if path.exists() and not args.overwrite:
            raise SystemExit(f"{path} exists; pass --overwrite to replace it")

    raw = input_path.read_bytes()
    rows = [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]
    if output_path.resolve().parent != input_path.resolve().parent and (
        _has_relative_paths(rows)
    ):
        raise SystemExit(
            "the output must be in the same directory as the input because the "
            "dataset paths are relative to the jsonl directory "
            f"({input_path.resolve().parent})"
        )

    try:
        rewritten, sidecar = build_reference_spec_cache(
            rows,
            base_dir=input_path.resolve().parent,
            cache_dir=cache_dir,
            jsonl_dir=output_path.resolve().parent,
            frontend=args.frontend,
            stft=stft,
        )
    except ReferenceSpecCacheError as exc:
        raise SystemExit(f"{input_path}: {exc}") from exc
    sidecar.update(
        {
            "input": str(input_path),
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "config": str(args.config),
            "versions": _versions(),
        }
    )
    _write_atomically(
        [
            # sidecar を先に置き、出力 jsonl は最後に置く: 出力 jsonl があれば
            # 必ずそれを覆う sidecar もある
            (sidecar_path, json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n"),
            (
                output_path,
                "".join(
                    json.dumps(row, ensure_ascii=False) + "\n" for row in rewritten
                ),
            ),
        ]
    )
    summary = {key: sidecar[key] for key in ("schema", "frontend", "count")}
    summary.update({"rows": len(rewritten), "output": str(output_path)})
    print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
