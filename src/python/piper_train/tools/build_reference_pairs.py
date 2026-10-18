#!/usr/bin/env python3
"""学習時の G 参照ペアを dataset jsonl に書き足す (参照融合計画 §8 Task 7R)。

各 target 発話に **同じ話者・同じ split・別音声** の参照発話を 1 つ割り当て、
次のフィールドを追加した新しい jsonl を書く::

    uv run python -m piper_train.tools.build_reference_pairs \\
        "${DATASET_DIR}/dataset.jsonl" "${DATASET_DIR}/dataset.pairs.jsonl" \\
        --seed 1234

追加フィールド:

* ``audio_sha256`` — target の音声 hash (下記)
* ``reference_utterance_id`` — 参照の ``audio_norm_path`` (入力の表記のまま)。
  学習側 (``PiperDataset``) は target の ``utterance_id`` と同じ規約
  ``str(resolve(audio_norm_path))`` に正規化して照合する。
* ``reference_audio_spec_path`` / ``reference_speaker_embedding_path`` —
  参照発話の ``audio_spec_path`` / ``speaker_embedding_path`` (表記のまま)
* ``reference_audio_sha256`` — 参照の音声 hash

音声 hash は **``audio_norm`` cache を読み込んだ float32 sample (little
endian、平坦化) の sha256**。ファイルの byte ではなく中身の sample を見るので、
別 path に置かれた同一音声 (cache 名は path から決まる) も同じ hash になる。
``--strict-zero-shot`` の ``validate_reference_pairs`` はこの hash で
「参照 = 同一音声」を拒否する。

候補がない target は自己参照に戻さず **除外** し、理由ごとの件数を summary
JSON (既定 ``<output>.summary.json``) に書く:

* ``missing_audio_norm_path`` / ``missing_audio_spec_path`` /
  ``missing_speaker_id`` / ``missing_split`` / ``missing_speaker_embedding_path``
  / ``missing_audio_sha256`` — 必要なフィールドがない
* ``no_other_utterance`` — 同じ話者・split に他の発話がない
* ``only_identical_audio`` — 他の発話はあるが全て同一音声

split フィールド (``split``) が dataset に 1 つもなければ全体を 1 つの split と
して扱い、summary の ``split_field_present`` を false にする。ここでの「同 split」
は **jsonl の ``split`` フィールドだけ** を指し、学習が実行時に行う random な
train/val 分割とは無関係 (summary の ``split_check`` に明記する。跨ぎは学習側が
読み込み時に数えて WARNING を出す)。

割り当ては ``(seed, target の audio_norm_path)`` から決まる乱数で選ぶので、
同じ seed なら入力の並びに依存せず同じ結果になる。入力 jsonl は上書きしない。
出力が既にあれば ``--overwrite`` なしでは拒否する。出力 jsonl と summary は
一時ファイルに書いてから rename し (summary が先、jsonl が最後)、途中で失敗
しても中途半端な出力や既存出力の破損を残さない。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path


SCHEMA = "reference_pairs_v1"
AUDIO_HASH = "sha256(float32-le samples of audio_norm)"
SPLIT_CHECK = (
    "same split = same value of the jsonl 'split' field only; independent of "
    "the training run's random train/val split (references crossing it are "
    "counted and logged at load time)"
)


def audio_sha256_of(path: Path | str) -> str:
    """``audio_norm`` cache (.pt / .npy) の float32 sample の sha256。"""
    import numpy as np  # noqa: PLC0415 - import 時に torch を要求しない

    from piper_train.vits.dataset import _load_tensor  # noqa: PLC0415

    samples = _load_tensor(Path(path))
    array = np.ascontiguousarray(samples.detach().cpu().numpy(), dtype="<f4")
    return hashlib.sha256(array.reshape(-1).tobytes()).hexdigest()


def _eligibility(entry: dict, split_present: bool) -> str | None:
    """target / 参照になれない理由 (なれるなら None)。"""
    if not entry.get("audio_norm_path"):
        return "missing_audio_norm_path"
    if not entry.get("audio_spec_path"):
        return "missing_audio_spec_path"
    if entry.get("speaker_id") is None:
        return "missing_speaker_id"
    if split_present and entry.get("split") is None:
        return "missing_split"
    if not entry.get("speaker_embedding_path"):
        return "missing_speaker_embedding_path"
    if not entry.get("audio_sha256"):
        return "missing_audio_sha256"
    return None


def build_reference_pairs(entries: list[dict], seed: int) -> tuple[list[dict], dict]:
    """各 target に同話者・同 split・別 hash の参照を 1 つ割り当てる。

    ``entries`` は dataset jsonl の行 (dict)。各行に ``audio_sha256`` が要る
    (CLI は ``audio_sha256_of`` で計算して入れる)。入力は変更しない。

    Returns ``(paired, summary)``: ``paired`` は参照フィールドを追加した行の
    コピー (入力順、除外分を除く)、``summary`` は件数と除外理由。
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError(f"seed must be a non-negative int, got {seed!r}")
    split_present = any(entry.get("split") is not None for entry in entries)

    reasons: list[str | None] = [_eligibility(e, split_present) for e in entries]
    groups: dict[tuple, list[int]] = defaultdict(list)
    for index, (entry, reason) in enumerate(zip(entries, reasons, strict=True)):
        if reason is None:
            groups[(entry.get("split"), entry["speaker_id"])].append(index)

    paired: list[dict] = []
    excluded: Counter = Counter()
    for index, entry in enumerate(entries):
        if reasons[index] is not None:
            excluded[reasons[index]] += 1
            continue
        members = groups[(entry.get("split"), entry["speaker_id"])]
        others = [
            i
            for i in members
            if i != index and entries[i]["audio_norm_path"] != entry["audio_norm_path"]
        ]
        if not others:
            excluded["no_other_utterance"] += 1
            continue
        candidates = sorted(
            (i for i in others if entries[i]["audio_sha256"] != entry["audio_sha256"]),
            key=lambda i: (entries[i]["audio_norm_path"], i),
        )
        if not candidates:
            excluded["only_identical_audio"] += 1
            continue
        rng = random.Random(f"{seed}\0{entry['audio_norm_path']}")
        reference = entries[candidates[rng.randrange(len(candidates))]]
        row = copy.deepcopy(entry)
        row["reference_utterance_id"] = reference["audio_norm_path"]
        row["reference_audio_spec_path"] = reference["audio_spec_path"]
        row["reference_speaker_embedding_path"] = reference["speaker_embedding_path"]
        row["reference_audio_sha256"] = reference["audio_sha256"]
        paired.append(row)

    summary = {
        "schema": SCHEMA,
        "seed": seed,
        "num_input": len(entries),
        "num_output": len(paired),
        "num_excluded": len(entries) - len(paired),
        "excluded_by_reason": dict(sorted(excluded.items())),
        "split_field_present": split_present,
        "split_check": SPLIT_CHECK,
        "num_speakers_paired": len(
            {(row.get("split"), row["speaker_id"]) for row in paired}
        ),
    }
    return paired, summary


