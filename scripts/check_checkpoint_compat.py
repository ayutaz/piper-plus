#!/usr/bin/env python3
"""Check that published checkpoints still load into the current model.

Issue #616 shipped because nothing tied the model's module layout to the
checkpoints already in users' hands. PR #579 widened
``MBiSTFTGenerator.cond`` and every published checkpoint stopped loading —
no test noticed, because every test builds its checkpoints *from the current
model definition* and is therefore self-consistent by construction.

This gate closes that loop. ``docs/spec/checkpoint-compat-contract.toml``
records, for each published checkpoint, the hyper-parameters it was trained
with and the exact ``key -> shape`` map of its ``state_dict`` (and of its EMA
shadow params). The gate rebuilds a model from those hyper-parameters, runs the
recorded shapes through ``normalize_checkpoint_state_dict``, and requires a
``strict=True`` load to succeed.

No download and no GPU: only shapes are stored, and the tensors are
materialised as zeros.

What a failure means
--------------------
A model-architecture change made a published checkpoint unloadable. Either

* add the migration to ``piper_train.vits.commons`` so old checkpoints keep
  working (preferred — see ``migrate_prefilm_decoder_cond`` for the pattern), or
* if the break is deliberate and unavoidable, publish a new checkpoint, update
  the contract with ``--update-snapshot``, and document the break in
  ``CHANGELOG.md`` under ``### Breaking`` with a migration guide entry.

Regenerating the snapshot to make CI green, without one of the above,
reintroduces exactly the bug this gate exists to prevent.

Usage:
    python scripts/check_checkpoint_compat.py
    python scripts/check_checkpoint_compat.py --update-snapshot <ckpt> --name <id>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACT = REPO_ROOT / "docs" / "spec" / "checkpoint-compat-contract.toml"

sys.path.insert(0, str(REPO_ROOT / "src" / "python"))


def _parse_shape(raw: str) -> tuple[int, ...]:
    raw = raw.strip()
    if not raw:
        return ()
    return tuple(int(part) for part in raw.split("x"))


def _format_shape(shape) -> str:
    return "x".join(str(int(dim)) for dim in shape)


def _build_model(hparams: dict):
    from piper_train.vits.lightning import VitsModel  # noqa: PLC0415

    kwargs = dict(hparams)
    kwargs["dataset"] = None
    # TOML has no tuple type; the model wants tuples for these.
    for key in (
        "resblock_kernel_sizes",
        "upsample_rates",
        "upsample_kernel_sizes",
        "betas",
    ):
        if key in kwargs and isinstance(kwargs[key], list):
            kwargs[key] = tuple(kwargs[key])
    if isinstance(kwargs.get("resblock_dilation_sizes"), list):
        kwargs["resblock_dilation_sizes"] = tuple(
            tuple(inner) for inner in kwargs["resblock_dilation_sizes"]
        )
    return VitsModel(**kwargs)


def _check_entry(entry: dict) -> list[str]:
    import torch  # noqa: PLC0415

    from piper_train.vits.commons import (  # noqa: PLC0415
        migrate_prefilm_decoder_cond,
        normalize_checkpoint_state_dict,
    )

    name = entry["name"]
    errors: list[str] = []

    model = _build_model(entry["hparams"])
    model_sd = model.state_dict()

    saved_sd = {
        key: torch.zeros(_parse_shape(shape))
        for key, shape in entry["state_dict_shapes"].items()
    }

    try:
        normalized, _stats = normalize_checkpoint_state_dict(
            saved_sd, model_sd, checkpoint_path=name
        )
    except RuntimeError as exc:
        errors.append(f"[{name}] normalisation raised: {exc}")
        return errors

    try:
        model.load_state_dict(normalized, strict=True)
    except RuntimeError as exc:
        errors.append(
            f"[{name}] strict load failed after normalisation.\n"
            f"        {exc}\n"
            f"        A published checkpoint can no longer be loaded by the "
            f"current model."
        )

    ema_shapes = entry.get("ema_shadow_shapes")
    if ema_shapes:
        decoder_sd = model.model_g.dec.state_dict()
        shadow = {
            key: torch.zeros(_parse_shape(shape)) for key, shape in ema_shapes.items()
        }
        shadow, _ = migrate_prefilm_decoder_cond(shadow, decoder_sd)
        dec_params = dict(model.model_g.dec.named_parameters())
        for key, value in shadow.items():
            target = dec_params.get(key)
            if target is None:
                continue
            if tuple(target.shape) != tuple(value.shape):
                errors.append(
                    f"[{name}] EMA shadow param '{key}' has shape "
                    f"{tuple(value.shape)} but the decoder expects "
                    f"{tuple(target.shape)}; applying EMA would raise."
                )

    return errors


def _update_snapshot(checkpoint_path: str, name: str) -> int:
    import torch  # noqa: PLC0415

    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    # Host-specific values (the trainer's dataset paths, output dir) are both
    # unserialisable and irrelevant to the shape contract, and would trip the
    # secret-path gate. The model builder does not need them.
    skip = {"dataset", "default_root_dir", "speaker_id"}

    def _keep(value) -> bool:
        if isinstance(value, bool) or isinstance(value, (int, float, str)):
            return True
        if isinstance(value, (list, tuple)):
            return all(_keep(item) for item in value)
        return False

    hparams = {
        key: value
        for key, value in ckpt["hyper_parameters"].items()
        if key not in skip and _keep(value)
    }
    lines = [f'[[checkpoints]]\nname = "{name}"\n\n[checkpoints.hparams]']
    for key, value in sorted(hparams.items()):
        if isinstance(value, str):
            lines.append(f'{key} = "{value}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, (list, tuple)):
            # TOML has no tuple syntax; nested tuples must be emitted as
            # nested arrays or tomllib rejects the file.
            def _as_array(item):
                if isinstance(item, (list, tuple)):
                    return [_as_array(inner) for inner in item]
                return item

            lines.append(f"{key} = {_as_array(list(value))}")
        else:
            lines.append(f"{key} = {value}")
    lines.append("\n[checkpoints.state_dict_shapes]")
    for key, value in sorted(ckpt["state_dict"].items()):
        lines.append(f'"{key}" = "{_format_shape(value.shape)}"')
    shadow = (ckpt.get("ema_generator_state") or {}).get("shadow_params")
    if shadow:
        lines.append("\n[checkpoints.ema_shadow_shapes]")
        for key, value in sorted(shadow.items()):
            lines.append(f'"{key}" = "{_format_shape(value.shape)}"')
    print("\n".join(lines))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-snapshot",
        metavar="CKPT",
        help="print a contract entry for CKPT (paste into the toml)",
    )
    parser.add_argument("--name", default="unnamed", help="entry name for --update-snapshot")
    args = parser.parse_args()

    if args.update_snapshot:
        return _update_snapshot(args.update_snapshot, args.name)

    if not CONTRACT.exists():
        print(f"ERROR: contract missing: {CONTRACT}", file=sys.stderr)
        return 1

    with CONTRACT.open("rb") as handle:
        contract = tomllib.load(handle)

    entries = contract.get("checkpoints", [])
    if not entries:
        print("ERROR: contract lists no checkpoints", file=sys.stderr)
        return 1

    errors: list[str] = []
    for entry in entries:
        errors.extend(_check_entry(entry))

    if errors:
        print("ERROR: published checkpoint compatibility broken:\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print(
            "\nFix options:\n"
            "  - Add a migration in piper_train/vits/commons.py so existing\n"
            "    checkpoints keep loading (see migrate_prefilm_decoder_cond).\n"
            "  - If the break is intentional, publish a replacement checkpoint,\n"
            "    regenerate this contract with --update-snapshot, and record the\n"
            "    break in CHANGELOG.md under '### Breaking' with a migration note.\n"
            "\nRegenerating the snapshot alone re-creates issue #616.",
            file=sys.stderr,
        )
        return 1

    total = sum(len(entry["state_dict_shapes"]) for entry in entries)
    print(
        f"OK: {len(entries)} published checkpoint(s) still load into the current "
        f"model ({total} tensors checked)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
