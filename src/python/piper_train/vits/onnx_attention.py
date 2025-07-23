"""
ONNX-friendly Custom Attention Implementation for F0 Predictor

This module provides a custom attention implementation that avoids
the reshape issues present in PyTorch's nn.MultiheadAttention during ONNX export.
"""

import torch
import torch.nn.functional as F
from torch import nn

from .modules import ConvReluNorm


class ONNXFriendlyAttention(nn.Module):
    """
    ONNX-compatible multi-head attention implementation.

    Unlike nn.MultiheadAttention, this implementation uses Conv1D operations
    and avoids problematic reshape operations that cause fixed-size constraints
    during ONNX export.
    """

    def __init__(self, hidden_channels: int, n_heads: int = 2, dropout: float = 0.1):
        super().__init__()

        assert hidden_channels % n_heads == 0, (
            f"hidden_channels {hidden_channels} must be divisible by n_heads {n_heads}"
        )

        self.hidden_channels = hidden_channels
        self.n_heads = n_heads
        self.head_dim = hidden_channels // n_heads
        self.scale = self.head_dim**-0.5

        # Use Conv1D for projections to avoid reshape issues
        self.q_proj = nn.Conv1d(
            hidden_channels, hidden_channels, kernel_size=1, bias=True
        )
        self.k_proj = nn.Conv1d(
            hidden_channels, hidden_channels, kernel_size=1, bias=True
        )
        self.v_proj = nn.Conv1d(
            hidden_channels, hidden_channels, kernel_size=1, bias=True
        )
        self.out_proj = nn.Conv1d(
            hidden_channels, hidden_channels, kernel_size=1, bias=True
        )

        self.dropout = nn.Dropout(dropout)

        # Initialize weights
        self._init_weights()

    def _init_weights(self):
        """Initialize weights similar to nn.MultiheadAttention"""
        for proj in [self.q_proj, self.k_proj, self.v_proj]:
            nn.init.xavier_uniform_(proj.weight)
            if proj.bias is not None:
                nn.init.constant_(proj.bias, 0)

        nn.init.xavier_uniform_(self.out_proj.weight)
        if self.out_proj.bias is not None:
            nn.init.constant_(self.out_proj.bias, 0)

    def forward(
        self, x: torch.Tensor, key_padding_mask: torch.Tensor = None
    ) -> torch.Tensor:
        """
        Forward pass of ONNX-friendly attention.

        Args:
            x: Input tensor [B, C, T] where C = hidden_channels
            key_padding_mask: Optional mask [B, T] where True indicates padding

        Returns:
            Output tensor [B, C, T] with same shape as input
        """
        B, C, T = x.shape

        # Project to Q, K, V using Conv1D
        q = self.q_proj(x)  # [B, C, T]
        k = self.k_proj(x)  # [B, C, T]
        v = self.v_proj(x)  # [B, C, T]

        # Reshape for multi-head attention
        # [B, C, T] -> [B, n_heads, head_dim, T]
        q = q.view(B, self.n_heads, self.head_dim, T)
        k = k.view(B, self.n_heads, self.head_dim, T)
        v = v.view(B, self.n_heads, self.head_dim, T)

        # Compute attention scores
        # [B, n_heads, head_dim, T] @ [B, n_heads, T, head_dim] -> [B, n_heads, T, T]
        attn_scores = torch.matmul(q.transpose(-2, -1), k) * self.scale

        # Apply key padding mask if provided
        if key_padding_mask is not None:
            # key_padding_mask: [B, T] -> [B, 1, 1, T]
            mask = key_padding_mask.unsqueeze(1).unsqueeze(1)
            attn_scores = attn_scores.masked_fill(mask, float("-inf"))

        # Apply softmax
        attn_weights = F.softmax(attn_scores, dim=-1)
        attn_weights = self.dropout(attn_weights)

        # Apply attention to values
        # [B, n_heads, T, T] @ [B, n_heads, T, head_dim] -> [B, n_heads, T, head_dim]
        attn_output = torch.matmul(attn_weights, v.transpose(-2, -1))

        # Reshape back to [B, C, T]
        attn_output = attn_output.transpose(
            -2, -1
        ).contiguous()  # [B, n_heads, head_dim, T]
        attn_output = attn_output.view(B, C, T)

        # Final projection
        output = self.out_proj(attn_output)

        return output

    def migrate_from_multihead_attention(self, multihead_attn: nn.MultiheadAttention):
        """
        Migrate weights from PyTorch's nn.MultiheadAttention to this implementation.

        Args:
            multihead_attn: Source nn.MultiheadAttention module
        """
        with torch.no_grad():
            # Get weights from the source attention
            in_proj_weight = (
                multihead_attn.in_proj_weight
            )  # [3*hidden_channels, hidden_channels]
            in_proj_bias = multihead_attn.in_proj_bias  # [3*hidden_channels]
            out_proj_weight = (
                multihead_attn.out_proj.weight
            )  # [hidden_channels, hidden_channels]
            out_proj_bias = multihead_attn.out_proj.bias  # [hidden_channels]

            # Split in_proj_weight into Q, K, V components
            hidden_dim = self.hidden_channels
            q_weight = in_proj_weight[
                :hidden_dim, :
            ]  # [hidden_channels, hidden_channels]
            k_weight = in_proj_weight[
                hidden_dim : 2 * hidden_dim, :
            ]  # [hidden_channels, hidden_channels]
            v_weight = in_proj_weight[
                2 * hidden_dim :, :
            ]  # [hidden_channels, hidden_channels]

            q_bias = in_proj_bias[:hidden_dim]  # [hidden_channels]
            k_bias = in_proj_bias[hidden_dim : 2 * hidden_dim]  # [hidden_channels]
            v_bias = in_proj_bias[2 * hidden_dim :]  # [hidden_channels]

            # Copy weights to Conv1D layers (add unsqueeze(-1) for conv kernel dimension)
            self.q_proj.weight.copy_(q_weight.unsqueeze(-1))
            self.k_proj.weight.copy_(k_weight.unsqueeze(-1))
            self.v_proj.weight.copy_(v_weight.unsqueeze(-1))

            self.q_proj.bias.copy_(q_bias)
            self.k_proj.bias.copy_(k_bias)
            self.v_proj.bias.copy_(v_bias)

            # Copy output projection weights
            self.out_proj.weight.copy_(out_proj_weight.unsqueeze(-1))
            self.out_proj.bias.copy_(out_proj_bias)

        print(
            "Successfully migrated MultiheadAttention weights to ONNXFriendlyAttention"
        )
        print(f"Hidden channels: {self.hidden_channels}, Heads: {self.n_heads}")


