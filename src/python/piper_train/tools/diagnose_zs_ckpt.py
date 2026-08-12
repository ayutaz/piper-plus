#!/usr/bin/env python3
"""Zero-shot checkpoint 診断 (v10 roadmap A-1b).

v9 で観測された zero-shot 話者類似度の退行/天井の構造要因候補
(lang 支配 / FiLM 未起動 / 話者感度の欠如) を、学習済み ckpt の
state_dict だけから定量化する。VitsModel は構築せず、
``torch.load(map_location="cpu")`` した ckpt の ``state_dict``
(``model_g.`` prefix) を直接読むため、dataset / config なしで実行できる。
EMA state (``ema_generator_state``) は読まない。

レポート内容:

1. **lang vs speaker 支配度** — 固定 seed の L2 正規化ランダム 192-d
   embedding K 本 (+ ``--emb-npy`` の実 embedding) を spk_proj
   (Linear→LayerNorm→GELU→Linear を state_dict から手動再構成) に通した
   出力ノルム vs ``emb_lang`` 各行のノルム。research doc では init 時に
   lang が ~2.7 倍 — 学習後の実測がこのツールの目的 (roadmap C-3 の
   投入ゲート)。
2. **FiLM の起き具合** — dec 内 FiLM 層 (input-stage ``dec.cond`` +
   各 upsample 段 ``dec.cond_layers.N``) の weight / bias ノルム。
   ``cond_layers`` は zero-init のため、ノルム = zero-init からの乖離。
   ``dec.cond`` は zero-init ではない点に注意 (絶対値の参考)。
3. **FiLM の話者感度** — embedding ごとの FiLM 変調の identity からの
   差分 ``delta = [sigmoid(scale_raw)+0.5-1, shift]`` を計算し、異なる
   embedding 間の相対差 (L2 / cosine) を層別に測る。
   「話者を変えても変調がほぼ同じ」(rel_l2 ≈ 0) なら条件付けが死んでいる。
4. **spk_proj 各層の weight / bias ノルム**。

ランダム embedding は CAM++ 実分布外なので、可能なら ``--emb-npy`` で
実 embedding (dataset の ``speaker_embeddings/*.npy`` 等) を渡すこと。

Usage:
    python -m piper_train.tools.diagnose_zs_ckpt ckpt.ckpt \
        [--json-out report.json] [--emb-npy A.npy B.npy]
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F


_LOGGER = logging.getLogger(__name__)

_MODEL_G_PREFIX = "model_g."

# models.py の spk_proj: Sequential(Linear(192,g), LayerNorm(g), GELU(),
# Linear(g,g))。GELU (index 2) はパラメータを持たない。
_SPK_PROJ_KEYS = (
    "spk_proj.0.weight",
    "spk_proj.0.bias",
    "spk_proj.1.weight",
    "spk_proj.1.bias",
    "spk_proj.3.weight",
    "spk_proj.3.bias",
)

_SPK_PROJ_LAYER_TYPES = {
    "spk_proj.0": "Linear",
    "spk_proj.1": "LayerNorm",
    "spk_proj.3": "Linear",
}

_EPS = 1e-8


def _load_checkpoint(path: str | Path) -> dict:
    """ckpt を CPU に読み込む。

    Lightning ckpt は hyper_parameters に Namespace 等の非テンソルを含み
    torch 2.6+ の weights_only=True では unpickle できないことがあるため、
    まず weights_only=True を試し、失敗したら False で再試行する
    (repo 内 ckpt は信頼済み前提 — __main__.py の resume 経路と同じ)。
    """
    try:
        return torch.load(path, map_location="cpu", weights_only=True)
    except Exception:
        _LOGGER.debug("weights_only=True failed; falling back to weights_only=False")
        return torch.load(path, map_location="cpu", weights_only=False)


def _extract_model_g_state(ckpt: dict) -> dict[str, torch.Tensor]:
    """ckpt から ``model_g.`` prefix のテンソルだけを取り出し prefix を剥がす。

    - ``state_dict`` キーがあればその配下、なければ ckpt 自体を state dict
      とみなす (素の state_dict ファイルにも対応)。
    - torch.compile 由来の ``._orig_mod.`` は除去する。
    - ``spk_proj_teacher.*`` (DINO teacher) や EMA state は prefix が
      付かないので自動的に無視される。
    """
    sd = ckpt.get("state_dict", ckpt) if isinstance(ckpt, dict) else ckpt
    out: dict[str, torch.Tensor] = {}
    for key, value in sd.items():
        if not isinstance(value, torch.Tensor):
            continue
        key = key.replace("._orig_mod.", ".")
        if key.startswith(_MODEL_G_PREFIX):
            out[key[len(_MODEL_G_PREFIX) :]] = value.detach().float()
    return out


def _spk_proj_forward(sd: dict[str, torch.Tensor], emb: torch.Tensor) -> torch.Tensor:
    """spk_proj (Linear→LayerNorm→GELU→Linear) を state_dict から手動再構成。

    Parameters
    ----------
    sd : dict
        ``model_g.`` prefix を剥がした state dict。
    emb : torch.Tensor
        [K, emb_dim] の speaker embedding。

    Returns
    -------
    torch.Tensor
        [K, gin_channels] の投影出力。
    """
    h = F.linear(emb, sd["spk_proj.0.weight"], sd["spk_proj.0.bias"])
    h = F.layer_norm(h, (h.shape[-1],), sd["spk_proj.1.weight"], sd["spk_proj.1.bias"])
    h = F.gelu(h)
    return F.linear(h, sd["spk_proj.3.weight"], sd["spk_proj.3.bias"])


def _random_unit_embeddings(num: int, dim: int, seed: int) -> torch.Tensor:
    """固定 seed の L2 正規化ランダム embedding [num, dim] を生成する。"""
    gen = torch.Generator().manual_seed(seed)
    emb = torch.randn(num, dim, generator=gen)
    return F.normalize(emb, dim=-1)


def _load_real_embeddings(paths: Sequence[str | Path], dim: int) -> torch.Tensor:
    """--emb-npy で渡された実 embedding を [N, dim] に整形して L2 正規化する。

    各ファイルは [dim] または [N, dim]。extract_speaker_embedding.py の
    出力は既に L2 正規化済みだが、再正規化は no-op なので常に正規化する。
    """
    chunks = []
    for p in paths:
        arr = np.asarray(np.load(str(p)), dtype=np.float32)
        t = torch.from_numpy(arr)
        if t.ndim == 1:
            t = t.unsqueeze(0)
        if t.ndim != 2 or t.shape[1] != dim:
            raise ValueError(
                f"{p}: expected shape [{dim}] or [N, {dim}], got {tuple(arr.shape)}"
            )
        chunks.append(F.normalize(t, dim=-1))
    return torch.cat(chunks, dim=0)


def _find_film_layers(sd: dict[str, torch.Tensor]) -> list[str]:
    """dec 内の FiLM 層名を列挙する (mb_istft.py の命名に準拠)。"""
    names = []
    if "dec.cond.weight" in sd:
        names.append("dec.cond")
    i = 0
    while f"dec.cond_layers.{i}.weight" in sd:
        names.append(f"dec.cond_layers.{i}")
        i += 1
    return names


def _film_wakeup_stats(name: str, sd: dict[str, torch.Tensor]) -> dict:
    """FiLM 層の weight/bias ノルム (zero-init からの乖離) を測る。

    weight は [2*ch, gin, 1] で、前半 ch 行が scale_raw、後半 ch 行が
    shift (mb_istft.py の ``_apply_film`` の split 順)。
    """
    weight = sd[f"{name}.weight"]
    bias = sd[f"{name}.bias"]
    ch = weight.shape[0] // 2
    return {
        # dec.cond (input-stage) は default init、cond_layers は zero-init。
        # zero_init=True の層はノルムがそのまま「起き具合」を表す。
        "zero_init": name.startswith("dec.cond_layers"),
        "out_channels": int(ch),
        "weight_norm": float(weight.norm()),
        "bias_norm": float(bias.norm()),
        "scale_weight_norm": float(weight[:ch].norm()),
        "shift_weight_norm": float(weight[ch:].norm()),
        "scale_bias_norm": float(bias[:ch].norm()),
        "shift_bias_norm": float(bias[ch:].norm()),
    }


def _film_modulation_delta(
    weight: torch.Tensor, bias: torch.Tensor, g: torch.Tensor
) -> torch.Tensor:
    """条件 g に対する FiLM 変調の identity からの差分ベクトルを計算する。

    1x1 Conv1d は行列積と等価。実際に乗算される gain は
    ``sigmoid(scale_raw) + 0.5`` (identity = 1.0)、shift の identity は 0
    なので、``delta = [gain - 1, shift]``。zero-init 層では delta = 0。
    """
    out = weight[:, :, 0] @ g + bias
    ch = out.shape[0] // 2
    gain = torch.sigmoid(out[:ch]) + 0.5
    return torch.cat([gain - 1.0, out[ch:]])


def _pairwise_delta_stats(deltas: Sequence[torch.Tensor]) -> dict:
    """変調差分ベクトル同士の全ペア相対差 (L2 / cosine) を集計する。

    - rel_l2 = ||a - b|| / (0.5 * (||a|| + ||b||))。両者がほぼゼロ
      (未学習 FiLM) のペアは「差なし」として 0.0 と数える。
    - cosine は両者のノルムが非ゼロのペアのみ (ゼロベクトルでは未定義)。
    """
    rels: list[float] = []
    coss: list[float] = []
    for i, j in itertools.combinations(range(len(deltas)), 2):
        a, b = deltas[i], deltas[j]
        na = float(a.norm())
        nb = float(b.norm())
        denom = 0.5 * (na + nb)
        if denom < _EPS:
            rels.append(0.0)
            continue
        rels.append(float((a - b).norm()) / denom)
        if na > _EPS and nb > _EPS:
            coss.append(float(torch.dot(a, b)) / (na * nb))
    if not rels:
        return {
            "num_pairs": 0,
            "rel_l2_mean": None,
            "rel_l2_max": None,
            "cosine_mean": None,
            "cosine_min": None,
        }
    return {
        "num_pairs": len(rels),
        "rel_l2_mean": sum(rels) / len(rels),
        "rel_l2_max": max(rels),
        "cosine_mean": sum(coss) / len(coss) if coss else None,
        "cosine_min": min(coss) if coss else None,
    }


def _film_sensitivity(
    sd: dict[str, torch.Tensor],
    film_names: Sequence[str],
    spk_out: torch.Tensor,
) -> dict[str, dict]:
    """各 FiLM 層について embedding 間の変調感度を集計する。"""
    result = {}
    for name in film_names:
        weight = sd[f"{name}.weight"]
        bias = sd[f"{name}.bias"]
        deltas = [_film_modulation_delta(weight, bias, g) for g in spk_out]
        stats = _pairwise_delta_stats(deltas)
        stats["delta_norm_mean"] = float(torch.stack([d.norm() for d in deltas]).mean())
        result[name] = stats
    return result


def diagnose(
    ckpt_path: str | Path,
    emb_npy: Sequence[str | Path] | None = None,
    num_random: int = 8,
    seed: int = 1234,
) -> dict:
    """ckpt を診断し JSON 化可能な dict を返す。"""
    ckpt = _load_checkpoint(ckpt_path)
    sd = _extract_model_g_state(ckpt)
    missing = [k for k in _SPK_PROJ_KEYS if k not in sd]
    if missing:
        raise ValueError(
            "spk_proj keys not found in checkpoint (zero-shot ckpt ではない?)."
            f" missing: {', '.join(missing)}"
        )

    emb_dim = int(sd["spk_proj.0.weight"].shape[1])
    gin_channels = int(sd["spk_proj.0.weight"].shape[0])

    rand_embs = _random_unit_embeddings(num_random, emb_dim, seed)
    real_embs = _load_real_embeddings(emb_npy, emb_dim) if emb_npy else None
    embs = (
        torch.cat([rand_embs, real_embs], dim=0) if real_embs is not None else rand_embs
    )
    num_real = int(real_embs.shape[0]) if real_embs is not None else 0

    # --- 1. lang vs speaker 支配度 ---
    spk_out = _spk_proj_forward(sd, embs)  # [K, gin]
    spk_norms = spk_out.norm(dim=-1)
    spk_norm_mean = float(spk_norms.mean())
    lang_weight = sd.get("emb_lang.weight")
    if lang_weight is not None:
        lang_norms = [float(v) for v in lang_weight.norm(dim=-1)]
        lang_norm_mean = sum(lang_norms) / len(lang_norms)
        n_languages = int(lang_weight.shape[0])
    else:
        lang_norms = None
        lang_norm_mean = None
        n_languages = None
    lang_vs_speaker = {
        "spk_out_norm_mean": spk_norm_mean,
        "spk_out_norm_std": float(spk_norms.std(correction=0)),
        "spk_out_norms": [float(v) for v in spk_norms],
        "lang_norms": lang_norms,
        "lang_norm_mean": lang_norm_mean,
        "lang_over_spk": (
            lang_norm_mean / spk_norm_mean
            if lang_norm_mean is not None and spk_norm_mean > _EPS
            else None
        ),
        "spk_over_lang": (
            spk_norm_mean / lang_norm_mean
            if lang_norm_mean is not None and lang_norm_mean > _EPS
            else None
        ),
    }

    # --- 2. FiLM の起き具合 / 3. FiLM の話者感度 ---
    film_names = _find_film_layers(sd)
    film_wakeup = {name: _film_wakeup_stats(name, sd) for name in film_names}
    film_sensitivity = _film_sensitivity(sd, film_names, spk_out)
    # 実 embedding が 2 本以上あれば、実 emb だけの感度も別集計する
    # (ランダム emb は CAM++ 実分布外のため実測はこちらを優先して読む)。
    film_sensitivity_real = None
    if num_real >= 2:
        real_out = spk_out[num_random:]
        film_sensitivity_real = _film_sensitivity(sd, film_names, real_out)

    # --- 4. spk_proj 各層の weight ノルム ---
    spk_proj_layers = {
        name: {
            "type": layer_type,
            "weight_norm": float(sd[f"{name}.weight"].norm()),
            "bias_norm": float(sd[f"{name}.bias"].norm()),
        }
        for name, layer_type in _SPK_PROJ_LAYER_TYPES.items()
    }

    return {
        "checkpoint": str(ckpt_path),
        "emb_dim": emb_dim,
        "gin_channels": gin_channels,
        "n_languages": n_languages,
        "seed": seed,
        "num_random_embeddings": int(num_random),
        "num_real_embeddings": num_real,
        "lang_vs_speaker": lang_vs_speaker,
        "film_wakeup": film_wakeup,
        "film_sensitivity": film_sensitivity,
        "film_sensitivity_real": film_sensitivity_real,
        "spk_proj_layers": spk_proj_layers,
    }


def _fmt(value, width: int = 9) -> str:
    """float / None を固定幅で整形する。"""
    if value is None:
        return "-".rjust(width)
    return f"{value:.4f}".rjust(width)


def _format_sensitivity_table(sens: dict[str, dict]) -> list[str]:
    lines = [
        f"  {'layer':<22} {'delta_norm':>10} {'rel_l2 mean':>11}"
        f" {'rel_l2 max':>10} {'cos mean':>9} {'cos min':>9} {'pairs':>5}"
    ]
    for name, s in sens.items():
        lines.append(
            f"  {name:<22} {_fmt(s['delta_norm_mean'], 10)}"
            f" {_fmt(s['rel_l2_mean'], 11)} {_fmt(s['rel_l2_max'], 10)}"
            f" {_fmt(s['cosine_mean'])} {_fmt(s['cosine_min'])}"
            f" {s['num_pairs']:>5}"
        )
    return lines


def _format_report(result: dict) -> str:
    """人間可読レポートを組み立てる。"""
    lines = []
    lines.append(f"=== Zero-shot ckpt diagnosis: {result['checkpoint']} ===")
    lines.append(
        f"emb_dim={result['emb_dim']}  gin_channels={result['gin_channels']}"
        f"  n_languages={result['n_languages']}"
    )
    lines.append(
        f"embeddings: {result['num_random_embeddings']} random"
        f" (seed={result['seed']}) + {result['num_real_embeddings']} real"
    )

    lv = result["lang_vs_speaker"]
    lines.append("")
    lines.append("[1] lang vs speaker dominance")
    lines.append(
        f"  spk_proj output norm : mean {_fmt(lv['spk_out_norm_mean'])}"
        f"  std {_fmt(lv['spk_out_norm_std'])}"
    )
    if lv["lang_norms"] is not None:
        lines.append(f"  emb_lang row norm    : mean {_fmt(lv['lang_norm_mean'])}")
        for i, n in enumerate(lv["lang_norms"]):
            lines.append(f"    lang {i}: {_fmt(n)}")
        lines.append(
            f"  lang / spk ratio     : {_fmt(lv['lang_over_spk'])}"
            "  (>1 = lang dominant; init 時 research 実測 ~2.7)"
        )
    else:
        lines.append("  emb_lang: not found (single-language model)")

    lines.append("")
    lines.append("[2] FiLM wake-up (weight/bias norms; cond_layers は zero-init)")
    if result["film_wakeup"]:
        lines.append(
            f"  {'layer':<22} {'ch':>4} {'|W|':>9} {'|b|':>9} {'|W_scale|':>9}"
            f" {'|W_shift|':>9} {'|b_scale|':>9} {'|b_shift|':>9}"
        )
        for name, s in result["film_wakeup"].items():
            mark = "" if s["zero_init"] else " *"
            lines.append(
                f"  {name + mark:<22} {s['out_channels']:>4}"
                f" {_fmt(s['weight_norm'])} {_fmt(s['bias_norm'])}"
                f" {_fmt(s['scale_weight_norm'])} {_fmt(s['shift_weight_norm'])}"
                f" {_fmt(s['scale_bias_norm'])} {_fmt(s['shift_bias_norm'])}"
            )
        lines.append("  (* = zero-init ではない層。ノルムは絶対値の参考)")
    else:
        lines.append("  FiLM layers not found (gin_channels == 0?)")

    lines.append("")
    lines.append("[3] FiLM speaker sensitivity (delta = [gain-1, shift])")
    if result["film_sensitivity"]:
        lines.extend(_format_sensitivity_table(result["film_sensitivity"]))
        # NOTE: cp932 console (Windows) で encode できない記号 (≈ 等) は使わない
        lines.append(
            "  (rel_l2 ~ 0 = 話者を変えても変調が同じ = speaker 条件付けが死亡)"
        )
        if result["film_sensitivity_real"] is not None:
            lines.append("  -- real embeddings のみ --")
            lines.extend(_format_sensitivity_table(result["film_sensitivity_real"]))
    else:
        lines.append("  FiLM layers not found")

    lines.append("")
    lines.append("[4] spk_proj layer norms")
    for name, s in result["spk_proj_layers"].items():
        lines.append(
            f"  {name:<12} {s['type']:<10} |W| {_fmt(s['weight_norm'])}"
            f"  |b| {_fmt(s['bias_norm'])}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(
        description="zero-shot ckpt の lang 支配度 / FiLM 起動 / 話者感度を診断する"
    )
    parser.add_argument("checkpoint", help="診断対象の .ckpt")
    parser.add_argument("--json-out", help="JSON レポートの出力先パス")
    parser.add_argument(
        "--emb-npy",
        nargs="+",
        metavar="NPY",
        help="実 speaker embedding の .npy (各 [192] または [N, 192]、複数可)",
    )
    parser.add_argument(
        "--num-random-embeddings",
        type=int,
        default=8,
        help="固定 seed で生成するランダム embedding の本数 (default: 8)",
    )
    parser.add_argument(
        "--seed", type=int, default=1234, help="ランダム embedding の seed"
    )
    args = parser.parse_args(argv)

    try:
        result = diagnose(
            args.checkpoint,
            emb_npy=args.emb_npy,
            num_random=args.num_random_embeddings,
            seed=args.seed,
        )
    except (ValueError, FileNotFoundError) as e:
        parser.error(str(e))

    print(_format_report(result))
    if args.json_out:
        out_path = Path(args.json_out)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        _LOGGER.info("JSON report written to %s", out_path)


if __name__ == "__main__":
    main()
