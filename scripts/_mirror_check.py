# editorconfig-checker-disable-file (docstring uses 2-space indented bullet lists)
"""Shared helper for canonical→mirror byte-equal sync gates.

A growing family of `scripts/check_*_consistency.py` and
`scripts/check_*_parity.py` scripts implement the same pattern:

  1. Declare a canonical source-of-truth file path.
  2. Declare N mirror file paths that must be byte-for-byte equal.
  3. SHA256-compare canonical vs each mirror.
  4. Offer `--fix` (canonical → mirror) and `--diff` (unified diff dry run).
  5. Optional schema validation on the canonical (loanword JSON).
  6. Optional `--allow-missing` phase-in mode.

This helper centralises that pattern so each gate is a thin
wrapper that points at a declarative TOML spec
(`docs/spec/<name>-mirrors.toml`). Specs surface the mirror list to
reviewers in a single place; the wrapper script becomes ~10 lines.

# Usage from a thin wrapper

    # scripts/check_dictionary_consistency.py
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from _mirror_check import run_from_toml  # noqa: E402

    sys.exit(run_from_toml(
        Path(__file__).resolve().parent.parent
        / "docs/spec/dictionary-mirrors.toml",
        argv=sys.argv[1:],
    ))

# Schema validator hook (loanword)

    from _mirror_check import run_from_toml, register_schema_validator
    register_schema_validator("zh_en_loanword", validate_loanword_schema)
    sys.exit(run_from_toml("docs/spec/loanword-mirrors.toml",
                           argv=sys.argv[1:]))

The validator is keyed by the TOML `[[groups]].name`; absent registration,
the canonical file is read as bytes only (no schema check). This keeps the
forward-compat behaviour of the original loanword loader (`schema_version: 2`
acceptance, unknown top-level field acceptance).

# TOML schema

    schema_version = 1

    [[groups]]
    name = "default_common dictionary"
    canonical = "data/dictionaries/default_common_dict.json"
    mirrors = ["src/wasm/openjtalk-web/assets/default_common_dict.json"]
    # allow_missing_default = false           # optional, defaults false
    # notes = "..."                           # informational only
    # incident_refs = ["Issue #384"]          # informational only
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import shutil
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

SchemaValidator = Callable[[Path], None]

_SCHEMA_VALIDATORS: dict[str, SchemaValidator] = {}


def register_schema_validator(group_name: str, fn: SchemaValidator) -> None:
    """Register a callable invoked on the canonical of the matching group.

    The validator should raise ValueError / json.JSONDecodeError on a
    schema violation; the helper turns that into a non-zero exit with a
    `SCHEMA ERROR:` prefix matching the legacy scripts.
    """
    _SCHEMA_VALIDATORS[group_name] = fn


@dataclass
class MirrorGroup:
    """A single canonical → N mirror declaration."""

    name: str
    canonical: Path
    mirrors: list[Path]
    allow_missing_default: bool = False
    notes: str = ""
    incident_refs: list[str] = field(default_factory=list)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _show_diff(src: Path, dst: Path) -> None:
    src_lines = src.read_text(encoding="utf-8").splitlines(keepends=True)
    dst_lines = (
        dst.read_text(encoding="utf-8").splitlines(keepends=True)
        if dst.exists()
        else []
    )
    diff = difflib.unified_diff(
        dst_lines,
        src_lines,
        fromfile=str(dst.relative_to(REPO_ROOT)) if dst.is_absolute() else str(dst),
        tofile=str(src.relative_to(REPO_ROOT)) if src.is_absolute() else str(src),
        n=1,
    )
    sys.stdout.writelines(diff)


def _process_pair(
    canonical: Path,
    mirror: Path,
    src_hash: str,
    *,
    fix: bool,
    diff: bool,
    allow_missing: bool,
    failed: list[str],
    fixed: list[str],
    warnings: list[str],
) -> None:
    rel = mirror.relative_to(REPO_ROOT) if mirror.is_absolute() else mirror
    if not mirror.exists():
        if fix:
            mirror.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(canonical, mirror)
            fixed.append(f"created {rel}")
            return
        if allow_missing:
            warnings.append(f"MISSING (allowed) {rel}")
            return
        failed.append(f"MISSING {rel}")
        return
    if _sha256(mirror) == src_hash:
        return
    if diff:
        _show_diff(canonical, mirror)
    if fix:
        shutil.copy2(canonical, mirror)
        fixed.append(f"synced {rel}")
        return
    failed.append(f"MISMATCH {rel}")


def run_check(
    groups: list[MirrorGroup],
    *,
    fix: bool = False,
    diff: bool = False,
    schema_only: bool = False,
    allow_missing: bool = False,
) -> int:
    """Verify every (canonical → mirror) pair declared in `groups`.

    Returns process exit code: 0 on success, 1 on any failure.
    `allow_missing=True` overrides every group's per-group default.
    """
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    failed: list[str] = []
    fixed: list[str] = []
    warnings: list[str] = []
    total_mirrors = 0

    for g in groups:
        rel_c = (
            g.canonical.relative_to(REPO_ROOT)
            if g.canonical.is_absolute()
            else g.canonical
        )
        if not g.canonical.exists():
            if allow_missing or g.allow_missing_default:
                warnings.append(f"CANONICAL MISSING (allowed) {rel_c}  [{g.name}]")
                continue
            print(
                f"ERROR: canonical missing: {rel_c}  [{g.name}]",
                file=sys.stderr,
            )
            return 1

        validator = _SCHEMA_VALIDATORS.get(g.name)
        if validator is not None:
            try:
                validator(g.canonical)
            except Exception as e:
                print(f"SCHEMA ERROR: {e}", file=sys.stderr)
                return 1

        if schema_only:
            print(f"OK schema: {rel_c}  [{g.name}]")
            continue

        src_hash = _sha256(g.canonical)
        print(f"Group {g.name}: {src_hash} ({rel_c})")

        effective_allow_missing = allow_missing or g.allow_missing_default
        for m in g.mirrors:
            total_mirrors += 1
            _process_pair(
                g.canonical,
                m,
                src_hash,
                fix=fix,
                diff=diff,
                allow_missing=effective_allow_missing,
                failed=failed,
                fixed=fixed,
                warnings=warnings,
            )

    for w in warnings:
        print(f"  WARN  {w}")
    for f in fixed:
        print(f"  FIXED {f}")

    if failed:
        print("", file=sys.stderr)
        for f in failed:
            print(f"  FAIL  {f}", file=sys.stderr)
        print(
            f"\n{len(failed)} file(s) out of sync across "
            f"{len(groups)} group(s). Run with --fix to copy from canonical.",
            file=sys.stderr,
        )
        return 1

    if schema_only:
        return 0

    if not fixed and not warnings:
        print(
            f"\nOK All {total_mirrors} mirror(s) in sync across {len(groups)} group(s)"
        )
    elif fixed and not failed:
        print(f"\nOK applied {len(fixed)} fix(es)")
    return 0


def load_groups(toml_path: Path) -> list[MirrorGroup]:
    """Parse a mirrors TOML spec into MirrorGroup instances."""
    with toml_path.open("rb") as f:
        spec = tomllib.load(f)

    if spec.get("schema_version") not in (1, None):
        raise ValueError(
            f"{toml_path}: unsupported schema_version "
            f"{spec.get('schema_version')!r} (helper supports 1)"
        )

    groups_raw = spec.get("groups", [])
    if not isinstance(groups_raw, list) or not groups_raw:
        raise ValueError(f"{toml_path}: [[groups]] array missing or empty")

    out: list[MirrorGroup] = []
    for i, g in enumerate(groups_raw):
        try:
            name = g["name"]
            canonical = REPO_ROOT / g["canonical"]
            mirrors = [REPO_ROOT / m for m in g["mirrors"]]
        except KeyError as e:
            raise ValueError(
                f"{toml_path}: [[groups]][{i}] missing required field {e}"
            ) from None
        out.append(
            MirrorGroup(
                name=name,
                canonical=canonical,
                mirrors=mirrors,
                allow_missing_default=bool(g.get("allow_missing_default", False)),
                notes=str(g.get("notes", "")),
                incident_refs=list(g.get("incident_refs", []) or []),
            )
        )
    return out


def run_from_toml(toml_path: str | Path, *, argv: list[str] | None = None) -> int:
    """End-to-end entry: load TOML, parse argv, run check."""
    parser = argparse.ArgumentParser(
        description="Canonical → mirror byte-equal sync gate (TOML-driven)",
    )
    parser.add_argument(
        "--fix", action="store_true", help="canonical → mirror 一方向コピー"
    )
    parser.add_argument(
        "--diff", action="store_true", help="--fix 前の dry-run unified diff"
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="hash check skip、登録された schema validator のみ実行",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="missing path を warn 扱いにして exit 0 (phase-in モード)",
    )
    args = parser.parse_args(argv)

    toml_p = Path(toml_path)
    if not toml_p.is_absolute():
        toml_p = REPO_ROOT / toml_p
    if not toml_p.exists():
        print(f"ERROR: mirrors spec missing: {toml_p}", file=sys.stderr)
        return 1

    try:
        groups = load_groups(toml_p)
    except (ValueError, tomllib.TOMLDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return run_check(
        groups,
        fix=args.fix,
        diff=args.diff,
        schema_only=args.schema_only,
        allow_missing=args.allow_missing,
    )
