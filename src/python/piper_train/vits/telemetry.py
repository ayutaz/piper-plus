"""v11 D-2: 変調統計テレメトリ (学習時常設、--telemetry-every)。

conditioning 設計 doc §3 D-2 / §10.6-4 の制度化。Phase 0 の教訓
「変調の**総量** (ノルム・分散量) だけでは SNAC 型の死荷重を検知できない」
(doc §10.3-1: sn_m は z 上の probe には見えるが decoder は描画しない) を受け、
各注入点 (dec FiLM / dec AdaIN / enc_p cond / enc_p AdaLN / SNAC / DP head) の
変調ベクトルについて**話者依存分散比**を学習中に追跡する。

話者依存分散比 (doc §10.6-4 の定義)::

    ratio = (batch 内の話者間分散) / (総分散)

変調行列 V [B, C] (発話ごとの変調ベクトル) と speaker_ids [B] に対し、
channel ごとに biased variance で

    total[c]   = mean_b (V[b,c] - μ[c])²
    between[c] = Σ_s (n_s / B) (μ_s[c] - μ[c])²

を計算し、channel 平均の比 mean_c(between) / mean_c(total) を返す。
1.0 = 変調が話者にのみ依存 (batch 内の同一話者サンプルで一致)、
0.0 = 話者共通の固定変換 (v10b 実測: FiLM の話者依存分は 10-16%、
sn_v は ~4% で死亡 — doc §10.2 D-2)。

全て ``torch.no_grad`` + 発話あたり 1 回の 1x1 conv/MLP なので計算コストは
無視できる。DDP 安全: collective を含まず、log は呼び出し側 (lightning) が
rank 0 に限定する。
"""

from __future__ import annotations

import torch
from torch.nn import functional as F


_EPS = 1e-12


def speaker_variance_ratio(
    values: torch.Tensor, speaker_ids: torch.Tensor
) -> float | None:
    """batch 内の話者間分散 / 総分散 (D-2 定義)。

    Parameters
    ----------
    values : torch.Tensor
        [B, C] — 発話ごとの変調ベクトル。
    speaker_ids : torch.Tensor
        [B] — 整数 speaker id。

    Returns
    -------
    float or None
        [0, 1] の比。B < 2 では定義できないため None。総分散 ≈ 0
        (定数変調) は 0.0 を返す。
    """
    values = values.detach().float().reshape(values.size(0), -1)
    b = values.size(0)
    if b < 2:
        return None
    speaker_ids = speaker_ids.reshape(-1)
    mu = values.mean(dim=0)
    total = ((values - mu) ** 2).mean(dim=0)  # [C], biased
    total_mean = float(total.mean())
    if total_mean < _EPS:
        return 0.0
    between = torch.zeros_like(total)
    for s in torch.unique(speaker_ids):
        mask = speaker_ids == s
        n_s = int(mask.sum())
        mu_s = values[mask].mean(dim=0)
        between = between + (n_s / b) * (mu_s - mu) ** 2
    return float(between.mean() / total.mean())


@torch.no_grad()
def collect_modulation_telemetry(
    model_g,
    speaker_embeddings: torch.Tensor,
    lid: torch.Tensor | None = None,
    speaker_ids: torch.Tensor | None = None,
) -> dict[str, float]:
    """全注入点の変調統計を 1 dict にまとめる (キーはそのまま TB へ log)。

    注入点ごとに:

    - ``telemetry/mod_std/<point>``: 変調ベクトルの batch 間 std (channel
      平均、biased) — 変調の「総量」(従来 D-2 の spread に相当)
    - ``telemetry/spk_var_ratio/<point>``: 話者依存分散比 (上の定義) —
      総量が大きくても話者共通の固定変換なら 0 に落ちる (死荷重の検知)

    加えて global 条件の相互作用 (D-2 (i)):

    - ``telemetry/g_spk_norm`` / ``telemetry/g_lang_spk_norm_ratio`` /
      ``telemetry/g_spk_lang_cos`` (v10b 実測 −0.56 の定点)
    - ``telemetry/dp_delta_norm``: DP 残差ヘッドのノルム (D-2 (v))

    各注入点は存在する場合のみ集計する (opt-in flag off の構成では
    キーが出ない)。speaker_ids が None の場合は spk_var_ratio を省略する。
    """
    metrics: dict[str, float] = {}
    g, g_spk, g_lang = model_g._get_global_conditioning(
        None, lid, speaker_embeddings=speaker_embeddings, return_components=True
    )
    if g_spk is None:
        return metrics

    flat_spk = g_spk.squeeze(-1).float()
    spk_norm = flat_spk.norm(dim=-1)
    metrics["telemetry/g_spk_norm"] = float(spk_norm.mean())
    if g_lang is not None:
        flat_lang = g_lang.squeeze(-1).float()
        metrics["telemetry/g_lang_spk_norm_ratio"] = float(
            (flat_lang.norm(dim=-1) / spk_norm.clamp_min(_EPS)).mean()
        )
        metrics["telemetry/g_spk_lang_cos"] = float(
            F.cosine_similarity(flat_spk, flat_lang, dim=-1).mean()
        )

    # --- 注入点ごとの変調ベクトル [B, C] ---
    points: dict[str, torch.Tensor] = {}
    dec = getattr(model_g, "dec", None)
    if dec is not None and getattr(dec, "gin_channels", 0) != 0 and g is not None:
        points["dec_film_input"] = dec.cond(g).squeeze(-1)
        for i, layer in enumerate(dec.cond_layers):
            points[f"dec_film_s{i + 1}"] = layer(g).squeeze(-1)
        if getattr(dec, "use_adain_decoder", False):
            points["dec_adain"] = torch.cat(
                [m.fc(g).squeeze(-1) for m in dec.adain_layers.values()], dim=-1
            )

    enc_p = getattr(model_g, "enc_p", None)
    if enc_p is not None and g is not None and hasattr(enc_p, "cond_layer"):
        points["encp_cond"] = enc_p.cond_layer(g).squeeze(-1)
    if enc_p is not None and getattr(enc_p, "use_adaln", False):
        # P0-4: AdaLN は g_spk のみ (models.TextEncoder.forward と同一配線)
        trunk = enc_p.encoder.adaln_trunk(g_spk)
        points["encp_adaln"] = torch.cat(
            [head(trunk).squeeze(-1) for head in enc_p.encoder.adaln_heads], dim=-1
        )

    if getattr(model_g, "use_snac_flow", False):
        # snac_stats=False (P5) では sn_linear が存在せずキー自体が出ない
        sn = [
            flow.sn_linear(g_spk).squeeze(-1)
            for flow in model_g.flow.flows
            if hasattr(flow, "sn_linear")
        ]
        if sn:
            points["flow_snac"] = torch.cat(sn, dim=-1)

    if hasattr(model_g, "spk_proj_dp") and g is not None:
        delta = model_g.spk_proj_dp(g.transpose(1, 2)).transpose(1, 2).squeeze(-1)
        points["dp_head"] = delta
        metrics["telemetry/dp_delta_norm"] = float(delta.float().norm(dim=-1).mean())

    for name, vals in points.items():
        vals = vals.float()
        metrics[f"telemetry/mod_std/{name}"] = float(
            vals.std(dim=0, unbiased=False).mean()
        )
        if speaker_ids is not None:
            ratio = speaker_variance_ratio(vals, speaker_ids)
            if ratio is not None:
                metrics[f"telemetry/spk_var_ratio/{name}"] = ratio
    return metrics
