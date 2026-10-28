"""組み立て済みの zero-shot 評価セットで、群ごとに cross-utt SECS を測る。

``build_zs_eval_set`` が作ったセット (``set.json`` + ``test.jsonl``) と、
``generate_eval_audio generate`` の出力 directory (``generation.json`` + wav) を
受け取り、群 (話者) ごとに合成音声を分けて ``eval_zs_secs`` を呼ぶ。参照に
使った実発話は ``--exclude-ref`` で cross 集合から除く。第 2 encoder (ECAPA) は
必須 (契約 docs/spec/zs-eval-contract.md §2)。

出力:

    <out>/synth/<group>/*.wav   群ごとの合成音声 (generation.json と hash 一致を検査済み)
    <out>/secs/<group>.json     eval_zs_secs の report (zs-eval-v3)
    <out>/summary.json          群ごとの主な値、日本語群 (ja_*) の平均、flag の一覧

``summary.json`` の平均は報告用の集計で、合否は判定しない。判定は計画書の規則
(docs/design/zero-shot-speaker-identity-plan-2026-10-29.md) に照らして行う。

使い方:

    python -m piper_train.tools.run_zs_eval_set \\
        --set <built set> --generation <wav dir> \\
        --encoder campplus.onnx --encoder2 ecapa.onnx --output <out> \\
        [--baseline <前回の out>] [--label E0]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
from collections.abc import Callable
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _group_of(row: dict) -> str:
    parts = Path(row["speaker_embedding_path"]).parts
    if len(parts) < 3 or parts[0] != "groups":
        raise ValueError(f"{row['id']}: embedding path is not under groups/: {parts}")
    return parts[1]


def _summarize(group: str, report: dict) -> dict:
    encoders = report["encoders"]
    row = {}
    for name in ("campplus", "encoder2"):
        block = encoders.get(name) or {}
        for key in ("normalized_transfer", "cross_utt_secs", "ceiling", "floor"):
            row[f"{name}_{key}"] = block.get(key)
    comb = (report.get("comb") or {}).get("synth") or {}
    row["comb_excess_db_median"] = comb.get("comb_excess_db_median")
    row["goodhart_flag"] = report.get("goodhart_flag")
    row["above_ceiling_flag"] = report.get("above_ceiling_flag")
    return row


def _mean(rows: list[dict], key: str):
    values = [r[key] for r in rows if r.get(key) is not None]
    return statistics.fmean(values) if values else None


def run(
    set_dir: Path,
    generation_dir: Path,
    output: Path,
    encoder: str,
    encoder2: str,
    evaluate: Callable[[list[str]], int] | None = None,
    *,
    baseline: Path | None = None,
    label: str | None = None,
    skip_acoustics: bool = False,
) -> dict:
    if evaluate is None:
        from . import eval_zs_secs  # noqa: PLC0415

        evaluate = eval_zs_secs.main
    set_dir, generation_dir, output = Path(set_dir), Path(generation_dir), Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    record = json.loads((set_dir / "set.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (set_dir / "test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    generation = json.loads(
        (generation_dir / "generation.json").read_text(encoding="utf-8")
    )
    expected = {clip["id"]: clip["wav_sha256"] for clip in generation["clips"]}

    groups: dict[str, list[str]] = {name: [] for name in record["groups"]}
    for row in rows:
        group = _group_of(row)
        if group not in groups:
            raise ValueError(f"{row['id']}: group {group!r} is not in set.json")
        wav = generation_dir / f"{row['id']}.wav"
        if row["id"] not in expected or _sha256(wav) != expected[row["id"]]:
            raise ValueError(f"sha256 of {wav} does not match generation.json")
        groups[group].append(row["id"])

    meta = {
        "label": label,
        "set": str(set_dir.resolve()),
        "set_name": record.get("name"),
        "generation": str(generation_dir.resolve()),
        "backend": generation.get("backend"),
        "seed": generation.get("seed"),
        "scales": generation.get("scales"),
        "training_epoch": generation.get("training_epoch"),
    }
    (output / "secs").mkdir(parents=True, exist_ok=True)
    meta_path = output / "meta.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    summaries = {}
    for group, ids in groups.items():
        synth = output / "synth" / group
        synth.mkdir(parents=True)
        for clip_id in ids:
            shutil.copyfile(generation_dir / f"{clip_id}.wav", synth / f"{clip_id}.wav")
        base = set_dir / "groups" / group
        argv = [
            "--synth-dir", str(synth),
            "--speaker-utts", str(base / "speaker"),
            "--floor-refs", str(base / "floor"),
            "--encoder", encoder,
            "--encoder2", encoder2,
            "--require-encoder2",
            "--meta-json", str(meta_path),
            "--floor-selection-note", f"{record.get('name')}: fixed in set spec",
            "--json-out", str(output / "secs" / f"{group}.json"),
        ]  # fmt: skip
        for item in record["groups"][group]["embeddings"]:
            argv += ["--exclude-ref", str(base / "speaker" / item["reference"])]
        if baseline is not None:
            argv += ["--baseline-json", str(Path(baseline) / "secs" / f"{group}.json")]
        if skip_acoustics:
            argv.append("--skip-acoustics")
        status = evaluate(argv)
        if status:
            raise RuntimeError(f"eval_zs_secs failed for {group} (exit {status})")
        report = json.loads(
            (output / "secs" / f"{group}.json").read_text(encoding="utf-8")
        )
        summaries[group] = _summarize(group, report)

    japanese = [row for group, row in summaries.items() if group.startswith("ja_")]
    keys = [k for k in next(iter(summaries.values())) if not k.endswith("_flag")]
    summary = {
        **meta,
        "groups": summaries,
        "ja_mean": {key: _mean(japanese, key) for key in keys},
        "comb_excess_db_mean_all": _mean(
            list(summaries.values()), "comb_excess_db_median"
        ),
        "flags": {
            "goodhart": [g for g, r in summaries.items() if r["goodhart_flag"] is True],
            "above_ceiling": [
                g for g, r in summaries.items() if r["above_ceiling_flag"] is True
            ],
        },
    }
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--set", type=Path, required=True)
    parser.add_argument("--generation", type=Path, required=True)
    parser.add_argument("--encoder", required=True, help="CAM++ ONNX")
    parser.add_argument(
        "--encoder2", required=True, help="held-out 第 2 encoder (ECAPA ONNX)"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--baseline", type=Path, help="比較の基準にする前回の出力 directory"
    )
    parser.add_argument("--label")
    parser.add_argument("--skip-acoustics", action="store_true")
    args = parser.parse_args(argv)
    summary = run(
        args.set,
        args.generation,
        args.output,
        args.encoder,
        args.encoder2,
        baseline=args.baseline,
        label=args.label,
        skip_acoustics=args.skip_acoustics,
    )
    print(
        json.dumps({"ja_mean": summary["ja_mean"], "flags": summary["flags"]}, indent=1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