class ONNXFriendlyF0Predictor(nn.Module):
    """
    F0 Predictor with ONNX-friendly attention implementation.

    This is a drop-in replacement for the original F0Predictor that uses
    ONNXFriendlyAttention instead of nn.MultiheadAttention.
    """

    def __init__(
        self,
        hidden_channels: int = 192,
        filter_channels: int = 768,
        n_heads: int = 2,
        n_layers: int = 4,
        kernel_size: int = 3,
        p_dropout: float = 0.1,
        n_bins: int = 256,
        min_f0: float = 50.0,
        max_f0: float = 800.0,
        use_log_f0: bool = True,
        gin_channels: int = 0,
    ):
        super().__init__()
        self.hidden_channels = hidden_channels
        self.filter_channels = filter_channels
        self.n_bins = n_bins
        self.min_f0 = min_f0
        self.max_f0 = max_f0
        self.use_log_f0 = use_log_f0
        self.gin_channels = gin_channels

        # F0 encoder layers (keep original implementation)
        self.encoder_layers = nn.ModuleList()
        for _ in range(n_layers):
            self.encoder_layers.append(
                ConvReluNorm(
                    hidden_channels,
                    hidden_channels,
                    hidden_channels,
                    kernel_size,
                    2,
                    p_dropout,
                )
            )

        # Replace MultiheadAttention with ONNX-friendly version
        self.attention = ONNXFriendlyAttention(
            hidden_channels, n_heads, dropout=p_dropout
        )

        # Prosody embedding (keep original)
        self.prosody_embed = nn.Embedding(16, hidden_channels)

        # F0 prediction head (keep original)
        self.f0_proj = nn.Sequential(
            nn.Conv1d(
                hidden_channels, filter_channels, kernel_size, padding=kernel_size // 2
            ),
            nn.ReLU(),
            nn.Dropout(p_dropout),
            nn.Conv1d(
                filter_channels, hidden_channels, kernel_size, padding=kernel_size // 2
            ),
            nn.ReLU(),
            nn.Dropout(p_dropout),
            nn.Conv1d(hidden_channels, n_bins, 1),
        )

        # Variance predictor (keep original)
        self.variance_proj = nn.Conv1d(hidden_channels, 1, 1)

        # Speaker conditioning (keep original)
        if gin_channels > 0:
            self.cond = nn.Conv1d(gin_channels, hidden_channels, 1)

    def forward(self, x, x_mask=None, prosody_ids=None, g=None):
        """
        Forward pass - same interface as original F0Predictor
        """
        # Apply speaker conditioning
        if g is not None:
            x = x + self.cond(g)

        # Add prosody embeddings if provided
        if prosody_ids is not None:
            prosody_ids = prosody_ids.long()
            prosody_emb = self.prosody_embed(prosody_ids)  # [B, T, hidden]
            prosody_emb = prosody_emb.transpose(1, 2)  # [B, hidden, T]
            x = x + prosody_emb

        # Encoder layers with residual connections
        for layer in self.encoder_layers:
            residual = x
            if x_mask is not None:
                x = layer(x, x_mask)
            else:
                dummy_mask = torch.ones_like(x[:, :1, :])
                x = layer(x, dummy_mask)
            x = x + residual

        # ONNX-friendly attention
        key_padding_mask = None
        if x_mask is not None:
            # Convert mask from [B, 1, T] to [B, T] and invert (True = padding)
            key_padding_mask = x_mask.squeeze(1) == 0

        x_att = self.attention(x, key_padding_mask)
        x = x + x_att

        # F0 prediction
        f0_prediction = self.f0_proj(x)  # [B, n_bins, T]

        # Convert to continuous F0 values
        f0_values = self._bins_to_f0(f0_prediction)

        # Predict variance for uncertainty
        variance = F.softplus(self.variance_proj(x))

        # Apply mask
        if x_mask is not None:
            f0_prediction = f0_prediction * x_mask
            f0_values = f0_values * x_mask
            variance = variance * x_mask

        return f0_prediction, f0_values, variance

    def _bins_to_f0(self, f0_bins):
        """Convert F0 bins to continuous F0 values"""
        if self.use_log_f0:
            min_val = torch.log(torch.tensor(self.min_f0))
            max_val = torch.log(torch.tensor(self.max_f0))
        else:
            min_val = torch.tensor(self.min_f0)
            max_val = torch.tensor(self.max_f0)

        # Create bin centers
        bin_centers = torch.linspace(min_val, max_val, self.n_bins)
        bin_centers = bin_centers.to(f0_bins.device)

        # Weighted average over bins
        f0_probs = F.softmax(f0_bins, dim=1)  # [B, n_bins, T]
        f0_values = torch.sum(
            f0_probs * bin_centers.view(1, -1, 1), dim=1, keepdim=True
        )  # [B, 1, T]

        if self.use_log_f0:
            f0_values = torch.exp(f0_values)

        return f0_values
