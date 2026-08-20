import math

import torch
from torch import nn
from torch.nn import functional as F

from .commons import subsequent_mask
from .modules import LayerNorm


class Encoder(nn.Module):
    def __init__(
        self,
        hidden_channels: int,
        filter_channels: int,
        n_heads: int,
        n_layers: int,
        kernel_size: int = 1,
        p_dropout: float = 0.0,
        window_size: int = 4,
        drop_rel_v: bool = False,
        # v11 P2 (--use-adaln-encp): 各層の LayerNorm 出力を話者条件で変調する
        # AdaLN-Zero。0 (default) は無効 = 従来経路と bit 互換 / 新規パラメータ
        # なし。> 0 で共有低ランク trunk (adaln_gin_channels → adaln_rank) +
        # per-norm zero-init head (adaln_rank → 2·hidden) を構築し、forward の
        # ``g_adaln`` から γ̂/β̂ を発話あたり 1 回計算して
        # ``x = LN(x)·(1+γ̂) + β̂`` を各 norm 直後に適用する。zero-init head に
        # より on 直後は素の LN と bit 一致 (conditioning 設計 doc §5.1 a-1)。
        adaln_gin_channels: int = 0,
        adaln_rank: int = 128,
        **kwargs,
    ):
        super().__init__()
        self.hidden_channels = hidden_channels
        self.filter_channels = filter_channels
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.window_size = window_size
        # T3: propagate SDPA opt-in flag down to every attention sub-layer.
        # ``drop_rel_v=True`` swaps the manual matmul path for
        # ``F.scaled_dot_product_attention`` (fuses Q@K^T / softmax / p_attn@V
        # into a single fused kernel and skips materializing the [B,H,T,T]
        # attention matrix). The relative-V correction is dropped because SDPA
        # does not expose ``p_attn`` needed for it. Default False preserves the
        # existing manual path with bit-parity.
        self.drop_rel_v = drop_rel_v

        self.drop = nn.Dropout(p_dropout)
        self.attn_layers = nn.ModuleList()
        self.norm_layers_1 = nn.ModuleList()
        self.ffn_layers = nn.ModuleList()
        self.norm_layers_2 = nn.ModuleList()
        for _i in range(self.n_layers):
            self.attn_layers.append(
                MultiHeadAttention(
                    hidden_channels,
                    hidden_channels,
                    n_heads,
                    p_dropout=p_dropout,
                    window_size=window_size,
                    drop_rel_v=drop_rel_v,
                )
            )
            self.norm_layers_1.append(LayerNorm(hidden_channels))
            self.ffn_layers.append(
                FFN(
                    hidden_channels,
                    hidden_channels,
                    filter_channels,
                    kernel_size,
                    p_dropout=p_dropout,
                )
            )
            self.norm_layers_2.append(LayerNorm(hidden_channels))

        # v11 P2: AdaLN trunk + heads (2 norm/層 × n_layers 本)。head は
        # zero-init (γ̂=β̂=0 → 恒等)、trunk は通常 init (head のゼロが恒等を
        # 保証するため対称性破りは trunk 側に残してよい)。
        self.adaln_heads = None
        if adaln_gin_channels > 0:
            self.adaln_trunk = nn.Sequential(
                nn.Conv1d(adaln_gin_channels, adaln_rank, 1),
                nn.GELU(),
            )
            self.adaln_heads = nn.ModuleList()
            for _i in range(2 * self.n_layers):
                head = nn.Conv1d(adaln_rank, hidden_channels * 2, 1)
                nn.init.zeros_(head.weight)
                nn.init.zeros_(head.bias)
                self.adaln_heads.append(head)

    @staticmethod
    def _apply_adaln(x, mod):
        """AdaLN-Zero 変調: ``x·(1+γ̂) + β̂`` (mod = [b, 2h, 1]、γ̂ が先)。"""
        gamma, beta = mod.split(mod.size(1) // 2, dim=1)
        return x * (1.0 + gamma) + beta

    def forward(self, x, x_mask, cond=None, cond_layer_idx=None, g_adaln=None):
        """x を n_layers 段の self-attention + FFN に通す。

        cond / cond_layer_idx (v10 M2, ``--speaker-cond-layer``):
        ``cond_layer_idx`` (1-based) を指定すると ``cond`` ([b, h, 1] を
        時間軸 broadcast) を第 N 層の入口で加算する — self-attention が
        話者情報を見られるようにする VITS2 同構成の注入位置。
        default (両方 None) は従来経路と bit 互換。

        g_adaln (v11 P2, ``--use-adaln-encp``): AdaLN 条件 [b, gin, 1]。
        構築時に ``adaln_gin_channels > 0`` の場合のみ有効で、各 LayerNorm
        直後に ``x·(1+γ̂(g)) + β̂(g)`` を適用する。None (default) または
        AdaLN 未構築なら素の LN のまま (bit 互換)。M2 (cond) とは独立に共存
        する (重複の要否は smoke A/B — conditioning 設計 doc §10.5)。
        """
        adaln_mods = None
        if g_adaln is not None and self.adaln_heads is not None:
            # 発話あたり 1 回 (時間軸 broadcast) — RTF への影響 ≈ 0
            trunk = self.adaln_trunk(g_adaln)
            adaln_mods = [head(trunk) for head in self.adaln_heads]
        attn_mask = x_mask.unsqueeze(2) * x_mask.unsqueeze(-1)
        x = x * x_mask
        for i, (attn_layer, norm_layer_1, ffn_layer, norm_layer_2) in enumerate(
            zip(
                self.attn_layers,
                self.norm_layers_1,
                self.ffn_layers,
                self.norm_layers_2,
                strict=False,
            )
        ):
            if (
                cond is not None
                and cond_layer_idx is not None
                and i == cond_layer_idx - 1
            ):
                # v10 M2: 話者条件を第 cond_layer_idx 層の入口に注入
                x = (x + cond) * x_mask
            y = attn_layer(x, x, attn_mask)
            y = self.drop(y)
            x = norm_layer_1(x + y)
            if adaln_mods is not None:
                x = self._apply_adaln(x, adaln_mods[2 * i])

            y = ffn_layer(x, x_mask)
            y = self.drop(y)
            x = norm_layer_2(x + y)
            if adaln_mods is not None:
                x = self._apply_adaln(x, adaln_mods[2 * i + 1])
        x = x * x_mask
        return x


class Decoder(nn.Module):
    def __init__(
        self,
        hidden_channels: int,
        filter_channels: int,
        n_heads: int,
        n_layers: int,
        kernel_size: int = 1,
        p_dropout: float = 0.0,
        proximal_bias: bool = False,
        proximal_init: bool = True,
        **kwargs,
    ):
        super().__init__()
        self.hidden_channels = hidden_channels
        self.filter_channels = filter_channels
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.proximal_bias = proximal_bias
        self.proximal_init = proximal_init

        self.drop = nn.Dropout(p_dropout)
        self.self_attn_layers = nn.ModuleList()
        self.norm_layers_0 = nn.ModuleList()
        self.encdec_attn_layers = nn.ModuleList()
        self.norm_layers_1 = nn.ModuleList()
        self.ffn_layers = nn.ModuleList()
        self.norm_layers_2 = nn.ModuleList()
        for _i in range(self.n_layers):
            self.self_attn_layers.append(
                MultiHeadAttention(
                    hidden_channels,
                    hidden_channels,
                    n_heads,
                    p_dropout=p_dropout,
                    proximal_bias=proximal_bias,
                    proximal_init=proximal_init,
                )
            )
            self.norm_layers_0.append(LayerNorm(hidden_channels))
            self.encdec_attn_layers.append(
                MultiHeadAttention(
                    hidden_channels, hidden_channels, n_heads, p_dropout=p_dropout
                )
            )
            self.norm_layers_1.append(LayerNorm(hidden_channels))
            self.ffn_layers.append(
                FFN(
                    hidden_channels,
                    hidden_channels,
                    filter_channels,
                    kernel_size,
                    p_dropout=p_dropout,
                    causal=True,
                )
            )
            self.norm_layers_2.append(LayerNorm(hidden_channels))

    def forward(self, x, x_mask, h, h_mask):
        """
        x: decoder input
        h: encoder output
        """
        self_attn_mask = subsequent_mask(x_mask.size(2)).type_as(x)
        encdec_attn_mask = h_mask.unsqueeze(2) * x_mask.unsqueeze(-1)
        x = x * x_mask
        for i in range(self.n_layers):
            y = self.self_attn_layers[i](x, x, self_attn_mask)
            y = self.drop(y)
            x = self.norm_layers_0[i](x + y)

            y = self.encdec_attn_layers[i](x, h, encdec_attn_mask)
            y = self.drop(y)
            x = self.norm_layers_1[i](x + y)

            y = self.ffn_layers[i](x, x_mask)
            y = self.drop(y)
            x = self.norm_layers_2[i](x + y)
        x = x * x_mask
        return x


class MultiHeadAttention(nn.Module):
    def __init__(
        self,
        channels: int,
        out_channels: int,
        n_heads: int,
        p_dropout: float = 0.0,
        window_size: int | None = None,
        heads_share: bool = True,
        block_length: int | None = None,
        proximal_bias: bool = False,
        proximal_init: bool = False,
        drop_rel_v: bool = False,
    ):
        super().__init__()
        assert channels % n_heads == 0

        self.channels = channels
        self.out_channels = out_channels
        self.n_heads = n_heads
        self.p_dropout = p_dropout
        self.window_size = window_size
        self.heads_share = heads_share
        self.block_length = block_length
        self.proximal_bias = proximal_bias
        self.proximal_init = proximal_init
        # T3: opt-in SDPA fast path (see ``attention()`` for the branch). Skipping
        # the relative-V correction (which requires ``p_attn``) is what allows
        # us to drop into ``F.scaled_dot_product_attention`` and save the
        # [B,H,T,T] activation-memory allocation. Default False preserves the
        # existing manual path with bit-parity (regression zero).
        self.drop_rel_v = drop_rel_v
        self.attn = torch.zeros(1)

        self.k_channels = channels // n_heads
        self.conv_q = nn.Conv1d(channels, channels, 1)
        self.conv_k = nn.Conv1d(channels, channels, 1)
        self.conv_v = nn.Conv1d(channels, channels, 1)
        self.conv_o = nn.Conv1d(channels, out_channels, 1)
        self.drop = nn.Dropout(p_dropout)

        if window_size is not None:
            n_heads_rel = 1 if heads_share else n_heads
            rel_stddev = self.k_channels**-0.5
            self.emb_rel_k = nn.Parameter(
                torch.randn(n_heads_rel, window_size * 2 + 1, self.k_channels)
                * rel_stddev
            )
            self.emb_rel_v = nn.Parameter(
                torch.randn(n_heads_rel, window_size * 2 + 1, self.k_channels)
                * rel_stddev
            )

        nn.init.xavier_uniform_(self.conv_q.weight)
        nn.init.xavier_uniform_(self.conv_k.weight)
        nn.init.xavier_uniform_(self.conv_v.weight)
        if proximal_init:
            with torch.no_grad():
                self.conv_k.weight.copy_(self.conv_q.weight)
                self.conv_k.bias.copy_(self.conv_q.bias)

    def forward(self, x, c, attn_mask=None):
        q = self.conv_q(x)
        k = self.conv_k(c)
        v = self.conv_v(c)

        x, self.attn = self.attention(q, k, v, mask=attn_mask)

        x = self.conv_o(x)
        return x

    def attention(self, query, key, value, mask=None):
        # reshape [b, d, t] -> [b, n_h, t, d_k]
        b, d, t_s, t_t = (key.size(0), key.size(1), key.size(2), query.size(2))
        query = query.view(b, self.n_heads, self.k_channels, t_t).transpose(2, 3)
        key = key.view(b, self.n_heads, self.k_channels, t_s).transpose(2, 3)
        value = value.view(b, self.n_heads, self.k_channels, t_s).transpose(2, 3)

        # T3 fast path: F.scaled_dot_product_attention fuses Q@K^T / softmax /
        # p_attn@V into one kernel and avoids materializing the [B,H,T,T]
        # activation. The relative-K bias (``scores_local``) and
        # ``proximal_bias`` are folded into ``attn_mask`` as additive biases.
        # The relative-V correction is dropped (requires ``p_attn`` which SDPA
        # does not surface) — this is why the flag is named ``drop_rel_v``.
        # Fallback to the manual path when ``block_length`` is used because
        # that pathway needs a second per-position mask that is cheap to add
        # but currently only exercised by the Decoder (not the TextEncoder).
        if self.drop_rel_v and self.block_length is None:
            attn_bias = None
            if self.window_size is not None:
                assert t_s == t_t, (
                    "Relative attention is only available for self-attention."
                )
                key_relative_embeddings = self._get_relative_embeddings(
                    self.emb_rel_k, t_s
                )
                rel_logits = self._matmul_with_relative_keys(
                    query / math.sqrt(self.k_channels), key_relative_embeddings
                )
                # scores_local: [B, H, T, T] — additive bias, pre-scaled by 1/sqrt(dk).
                # SDPA re-applies scale=1/sqrt(dk) to (Q @ K^T) *inside*, so
                # additive biases are combined post-scale (matches manual math).
                attn_bias = self._relative_position_to_absolute_position(rel_logits)
            if self.proximal_bias:
                assert t_s == t_t, "Proximal bias is only available for self-attention."
                proximal = self._attention_bias_proximal(t_s).type_as(query)
                attn_bias = proximal if attn_bias is None else attn_bias + proximal
            if mask is not None:
                if attn_bias is None:
                    # No prior bias: build a pure additive mask (broadcast-safe).
                    attn_bias = torch.zeros_like(mask, dtype=query.dtype).masked_fill(
                        mask == 0, -1e4
                    )
                else:
                    attn_bias = attn_bias.masked_fill(mask == 0, -1e4)
            dropout_p = self.p_dropout if self.training else 0.0
            output = F.scaled_dot_product_attention(
                query,
                key,
                value,
                attn_mask=attn_bias,
                dropout_p=dropout_p,
                is_causal=False,
            )
            # Match manual-path reshape: [B, H, T_t, d_k] -> [B, d, T_t].
            output = output.transpose(2, 3).contiguous().view(b, d, t_t)
            # SDPA does not expose p_attn. Return a scalar placeholder so
            # ``self.attn = ...`` in ``forward()`` stays wired up cheaply.
            return output, torch.zeros(0, device=output.device, dtype=output.dtype)

        scores = torch.matmul(query / math.sqrt(self.k_channels), key.transpose(-2, -1))
        if self.window_size is not None:
            assert t_s == t_t, (
                "Relative attention is only available for self-attention."
            )
            key_relative_embeddings = self._get_relative_embeddings(self.emb_rel_k, t_s)
            rel_logits = self._matmul_with_relative_keys(
                query / math.sqrt(self.k_channels), key_relative_embeddings
            )
            scores_local = self._relative_position_to_absolute_position(rel_logits)
            scores = scores + scores_local
        if self.proximal_bias:
            assert t_s == t_t, "Proximal bias is only available for self-attention."
            scores = scores + self._attention_bias_proximal(t_s).type_as(scores)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e4)
            if self.block_length is not None:
                assert t_s == t_t, (
                    "Local attention is only available for self-attention."
                )
                block_mask = (
                    torch.ones_like(scores)
                    .triu(-self.block_length)
                    .tril(self.block_length)
                )
                scores = scores.masked_fill(block_mask == 0, -1e4)
        p_attn = F.softmax(scores, dim=-1)  # [b, n_h, t_t, t_s]
        p_attn = self.drop(p_attn)
        output = torch.matmul(p_attn, value)
        if self.window_size is not None:
            relative_weights = self._absolute_position_to_relative_position(p_attn)
            value_relative_embeddings = self._get_relative_embeddings(
                self.emb_rel_v, t_s
            )
            output = output + self._matmul_with_relative_values(
                relative_weights, value_relative_embeddings
            )
        output = (
            output.transpose(2, 3).contiguous().view(b, d, t_t)
        )  # [b, n_h, t_t, d_k] -> [b, d, t_t]
        return output, p_attn

    def _matmul_with_relative_values(self, x, y):
        """
        x: [b, h, l, m]
        y: [h or 1, m, d]
        ret: [b, h, l, d]
        """
        ret = torch.matmul(x, y.unsqueeze(0))
        return ret

    def _matmul_with_relative_keys(self, x, y):
        """
        x: [b, h, l, d]
        y: [h or 1, m, d]
        ret: [b, h, l, m]
        """
        ret = torch.matmul(x, y.unsqueeze(0).transpose(-2, -1))
        return ret

    def _get_relative_embeddings(self, relative_embeddings, length: int):
        # max_relative_position = 2 * self.window_size + 1
        # Pad first before slice to avoid using cond ops.
        pad_length = max(length - (self.window_size + 1), 0)
        slice_start_position = max((self.window_size + 1) - length, 0)
        slice_end_position = slice_start_position + 2 * length - 1
        if pad_length > 0:
            padded_relative_embeddings = F.pad(
                relative_embeddings,
                # convert_pad_shape([[0, 0], [pad_length, pad_length], [0, 0]]),
                (0, 0, pad_length, pad_length, 0, 0),
            )
        else:
            padded_relative_embeddings = relative_embeddings
        used_relative_embeddings = padded_relative_embeddings[
            :, slice_start_position:slice_end_position
        ]
        return used_relative_embeddings

    def _relative_position_to_absolute_position(self, x):
        """
        x: [b, h, l, 2*l-1]
        ret: [b, h, l, l]
        """
        batch, heads, length, _ = x.size()

        # Concat columns of pad to shift from relative to absolute indexing.
        # x = F.pad(x, convert_pad_shape([[0, 0], [0, 0], [0, 0], [0, 1]]))
        x = F.pad(x, (0, 1, 0, 0, 0, 0, 0, 0))

        # Concat extra elements so to add up to shape (len+1, 2*len-1).
        x_flat = x.view([batch, heads, length * 2 * length])
        # x_flat = F.pad(x_flat, convert_pad_shape([[0, 0], [0, 0], [0, length - 1]]))
        x_flat = F.pad(x_flat, (0, length - 1, 0, 0, 0, 0))

        # Reshape and slice out the padded elements.
        x_final = x_flat.view([batch, heads, length + 1, (2 * length) - 1])[
            :, :, :length, length - 1 :
        ]
        return x_final

    def _absolute_position_to_relative_position(self, x):
        """
        x: [b, h, l, l]
        ret: [b, h, l, 2*l-1]
        """
        batch, heads, length, _ = x.size()

        # padd along column
        # x = F.pad(x, convert_pad_shape([[0, 0], [0, 0], [0, 0], [0, length - 1]]))
        x = F.pad(x, (0, length - 1, 0, 0, 0, 0, 0, 0))
        x_flat = x.view([batch, heads, (length * length) + (length * (length - 1))])
        # add 0's in the beginning that will skew the elements after reshape
        # x_flat = F.pad(x_flat, convert_pad_shape([[0, 0], [0, 0], [length, 0]]))
        x_flat = F.pad(x_flat, (length, 0, 0, 0, 0, 0))
        x_final = x_flat.view([batch, heads, length, 2 * length])[:, :, :, 1:]
        return x_final

    def _attention_bias_proximal(self, length: int):
        """Bias for self-attention to encourage attention to close positions.
        Args:
          length: an integer scalar.
        Returns:
          a Tensor with shape [1, 1, length, length]
        """
        r = torch.arange(length, dtype=torch.float32)
        diff = torch.unsqueeze(r, 0) - torch.unsqueeze(r, 1)
        return torch.unsqueeze(torch.unsqueeze(-torch.log1p(torch.abs(diff)), 0), 0)


