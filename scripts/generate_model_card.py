#!/usr/bin/env python3
"""Model card / LICENSE_ATTRIBUTIONS auto-generation (M3.2).

``data-sources.yml`` を canonical source として ``MODEL_CARD.md`` と
``LICENSE_ATTRIBUTIONS.md`` を deterministic に生成する CLI。 HF Hub に
ONNX を upload する直前 (`deploy-huggingface.yml`) と shared lib release
(`release-shared-lib.yml`) の前段で本 script が走り、 attribution が
artifact 同梱物に確実に含まれるようにする。

設計上の不変条件:

* 入力 YAML が同じなら出力 markdown は byte-identical (テスト容易性 +
  diff レビュー性)。
* ``license.verified: false`` の dataset は MODEL_CARD に明示的な warning を
  emit する (法務承認待ちを目に見える形で残す)。
* ``used_only_in`` で対応モデルを絞り込んだ生成も可能 (e.g.
  ``--model tsukuyomi-6lang-v2`` で対応 dataset のみ出す)。
* CLI のサブコマンドは ``generate`` (markdown 生成) と ``validate``
  (YAML 整合性のみチェック) の 2 つ。

PyYAML を使う (pyproject 依存に明示的に存在)。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_YAML = REPO_ROOT / "data-sources.yml"


@dataclass
class Dataset:
    id: str
    title: str
    languages: list[str]
    speakers: int
    utterances: int
    spdx: str
    license_url: str
    verified: bool
    source_url: str
    source_revision: str
    attribution_required: bool
    attribution_text: str
    used_only_in: list[str]

    @classmethod
    def from_dict(cls, d: dict) -> Dataset:
        license_block = d.get("license", {})
        source_block = d.get("source", {})
        return cls(
            id=d["id"],
            title=d["title"],
            languages=list(d.get("languages", [])),
            speakers=int(d.get("speakers", 0)),
            utterances=int(d.get("utterances", 0)),
            spdx=str(license_block.get("spdx", "UNKNOWN")),
            license_url=str(license_block.get("url", "")),
            verified=bool(license_block.get("verified", False)),
            source_url=str(source_block.get("url", "")),
            source_revision=str(source_block.get("commit_or_version", "unspecified")),
            attribution_required=bool(d.get("attribution_required", False)),
            attribution_text=str(d.get("attribution_text", "")).strip(),
            used_only_in=list(d.get("used_only_in", [])),
        )


def load_yaml(path: Path) -> tuple[dict, list[Dataset]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != 1:
        raise SystemExit(
            f"unsupported schema_version: {raw.get('schema_version')!r} (expected 1)"
        )
    datasets = [Dataset.from_dict(d) for d in raw.get("datasets", [])]
    return raw, datasets


def filter_for_model(datasets: list[Dataset], model: str | None) -> list[Dataset]:
    if model is None:
        return datasets
    return [d for d in datasets if not d.used_only_in or model in d.used_only_in]


def render_model_card(meta: dict, datasets: list[Dataset], model: str | None) -> str:
    lines = [
        "# Model card",
        "",
        f"Generated from `data-sources.yml` (schema_version={meta.get('schema_version')}, "
        f"last reviewed {meta.get('last_reviewed')}).",
        "",
    ]
    if model:
        lines.append(f"Model: **{model}**")
        lines.append("")
    unverified = [d for d in datasets if not d.verified]
    if unverified:
        lines.append(
            "> ⚠️ The following dataset license entries are *pending maintainer review*:"
        )
        lines.append(">")
        for d in unverified:
            lines.append(f"> - `{d.id}` ({d.spdx})")
        lines.append("")
    lines.append("## Training data")
    lines.append("")
    lines.append("| Dataset | Lang | Speakers | Utterances | License | Source |")
    lines.append("|---------|------|----------|------------|---------|--------|")
    for d in datasets:
        langs = ", ".join(d.languages) if d.languages else "—"
        license_cell = f"[{d.spdx}]({d.license_url})" if d.license_url else d.spdx
        source_cell = (
            f"[{d.source_revision}]({d.source_url})"
            if d.source_url
            else d.source_revision
        )
        lines.append(
            f"| `{d.id}` ({d.title}) | {langs} | {d.speakers} | {d.utterances} | "
            f"{license_cell} | {source_cell} |"
        )
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append(
        "The full attribution text required for redistribution is also bundled "
        "in `LICENSE_ATTRIBUTIONS.md`. Keep that file with the ONNX when you "
        "redistribute the model."
    )
    return "\n".join(lines).rstrip() + "\n"


def render_attributions(datasets: list[Dataset]) -> str:
    lines = ["# License attributions", ""]
    required = [d for d in datasets if d.attribution_required]
    if not required:
        lines.append("_No dataset requires explicit attribution._")
        return "\n".join(lines).rstrip() + "\n"
    for d in required:
        lines.append(f"## {d.title}")
        lines.append("")
        lines.append(f"- License: {d.spdx} ({d.license_url})")
        if d.source_url:
            lines.append(f"- Source: {d.source_url} ({d.source_revision})")
        lines.append("")
        if d.attribution_text:
            for paragraph in d.attribution_text.split("\n\n"):
                lines.append(paragraph.rstrip())
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def cmd_generate(args: argparse.Namespace) -> int:
    meta, datasets = load_yaml(args.input)
    datasets = filter_for_model(datasets, args.model)
    model_card = render_model_card(meta, datasets, args.model)
    attributions = render_attributions(datasets)
    args.model_card.write_text(model_card, encoding="utf-8")
    args.attributions.write_text(attributions, encoding="utf-8")
    print(
        f"Wrote {args.model_card} ({len(model_card)} bytes) and "
        f"{args.attributions} ({len(attributions)} bytes) "
        f"for {len(datasets)} dataset(s)."
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Confirm the YAML is parseable and that every dataset entry has the
    keys the renderer relies on. Used by the pre-commit hook so a typo in
    `data-sources.yml` is caught before release."""
    meta, datasets = load_yaml(args.input)
    errors: list[str] = []
    seen_ids: set[str] = set()
    for d in datasets:
        if d.id in seen_ids:
            errors.append(f"duplicate dataset id: {d.id!r}")
        seen_ids.add(d.id)
        if d.spdx == "UNKNOWN":
            errors.append(f"{d.id}: missing license.spdx")
        if d.attribution_required and not d.attribution_text:
            errors.append(f"{d.id}: attribution_required but attribution_text is empty")
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(
        f"data-sources.yml OK ({len(datasets)} datasets, "
        f"last_reviewed {meta.get('last_reviewed')})."
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--input", type=Path, default=DEFAULT_YAML)
    g.add_argument(
        "--model", default=None, help="Filter to datasets used_only_in this model."
    )
    g.add_argument("--model-card", type=Path, required=True)
    g.add_argument("--attributions", type=Path, required=True)
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("validate")
    v.add_argument("--input", type=Path, default=DEFAULT_YAML)
    v.set_defaults(func=cmd_validate)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
