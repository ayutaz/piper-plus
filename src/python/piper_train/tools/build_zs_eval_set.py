"""zero-shot 評価セットを、固定した仕様 JSON から組み立てる。

仕様 JSON (schema ``zs-eval-set-v1``) は、評価に使う実録音の取り出し元
(コーパスの zip の member または directory 内の file) と sha256、役割
(``speaker`` = 参照と cross 用の実発話 / ``floor`` = 別話者の実発話)、参照に
使う file、合成する文と音素 ID を持つ。本ツールは音声を取り出して hash を
検査し、参照ごとに speaker embedding を作り、``evaluation_manifest`` が読む
``test.jsonl`` を書く。録音は加工しない (取り出したバイト列のまま)。

出力の layout (``eval_zs_secs`` の speaker / floor directory にそのまま渡せる):

    <out>/groups/<group>/speaker/<file>   参照と cross 用の実発話
    <out>/groups/<group>/floor/<file>     floor 用の別話者の実発話
    <out>/groups/<group>/ref<i>.npy       references[i] の embedding
    <out>/test.jsonl                      clip ごとの文・音素 ID・参照
    <out>/set.json                        仕様名と、書いた全 file の sha256

組み立ては ``<out>`` の隣の一時 directory で行い、全検査が通った後に
rename で公開する。途中で失敗した場合は何も公開しない。

使い方:

    python -m piper_train.tools.build_zs_eval_set \\
        --spec scripts/evaluation/zs_identity/dev_set_s4.json \\
        --source moe-speech-plus=<zip directory> \\
        --source tsukuyomi-raw=<wav directory> \\
        --campplus <campplus.onnx> --output <out>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from pathlib import Path

import numpy as np


SCHEMA = "zs-eval-set-v1"
ROLES = ("speaker", "floor")
SOURCE_KINDS = ("zip-dir", "dir")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_spec(spec: dict, sources: dict[str, Path]) -> None:
    if spec.get("schema") != SCHEMA:
        raise ValueError(f"spec schema must be {SCHEMA}: {spec.get('schema')!r}")
    for name, source in spec["sources"].items():
        if source.get("kind") not in SOURCE_KINDS:
            raise ValueError(f"unknown source kind for {name}: {source.get('kind')!r}")
    for group, record in spec["groups"].items():
        names = set()
        for entry in record["files"]:
            if entry["role"] not in ROLES:
                raise ValueError(f"{group}: unknown role {entry['role']!r}")
            if entry["source"] not in spec["sources"]:
                raise ValueError(f"{group}: unknown source {entry['source']!r}")
            if entry["source"] not in sources:
                raise ValueError(
                    f"{group}: no path given for source {entry['source']!r}"
                )
            key = (entry["role"], entry["file"])
            if key in names:
                raise ValueError(f"{group}: duplicate file {key}")
            names.add(key)
        for reference in record["references"]:
            if ("speaker", reference) not in names:
                raise ValueError(
                    f"{group}: reference {reference!r} is not a speaker file"
                )
    seen = set()
    for clip in spec["clips"]:
        if clip["id"] in seen:
            raise ValueError(f"duplicate clip id {clip['id']!r}")
        seen.add(clip["id"])
        record = spec["groups"].get(clip["group"])
        if record is None:
            raise ValueError(f"{clip['id']}: unknown group {clip['group']!r}")
        if not 0 <= clip["reference"] < len(record["references"]):
            raise ValueError(f"{clip['id']}: reference index out of range")


def _read(entry: dict, spec: dict, sources: dict[str, Path]) -> bytes:
    root = Path(sources[entry["source"]])
    if spec["sources"][entry["source"]]["kind"] == "zip-dir":
        with zipfile.ZipFile(root / entry["zip"]) as archive:
            data = archive.read(entry["member"])
    else:
        data = (root / entry["member"]).read_bytes()
    if _sha256(data) != entry["sha256"]:
        raise ValueError(
            f"sha256 mismatch for {entry['file']} ({entry['source']}:"
            f"{entry.get('zip', '')}{entry['member']})"
        )
    return data


def materialize(
    spec: dict,
    sources: dict[str, Path],
    output: Path,
    embed: Callable[[Path], np.ndarray],
) -> dict:
    """Build the evaluation set at ``output``; return the ``set.json`` record."""
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory is not empty: {output}")
    _check_spec(spec, sources)
    output.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        record = {"schema": SCHEMA, "name": spec["name"], "groups": {}}
        for group, entry_group in spec["groups"].items():
            base = work / "groups" / group
            files = []
            for entry in entry_group["files"]:
                target = base / entry["role"] / entry["file"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(_read(entry, spec, sources))
                files.append(
                    {
                        "role": entry["role"],
                        "file": entry["file"],
                        "sha256": entry["sha256"],
                    }
                )
            embeddings = []
            for index, reference in enumerate(entry_group["references"]):
                vector = np.asarray(
                    embed(base / "speaker" / reference), dtype=np.float32
                )
                path = base / f"ref{index}.npy"
                np.save(path, vector, allow_pickle=False)
                embeddings.append(
                    {"reference": reference, "sha256": _sha256(path.read_bytes())}
                )
            record["groups"][group] = {"files": files, "embeddings": embeddings}
        lines = []
        for clip in spec["clips"]:
            reference = spec["groups"][clip["group"]]["references"][clip["reference"]]
            row = {
                "id": clip["id"],
                "text": clip["text"],
                "phoneme_ids": clip["phoneme_ids"],
                "language_id": clip.get("language_id", 0),
                "speaker_id": clip.get("speaker_id", 0),
                "speaker_embedding_path": f"groups/{clip['group']}/ref{clip['reference']}.npy",
                "reference_audio_paths": [
                    f"groups/{clip['group']}/speaker/{reference}"
                ],
            }
            if clip.get("prosody_features") is not None:
                row["prosody_features"] = clip["prosody_features"]
            lines.append(json.dumps(row, ensure_ascii=False) + "\n")
        (work / "test.jsonl").write_bytes("".join(lines).encode("utf-8"))
        (work / "set.json").write_bytes(
            (json.dumps(record, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        )
        if output.exists():
            output.rmdir()
        os.replace(work, output)
    finally:
        if work.exists():
            shutil.rmtree(work)
    return record


def campplus_embedder(model_path: Path) -> Callable[[Path], np.ndarray]:
    """Whole-utterance CAM++ embedding (no trim), same as the S4/S5' evaluation."""
    import onnxruntime as ort  # noqa: PLC0415

    from .cpu_reference_comparison import reference_embedding  # noqa: PLC0415

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    return lambda path: reference_embedding(session, [path])[0]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="仕様の sources に書いた名前と、その実体の directory",
    )
    parser.add_argument("--campplus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    sources = {}
    for item in args.source:
        name, sep, path = item.partition("=")
        if not sep:
            parser.error(f"--source must be NAME=PATH: {item!r}")
        sources[name] = Path(path)
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    record = materialize(spec, sources, args.output, campplus_embedder(args.campplus))
    print(
        f"wrote {args.output} ({len(record['groups'])} groups, {len(spec['clips'])} clips)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
