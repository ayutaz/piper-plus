"""Per-loss gradient-norm probe (zero-shot v10 roadmap A-1c).

各 loss 成分 (mel / kl / spk(SCL) / dino / sub_stft / full_stft / mrd /
mpd_msd / wavlm) が共有の probe パラメータ上に作る勾配の L2 ノルムを測定する。
SCL とスペクトル系 loss (mel / sub_stft / full_stft / mrd) の勾配ノルム比は
「SCL 勾配希釈」仮説 (v9 SECS 退行の主因候補) の直接測定になる。

このモジュールは Lightning 非依存の純関数のみを提供する
(計装側は ``lightning.py`` の ``--grad-probe-every`` 経路)。
``torch.autograd.grad(..., retain_graph=True)`` を使うため、probe 後の
combined backward はそのまま実行できる (``.grad`` への蓄積もしない)。
"""

from __future__ import annotations

import torch


# metrics key の共通 prefix (例: grad_probe/spk/dec_pre)
METRIC_PREFIX = "grad_probe"

# SCL loss の losses dict 上の名前
SPK_LOSS_KEY = "spk"

# 「スペクトル系」loss 群 — spk との勾配ノルム比 (希釈測定) の分母
SPECTRAL_LOSS_KEYS = ("mel", "sub_stft", "full_stft", "mrd")

# ratio の分母がゼロのときのガード
_RATIO_EPS = 1e-12


def _resolve_weight(module: torch.nn.Module | None) -> torch.Tensor | None:
    """Conv/Linear から leaf の weight Parameter を取り出す。

    weight_norm 適用済み module では ``.weight`` は forward ごとに再計算される
    非 leaf テンソルのため、autograd.grad の対象にできない。旧 API
    (``torch.nn.utils.weight_norm``) の ``weight_v``、新 parametrization API の
    ``parametrizations.weight.original1`` を優先して解決する。
    """
    if module is None:
        return None
    # 旧 weight_norm: leaf は weight_v / weight_g
    weight_v = getattr(module, "weight_v", None)
    if isinstance(weight_v, torch.nn.Parameter):
        return weight_v
    # 新 parametrization API (torch.nn.utils.parametrizations.weight_norm)
    parametrizations = getattr(module, "parametrizations", None)
    if parametrizations is not None and "weight" in parametrizations:
        return parametrizations["weight"].original1
    weight = getattr(module, "weight", None)
    if isinstance(weight, torch.nn.Parameter):
        return weight
    return None


def collect_probe_params(model_g: torch.nn.Module) -> dict[str, torch.Tensor]:
    """SynthesizerTrn から probe 対象パラメータ (3-4 点) を集める。

    - ``spk_proj_out``: spk_proj 最終 Linear の weight (話者条件付け入口)
    - ``dec_pre``: dec.conv_pre の weight (decoder 入口、weight_norm leaf)
    - ``enc_p_proj``: enc_p.proj の weight (TextEncoder の出力側 stats 射影)
    - ``flow0_pre``: flow.flows[0].pre の weight (flow 先頭 coupling)

    存在しない (single-speaker 等) / freeze 済み (requires_grad=False、
    ``--train-decoder-only`` 等) のパラメータは黙って除外する
    (requires_grad=False の入力は ``torch.autograd.grad`` が拒否するため)。
    """
    candidates: dict[str, torch.Tensor | None] = {}

    # spk_proj: nn.Sequential(Linear, LayerNorm, GELU, Linear) — 最終 Linear
    spk_proj = getattr(model_g, "spk_proj", None)
    if spk_proj is not None:
        last_linear = None
        for m in spk_proj.modules():
            if isinstance(m, torch.nn.Linear):
                last_linear = m
        candidates["spk_proj_out"] = _resolve_weight(last_linear)

    dec = getattr(model_g, "dec", None)
    candidates["dec_pre"] = _resolve_weight(getattr(dec, "conv_pre", None))

    enc_p = getattr(model_g, "enc_p", None)
    candidates["enc_p_proj"] = _resolve_weight(getattr(enc_p, "proj", None))

    flow = getattr(model_g, "flow", None)
    flows = getattr(flow, "flows", None)
    if flows is not None and len(flows) > 0:
        candidates["flow0_pre"] = _resolve_weight(getattr(flows[0], "pre", None))

    # v10b S-2: F0 予測器の出力射影。``--use-f0-path`` 有効時のみ存在する。
    #
    # 他の 4 点と違い、これは **F0 loss しか届かない** 点である
    # (default の ``f0_detach_input=True`` が予測器の入力を切っているため、
    # mel / GAN の勾配はここに来ない)。従って「mel の 5-15%」型の比率較正は
    # 使えず、c_f0 の較正は「F0 loss の勾配がこの点で有意な大きさを持つか /
    # 他 4 点を汚していないか」で見る。後者がゼロでないなら、意図せず
    # ``--f0-spk-grad`` か ``--f0-attach-predictor-input`` が効いている。
    f0_predictor = getattr(model_g, "f0_predictor", None)
    candidates["f0_pred_out"] = _resolve_weight(getattr(f0_predictor, "proj_f0", None))

    return {
        name: param
        for name, param in candidates.items()
        if param is not None and param.requires_grad
    }