def _has_relative_paths(entries: list[dict]) -> bool:
    keys = ("audio_norm_path", "audio_spec_path", "speaker_embedding_path", "f0_path")
    return any(
        entry.get(key) and not Path(entry[key]).is_absolute()
        for entry in entries
        for key in keys
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assign each utterance a same-speaker, same-split, "
        "different-audio reference utterance for --generator-reference cross_utt."
    )
    parser.add_argument("input", type=Path, help="dataset jsonl")
    parser.add_argument("output", type=Path, help="new jsonl with reference fields")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--summary",
        type=Path,
        default=None,
        help="summary JSON (default: <output>.summary.json)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing output / summary (never the input)",
    )
    args = parser.parse_args(argv)

    input_path = args.input
    output_path = args.output
    summary_path = args.summary or output_path.with_name(
        output_path.name + ".summary.json"
    )
    if not input_path.is_file():
        raise SystemExit(f"input jsonl not found: {input_path}")
    for path in (output_path, summary_path):
        if path.resolve() == input_path.resolve():
            raise SystemExit(f"refusing to overwrite the input jsonl: {input_path}")
        if path.exists() and not args.overwrite:
            raise SystemExit(f"{path} exists; pass --overwrite to replace it")

    raw = input_path.read_bytes()
    entries = [
        json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()
    ]
    if (
        output_path.resolve().parent != input_path.resolve().parent
        and _has_relative_paths(entries)
    ):
        raise SystemExit(
            "the output must be in the same directory as the input because the "
            "dataset paths are relative to the jsonl directory "
            f"({input_path.resolve().parent})"
        )

    dataset_dir = input_path.resolve().parent
    for entry in entries:
        if not entry.get("audio_norm_path"):
            continue  # build_reference_pairs が missing_audio_norm_path で除外する
        audio = Path(entry["audio_norm_path"])
        if not audio.is_absolute():
            audio = dataset_dir / audio
        try:
            entry["audio_sha256"] = audio_sha256_of(audio)
        except Exception as exc:  # noqa: BLE001 - 壊れた cache は種類を問わず名前付きで止める
            raise SystemExit(
                f"cannot hash audio_norm {audio}: {type(exc).__name__}: {exc}"
            ) from exc

    paired, summary = build_reference_pairs(entries, args.seed)
    summary.update(
        {
            "input": str(input_path),
            "input_sha256": hashlib.sha256(raw).hexdigest(),
            "output": str(output_path),
            "audio_hash": AUDIO_HASH,
        }
    )
    _write_atomically(
        [
            # summary を先に置き、出力 jsonl は最後に置く: 出力があれば必ず
            # 対応する summary もある
            (summary_path, json.dumps(summary, ensure_ascii=False, indent=2) + "\n"),
            (
                output_path,
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in paired),
            ),
        ]
    )
    print(json.dumps(summary, ensure_ascii=False), file=sys.stderr)
    return 0


def _write_atomically(files: list[tuple[Path, str]]) -> None:
    """全ファイルを同じ directory の一時ファイルに書いてから順に rename する。

    書き込みや rename に失敗したら一時ファイルを消して SystemExit。既存の
    出力は rename されるまで元のまま残る。
    """
    staged: list[tuple[Path, Path]] = []
    try:
        for path, text in files:
            tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
            staged.append((tmp, path))
            tmp.write_text(text, encoding="utf-8")
        for tmp, path in staged:
            os.replace(tmp, path)
    except OSError as exc:
        raise SystemExit(f"cannot write {exc.filename or 'output'}: {exc}") from exc
    finally:
        for tmp, _ in staged:
            if tmp.exists():
                tmp.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
