"""Map tokens dropped by the 185-symbol table onto existing symbols (plan §7.5 P0-8).

The multilingual G2P emits tokens that are not in the phoneme_id_map, and
``prepare_multilingual_dataset`` silently drops them: the word-boundary space
and punctuation of en/es/fr/pt/zh, pt ``ã``, es ``ʝ`` and fr ``ɥ``.  Adding new
symbols would grow the embedding table (and the FP16 ONNX past the v10b size
limit), so each one is mapped onto a symbol the table already has:

- space -> ``#`` (the Japanese accent-phrase boundary)
- ``, . ! ; : —`` -> ``_`` (the Japanese short pause; becomes a double pad)
- ``ã`` -> ``ɐ̃`` (its IPA, already in the table), ``ʝ`` -> ``j``, ``ɥ`` -> ``y``

``num_symbols`` stays the same.  The aliases go into the model config's
phoneme_id_map, so a runtime that looks tokens up in the config map gets the
same ids.  Rows are re-encoded from their stored ``phonemes``; the stored
prosody of kept tokens is carried over and aliased tokens get ``None``.

usage:
  python -m piper_train.tools.phoneme_aliases remap --jsonl IN --config IN \
      --out-jsonl OUT --out-config OUT [--report OUT.json]
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import sys
from pathlib import Path

from piper_plus_g2p.encode.pua import map_token


ALIASES: dict[str, str] = {
    " ": "#",
    ",": "_",
    ".": "_",
    "!": "_",
    ";": "_",
    ":": "_",
    "—": "_",  # em dash
    "ã": "ɐ̃",  # ã -> ɐ̃
    "ʝ": "j",  # ʝ
    "ɥ": "y",  # ɥ
}


def extend_id_map(id_map: dict[str, list[int]]) -> dict[str, list[int]]:
    """Return *id_map* plus the alias keys, each pointing at an existing id."""
    out = dict(id_map)
    for raw, target in ALIASES.items():
        key = map_token(raw)
        if key in id_map:
            raise ValueError(f"alias {raw!r} is already in the table")
        out[key] = list(id_map[map_token(target)])
    return out


def _encode(tokens, prosody, id_map, eos):
    pad = id_map.get("_", [0])
    ids: list[int] = list(id_map["^"]) + [pad[0]]
    pros: list = [None] * len(ids)
    for i, p in zip(tokens, prosody, strict=True):
        ids.append(i)
        pros.append(p)
        if i not in pad:
            ids.extend(pad)
            pros.extend([None] * len(pad))
    ids.extend(eos)
    pros.extend([None] * len(eos))
    return ids, pros


def remap_row(
    row: dict, old_map: dict[str, list[int]], new_map: dict[str, list[int]]
) -> dict:
    """Re-encode one dataset row with *new_map*; raise if *old_map* does not reproduce it."""
    phonemes = row.get("phonemes") or []
    if not phonemes:
        return row
    pad = old_map.get("_", [0])
    old_ids: list[int] = []
    src: list[int | None] = []  # per old id: index of its token
    for k, tok in enumerate(phonemes):
        key = map_token(tok)
        if key in old_map:
            old_ids.extend(old_map[key])
            src.extend([k] * len(old_map[key]))
    stored = row["phoneme_ids"]
    # The EOS is '$', or the last token itself (rows ending in '?' use it as the EOS).
    for n_body, eos in ((len(old_ids), old_map["$"]), (len(old_ids) - 1, old_ids[-1:])):
        body = old_ids[:n_body]
        if _encode(body, [None] * len(body), old_map, eos)[0] == stored:
            break
    else:
        raise ValueError(
            f"row is not reproduced by the original map: {row.get('audio_path')}"
        )
    eos_token = None if n_body == len(old_ids) else src[-1]
    # prosody of each kept token, read at the position the old encoding put it
    tok_pros: dict[int, object] = {}
    pos = len(old_map["^"]) + 1
    for i, k in zip(body, src[:n_body], strict=True):
        tok_pros.setdefault(k, row["prosody_features"][pos])
        pos += 1 + (0 if i in pad else len(pad))
    new_ids: list[int] = []
    new_pros: list = []
    for k, tok in enumerate(phonemes):
        if k == eos_token:
            break
        key = map_token(tok)
        if key in old_map:
            new_ids.extend(old_map[key])
            new_pros.extend([tok_pros[k]] * len(old_map[key]))
        elif key in new_map:
            new_ids.extend(new_map[key])
            new_pros.extend([None] * len(new_map[key]))
    ids, pros = _encode(new_ids, new_pros, new_map, eos)
    out = dict(row)
    out["phoneme_ids"] = ids
    out["prosody_features"] = pros
    return out


def _open(path: Path, mode: str):
    if path.suffix == ".gz":
        return gzip.open(path, mode + "t", encoding="utf-8", newline="\n")
    return open(path, mode, encoding="utf-8", newline="\n")


def cmd_remap(a: argparse.Namespace) -> int:
    config = json.loads(a.config.read_text(encoding="utf-8"))
    old_map = config["phoneme_id_map"]
    new_map = extend_id_map(old_map)
    max_ids = a.max_phoneme_ids
    rows = collections.Counter()
    changed = collections.Counter()
    over_old = collections.Counter()
    over_new = collections.Counter()
    added = collections.Counter()
    alias_keys = {map_token(r): r for r in ALIASES}
    with _open(a.jsonl, "r") as fi, _open(a.out_jsonl, "w") as fo:
        for line in fi:
            row = json.loads(line)
            lid = str(row["language_id"])
            out = remap_row(row, old_map, new_map)
            rows[lid] += 1
            if out["phoneme_ids"] != row["phoneme_ids"]:
                changed[lid] += 1
                for tok in row["phonemes"]:
                    if map_token(tok) in alias_keys:
                        added[f"{lid} {tok!r}"] += 1
            over_old[lid] += len(row["phoneme_ids"]) > max_ids
            over_new[lid] += len(out["phoneme_ids"]) > max_ids
            fo.write(json.dumps(out, ensure_ascii=False) + "\n")
    config["phoneme_id_map"] = new_map
    a.out_config.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = {
        "rows": dict(rows),
        "changed": dict(changed),
        f"over_{max_ids}_before": dict(over_old),
        f"over_{max_ids}_after": dict(over_new),
        "alias_tokens_added": dict(added.most_common()),
        "num_symbols": config.get("num_symbols"),
        "distinct_ids": len({v[0] for v in new_map.values()}),
    }
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if a.report:
        a.report.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("remap", help="re-encode a dataset jsonl with the alias map")
    r.add_argument("--jsonl", type=Path, required=True)
    r.add_argument("--config", type=Path, required=True)
    r.add_argument("--out-jsonl", type=Path, required=True)
    r.add_argument("--out-config", type=Path, required=True)
    r.add_argument("--report", type=Path)
    r.add_argument("--max-phoneme-ids", type=int, default=400)
    a = ap.parse_args(argv)
    return cmd_remap(a)


if __name__ == "__main__":
    sys.exit(main())