def compute_grad_probe(
    losses: dict[str, torch.Tensor],
    probe_params: dict[str, torch.Tensor],
) -> dict[str, float]:
    """各 loss 成分の勾配 L2 ノルムを probe パラメータ上で測定する。

    Parameters
    ----------
    losses:
        loss 名 → スカラー loss テンソル。``requires_grad=False`` のダミー
        (no-grad ONNX SCL fallback / NaN マスクで定数化した loss 等) は
        勾配恒等ゼロとして記録する。probe 対象パラメータに依存しない loss は
        ``allow_unused=True`` により 0.0 になる。
    probe_params:
        パラメータ名 → leaf Parameter (``collect_probe_params`` の出力)。

    Returns
    -------
    dict[str, float]
        ``grad_probe/{loss}/{param}`` (per-param L2 ノルム、float32 で記録)、
        ``grad_probe/{loss}/total`` (loss ごとの合計)、および ``spk`` が
        存在する場合は ``grad_probe/ratio_spk_to_spectral``
        (spk / スペクトル系合計 — 希釈仮説の 1 スカラー指標)。

    Notes
    -----
    全 autograd.grad 呼び出しは ``retain_graph=True`` / ``.grad`` 非蓄積のため、
    呼び出し後に本来の combined backward をそのまま実行できる。
    """
    results: dict[str, float] = {}
    if not probe_params:
        return results

    param_names = list(probe_params.keys())
    param_tensors = [probe_params[name] for name in param_names]
    loss_totals: dict[str, float] = {}

    for loss_name, loss in losses.items():
        if not isinstance(loss, torch.Tensor):
            continue
        if loss.requires_grad:
            grads = torch.autograd.grad(
                loss,
                param_tensors,
                retain_graph=True,
                allow_unused=True,
            )
            norms = [
                0.0
                if g is None
                # bf16-mixed autocast 下でも記録は float32 に cast する
                else float(torch.linalg.vector_norm(g.detach().to(torch.float32)))
                for g in grads
            ]
        else:
            # requires_grad しないダミー loss — 勾配は恒等ゼロ
            norms = [0.0] * len(param_names)

        total = 0.0
        for param_name, norm in zip(param_names, norms, strict=True):
            results[f"{METRIC_PREFIX}/{loss_name}/{param_name}"] = norm
            total += norm
        results[f"{METRIC_PREFIX}/{loss_name}/total"] = total
        loss_totals[loss_name] = total

    # spk / スペクトル系合計 の勾配ノルム比 (SCL 希釈仮説の直接測定)
    if SPK_LOSS_KEY in loss_totals:
        spectral_total = sum(loss_totals.get(k, 0.0) for k in SPECTRAL_LOSS_KEYS)
        results[f"{METRIC_PREFIX}/ratio_spk_to_spectral"] = loss_totals[
            SPK_LOSS_KEY
        ] / max(spectral_total, _RATIO_EPS)

    return results
