"""Align a preprocessed single-speaker dataset with a trained base vocabulary.

Equal vocabulary sizes do not imply equal token IDs. Audio caches remain in
the input directory; the new dataset references them by absolute path.
"""

import argparse
import json
from pathlib import Path


def prepare(source: Path, base_config: Path, output: Path) -> int:
    source, base_config, output = map(Path, (source, base_config, output))
    if output.exists():
        raise FileExistsError(output)
    old = json.loads((source / "config.json").read_text(encoding="utf-8"))
    base = json.loads(base_config.read_text(encoding="utf-8"))
    if old["num_speakers"] != 1:
        raise ValueError("This helper requires a single-speaker input dataset")
    inverse = {}
    for token, ids in old["phoneme_id_map"].items():
        if len(ids) != 1 or ids[0] in inverse:
            raise ValueError("Source vocabulary must assign a unique ID to each token")
        inverse[ids[0]] = token
    old_languages = {v: k for k, v in old.get("language_id_map", {"ja": 0}).items()}
    new_languages = base["language_id_map"]
    entries = []
    for number, line in enumerate(
        (source / "dataset.jsonl").read_text(encoding="utf-8").splitlines(), 1
    ):
        entry = json.loads(line)
        remapped = []
        for old_id in entry["phoneme_ids"]:
            token = inverse.get(old_id)
            target = base["phoneme_id_map"].get(token)
            if target is None or len(target) != 1:
                raise ValueError(
                    f"Line {number}: token {token!r} (ID {old_id}) is absent from the base vocabulary"
                )
            if not 0 <= target[0] < base["num_symbols"]:
                raise ValueError(f"Invalid base token ID for {token!r}")
            remapped.append(target[0])
        prosody = entry.get("prosody_features")
        if prosody is not None and len(prosody) != len(remapped):
            raise ValueError(f"Line {number}: prosody length differs from phoneme IDs")
        language = old_languages.get(entry.get("language_id", 0))
        if language not in new_languages:
            raise ValueError(
                f"Line {number}: language {language!r} is absent from the base"
            )
        entry["phoneme_ids"] = remapped
        entry["language_id"] = new_languages[language]
        entry.pop("speaker_embedding_path", None)
        entry.pop("speaker_id", None)
        for key in ["audio_norm_path", "audio_spec_path"]:
            # New preprocess output can carry paths relative to its working
            # directory; older prepared datasets use dataset-relative paths.
            candidates = {(source / entry[key]).resolve(), Path(entry[key]).resolve()}
            matches = [path for path in candidates if path.is_file()]
            if not matches:
                raise ValueError(f"Line {number}: missing cache {entry[key]}")
            if len(matches) != 1:
                raise ValueError(
                    f"Line {number}: ambiguous cache {entry[key]}; use an absolute path"
                )
            path = matches[0]
            entry[key] = str(path)
        entries.append(entry)
    if not entries:
        raise ValueError("Input dataset is empty")
    # Validate every utterance before creating an output or writing files.
    output.mkdir(parents=True)
    base.update(num_speakers=1, speaker_id_map={}, dataset=output.name)
    (output / "config.json").write_text(
        json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (output / "dataset.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in entries),
        encoding="utf-8",
    )
    return len(entries)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            {"utterances": prepare(args.input_dir, args.base_config, args.output_dir)}
        )
    )


if __name__ == "__main__":
    main()