class FFN(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        filter_channels: int,
        kernel_size: int,
        p_dropout: float = 0.0,
        activation: str = "",
        causal: bool = False,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.filter_channels = filter_channels
        self.kernel_size = kernel_size
        self.p_dropout = p_dropout
        self.activation = activation
        self.causal = causal

        self.conv_1 = nn.Conv1d(in_channels, filter_channels, kernel_size)
        self.conv_2 = nn.Conv1d(filter_channels, out_channels, kernel_size)
        self.drop = nn.Dropout(p_dropout)

    def forward(self, x, x_mask):
        if self.causal:
            padding1 = self._causal_padding(x * x_mask)
        else:
            padding1 = self._same_padding(x * x_mask)

        x = self.conv_1(padding1)

        if self.activation == "gelu":
            x = x * torch.sigmoid(1.702 * x)
        else:
            x = torch.relu(x)
        x = self.drop(x)

        if self.causal:
            padding2 = self._causal_padding(x * x_mask)
        else:
            padding2 = self._same_padding(x * x_mask)

        x = self.conv_2(padding2)

        return x * x_mask

    def _causal_padding(self, x):
        if self.kernel_size == 1:
            return x
        pad_l = self.kernel_size - 1
        pad_r = 0
        # padding = [[0, 0], [0, 0], [pad_l, pad_r]]
        # x = F.pad(x, convert_pad_shape(padding))
        x = F.pad(x, (pad_l, pad_r, 0, 0, 0, 0))
        return x

    def _same_padding(self, x):
        if self.kernel_size == 1:
            return x
        pad_l = (self.kernel_size - 1) // 2
        pad_r = self.kernel_size // 2
        # padding = [[0, 0], [0, 0], [pad_l, pad_r]]
        # x = F.pad(x, convert_pad_shape(padding))
        x = F.pad(x, (pad_l, pad_r, 0, 0, 0, 0))
        return x
