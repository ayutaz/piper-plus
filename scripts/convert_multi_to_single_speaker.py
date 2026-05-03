#!/usr/bin/env python3
"""
マルチスピーカー学習チェックポイントから HuggingFace 公開用の
"ファインチューニング ベース" チェックポイントを作成するスクリプト。

学習直後の `last.ckpt` (~938 MB) には optimizer states や discriminator EMA
が含まれていて HF にアップロードするには大きすぎるので、推論 / FT に必要な
要素だけ残した軽量版を生成する。

処理内容:
  1. top-level から optimizer_states / lr_schedulers / ema_discriminator_state
     / loops / callbacks を削除 (これだけで ~600 MB 削減)
  2. state_dict から model_g.emb_g.weight (話者埋め込み) を削除
  3. hyper_parameters.num_speakers を 0 / speaker_id を None に変更

Note:
  cond_layer 系 (model_g.dec.cond.*, dp.cond.*, enc_q/flow.*.cond_layer.*,
  enc_p.cond_layer.*) は **保持** する。学習側 `--resume-from-multispeaker-checkpoint`
  が起動時に動的に emb_g.mean() を bias に吸収する設計のため。
  (PR #170 時点では cond_layer も削除していたが現行アーキでは不要)

  ema_generator_state は decoder の shadow_params のみを保持しており
  emb_g 系キーは元々含まれないため処理不要。

Security:
  torch.load(weights_only=False) は任意のオブジェクトをアンピクルするため
  **信頼できる ckpt** にのみ使用すること。Lightning ckpt の hyper_parameters に
  pathlib.Path 等が含まれるため weights_only=True では読み込めない。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from pathlib import Path

import torch


# Windows で Linux 由来の ckpt をロードするための互換パッチ。
# (Lightning は hyper_parameters に PosixPath を直接ピクルする)
if sys.platform == "win32":
    pathlib.PosixPath = pathlib.WindowsPath  # type: ignore[misc,assignment]
torch.serialization.add_safe_globals([pathlib.PosixPath, pathlib.WindowsPath])


TOP_LEVEL_KEYS_TO_DROP = (
    "optimizer_states",
    "lr_schedulers",
    "ema_discriminator_state",
    "loops",
    "callbacks",
)

STATE_DICT_KEYS_TO_DROP = ("model_g.emb_g.weight",)


def _file_size_mb(path: str | Path) -> float:
    return Path(path).stat().st_size / 1024**2


def convert_checkpoint(input_path: str, output_path: str) -> bool:
    if not Path(input_path).exists():
        print(f"ERROR: input checkpoint not found: {input_path}", file=sys.stderr)
        return False

    print(f"Loading checkpoint: {input_path}")
    print(f"  size: {_file_size_mb(input_path):.1f} MB")
    # weights_only=False is required because Lightning ckpts pickle pathlib
    # objects in hyper_parameters. Only run on TRUSTED checkpoint files.
    ckpt = torch.load(input_path, map_location="cpu", weights_only=False)
    print(f"  top-level keys: {list(ckpt.keys())}")

    hp = ckpt.get("hyper_parameters", {})
    print(
        f"  hparams: num_speakers={hp.get('num_speakers')}, "
        f"num_languages={hp.get('num_languages')}, "
        f"epoch={ckpt.get('epoch')}"
    )

    dropped_top = []
    for key in TOP_LEVEL_KEYS_TO_DROP:
        if key in ckpt:
            del ckpt[key]
            dropped_top.append(key)
    print(f"  dropped top-level: {dropped_top}")

    state_dict = ckpt.get("state_dict", {})
    dropped_sd = []
    for key in STATE_DICT_KEYS_TO_DROP:
        if key in state_dict:
            del state_dict[key]
            dropped_sd.append(key)
    print(f"  dropped state_dict: {dropped_sd}")

    # NOTE: 現行 ema (vits/ema.py) は decoder のみ shadow_params で保持しており
    # emb_g は元々 EMA の対象外。よって ema_generator_state 側の clean-up は不要。

    if "hyper_parameters" in ckpt:
        ckpt["hyper_parameters"]["num_speakers"] = 0
        if "speaker_id" in ckpt["hyper_parameters"]:
            ckpt["hyper_parameters"]["speaker_id"] = None
        print("  hparams.num_speakers -> 0")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(ckpt, output_path)
    print(f"\nSaved: {output_path}")
    print(f"  size: {_file_size_mb(output_path):.1f} MB")
    return True


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Multi-speaker checkpoint -> FT-base checkpoint converter "
        "(strips optimizer / discriminator EMA / emb_g for HF publishing)"
    )
    p.add_argument(
        "--input-checkpoint",
        type=str,
        default=os.environ.get("INPUT_CHECKPOINT"),
        required="INPUT_CHECKPOINT" not in os.environ,
        help="path to source multi-speaker checkpoint (env: INPUT_CHECKPOINT)",
    )
    p.add_argument(
        "--output-checkpoint",
        type=str,
        default=os.environ.get("OUTPUT_CHECKPOINT"),
        required="OUTPUT_CHECKPOINT" not in os.environ,
        help="path to write the stripped FT-base checkpoint (env: OUTPUT_CHECKPOINT)",
    )
    return p


def main() -> int:
    args = _build_parser().parse_args()
    ok = convert_checkpoint(args.input_checkpoint, args.output_checkpoint)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
