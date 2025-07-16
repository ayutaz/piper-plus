"""Conditional Flow Matching for VITS.

This module implements Conditional Flow Matching (CFM) as an alternative to
the original normalizing flow in VITS. CFM provides more stable training
and potentially better quality.

References:
- Flow Matching for Generative Modeling (Lipman et al., 2023)
- Matcha-TTS: A fast TTS architecture with conditional flow matching
"""

import torch
import torch.nn.functional as F
from torch import nn

try:
    from torchdiffeq import odeint

    ODE_AVAILABLE = True
except ImportError:
    ODE_AVAILABLE = False
    print("Warning: torchdiffeq not available. Install with: pip install torchdiffeq")


class ConditionalFlowMatcher(nn.Module):
    """Conditional Flow Matching module for VITS.

    This replaces the normalizing flow in VITS with a conditional flow matching
    approach, which learns a continuous-time flow between noise and data.
    """

    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        n_layers: int,
        n_flows: int = 4,
        gin_channels: int = 0,
        p_dropout: float = 0.0,
        sigmoid_scale: bool = False,
    ):
        super().__init__()

        if not ODE_AVAILABLE:
            raise ImportError(
                "torchdiffeq is required for Flow Matching. "
                "Please install it with: pip install torchdiffeq"
            )

        self.channels = channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.n_flows = n_flows
        self.gin_channels = gin_channels
        self.p_dropout = p_dropout
        self.sigmoid_scale = sigmoid_scale

        # Time embedding
        self.time_embed = TimeEmbedding(hidden_channels)

        # Flow estimator network
        self.estimator = FlowEstimator(
            channels,
            hidden_channels,
            kernel_size,
            n_layers,
            gin_channels=gin_channels,
            p_dropout=p_dropout,
        )

    def forward(
        self,
        z: torch.Tensor,
        x_mask: torch.Tensor,
        g: torch.Tensor | None = None,
        reverse: bool = False,
        **kwargs,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward or reverse flow matching.

        Args:
            z: Input tensor [B, C, T]
            x_mask: Mask tensor [B, 1, T]
            g: Global conditioning [B, C_g, T]
            reverse: If True, convert data to noise; if False, convert noise to data

        Returns:
            output: Transformed tensor [B, C, T]
            log_det: Log determinant (always 0 for CFM)
        """
        if reverse:
            # Data to noise (encoding)
            return self._reverse_flow(z, x_mask, g)
        else:
            # Noise to data (generation)
            return self._forward_flow(z, x_mask, g)

    def _forward_flow(
        self, z: torch.Tensor, x_mask: torch.Tensor, g: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Forward flow: noise to data."""
        batch_size = z.shape[0]

        # Define ODE function
        def ode_func(t, x):
            # Expand time to match batch size
            t_expanded = t.expand(batch_size)
            # Get velocity field
            v_t = self.estimator(x, t_expanded, x_mask, g)
            return v_t

        # Solve ODE from t=0 to t=1
        t_span = torch.tensor([0.0, 1.0], device=z.device)
        # Use adaptive solver for better quality
        x_1 = odeint(
            ode_func,
            z,
            t_span,
            method="dopri5",
            atol=1e-5,
            rtol=1e-5,
        )[-1]

        # Apply mask
        x_1 = x_1 * x_mask

        # CFM has zero log determinant by construction
        log_det = torch.zeros(batch_size, device=z.device)

        return x_1, log_det

    def _reverse_flow(
        self, x: torch.Tensor, x_mask: torch.Tensor, g: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Reverse flow: data to noise."""
        batch_size = x.shape[0]

        # Define ODE function (reverse time)
        def ode_func(t, z):
            # Expand time to match batch size
            t_expanded = t.expand(batch_size)
            # Get velocity field (negative for reverse)
            v_t = -self.estimator(z, 1.0 - t_expanded, x_mask, g)
            return v_t

        # Solve ODE from t=0 to t=1 (which is t=1 to t=0 in forward time)
        t_span = torch.tensor([0.0, 1.0], device=x.device)
        z_0 = odeint(
            ode_func,
            x,
            t_span,
            method="dopri5",
            atol=1e-5,
            rtol=1e-5,
        )[-1]

        # Apply mask
        z_0 = z_0 * x_mask

        # CFM has zero log determinant
        log_det = torch.zeros(batch_size, device=x.device)

        return z_0, log_det

    def compute_loss(
        self, x_1: torch.Tensor, x_mask: torch.Tensor, g: torch.Tensor | None = None
    ) -> torch.Tensor:
        """Compute flow matching loss.

        Args:
            x_1: Data samples [B, C, T]
            x_mask: Mask tensor [B, 1, T]
            g: Global conditioning [B, C_g, T]

        Returns:
            loss: Flow matching loss
        """
        batch_size, channels, length = x_1.shape

        # Sample random time
        t = torch.rand(batch_size, 1, 1, device=x_1.device)

        # Sample noise
        x_0 = torch.randn_like(x_1)

        # Interpolate between noise and data
        x_t = t * x_1 + (1 - t) * x_0

        # Target velocity field
        v_target = x_1 - x_0

        # Flatten time for the estimator
        t_flat = t.squeeze(-1).squeeze(-1)

        # Predicted velocity field
        v_pred = self.estimator(x_t, t_flat, x_mask, g)

        # MSE loss
        loss = F.mse_loss(v_pred * x_mask, v_target * x_mask)

        return loss


class TimeEmbedding(nn.Module):
    """Sinusoidal time embedding."""

    def __init__(self, hidden_channels: int):
        super().__init__()
        self.hidden_channels = hidden_channels
        self.projection = nn.Sequential(
            nn.Linear(hidden_channels, hidden_channels * 4),
            nn.SiLU(),
            nn.Linear(hidden_channels * 4, hidden_channels),
        )

    def forward(self, t: torch.Tensor) -> torch.Tensor:
        """Create sinusoidal time embeddings.

        Args:
            t: Time values [B]

        Returns:
            embeddings: Time embeddings [B, C]
        """
        half_dim = self.hidden_channels // 2
        embeddings = torch.zeros(t.shape[0], self.hidden_channels, device=t.device)

        # Sinusoidal embeddings
        embeddings[:, 0::2] = torch.sin(
            t[:, None]
            * torch.pow(10000, torch.arange(0, half_dim, device=t.device) / half_dim)
        )
        embeddings[:, 1::2] = torch.cos(
            t[:, None]
            * torch.pow(10000, torch.arange(0, half_dim, device=t.device) / half_dim)
        )

        # Project
        embeddings = self.projection(embeddings)

        return embeddings


class FlowEstimator(nn.Module):
    """Velocity field estimator for flow matching."""

    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        n_layers: int,
        gin_channels: int = 0,
        p_dropout: float = 0.0,
    ):
        super().__init__()

        self.channels = channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.n_layers = n_layers
        self.gin_channels = gin_channels
        self.p_dropout = p_dropout

        # Time embedding
        self.time_embed = TimeEmbedding(hidden_channels)

        # Pre-convolution
        self.pre_conv = nn.Conv1d(channels, hidden_channels, 1)

        # Dilated convolution layers
        self.conv_layers = nn.ModuleList()
        self.norm_layers = nn.ModuleList()

        for i in range(n_layers):
            dilation = 2**i
            padding = (kernel_size * dilation - dilation) // 2
            conv = nn.Conv1d(
                hidden_channels,
                hidden_channels * 2,
                kernel_size,
                padding=padding,
                dilation=dilation,
            )
            self.conv_layers.append(conv)
            self.norm_layers.append(nn.GroupNorm(8, hidden_channels))

        # Post-convolution
        self.post_conv = nn.Conv1d(hidden_channels, channels, 1)
        nn.init.zeros_(self.post_conv.weight)
        nn.init.zeros_(self.post_conv.bias)

        # Conditioning
        if gin_channels > 0:
            self.cond_layer = nn.Conv1d(gin_channels, hidden_channels, 1)

        # Dropout
        self.dropout = nn.Dropout(p_dropout)

    def forward(
        self,
        x: torch.Tensor,
        t: torch.Tensor,
        x_mask: torch.Tensor,
        g: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """Estimate velocity field.

        Args:
            x: Input tensor [B, C, T]
            t: Time values [B]
            x_mask: Mask tensor [B, 1, T]
            g: Global conditioning [B, C_g, T]

        Returns:
            v: Velocity field [B, C, T]
        """
        # Get time embedding
        t_emb = self.time_embed(t)  # [B, C]

        # Pre-convolution
        h = self.pre_conv(x) * x_mask

        # Add conditioning if available
        if g is not None and self.gin_channels > 0:
            h = h + self.cond_layer(g)

        # Dilated convolutions with residual connections
        for _, (conv, norm) in enumerate(
            zip(self.conv_layers, self.norm_layers, strict=False)
        ):
            # Add time embedding
            h_time = h + t_emb.unsqueeze(-1)

            # Convolution
            h_conv = conv(h_time)

            # Gated activation
            h_1, h_2 = torch.chunk(h_conv, 2, dim=1)
            h_gated = torch.tanh(h_1) * torch.sigmoid(h_2)

            # Normalize and dropout
            h_gated = norm(h_gated)
            h_gated = self.dropout(h_gated)

            # Residual connection
            h = h + h_gated

        # Apply mask
        h = h * x_mask

        # Post-convolution
        v = self.post_conv(h) * x_mask

        return v


class FlowMatchingBlock(nn.Module):
    """Flow matching block that can replace ResidualCouplingBlock."""

    def __init__(
        self,
        channels: int,
        hidden_channels: int,
        kernel_size: int,
        dilation_rate: int,
        n_layers: int,
        n_flows: int = 4,
        gin_channels: int = 0,
        share_parameter: bool = False,
    ):
        super().__init__()

        self.channels = channels
        self.hidden_channels = hidden_channels
        self.kernel_size = kernel_size
        self.dilation_rate = dilation_rate
        self.n_layers = n_layers
        self.n_flows = n_flows
        self.gin_channels = gin_channels
        self.share_parameter = share_parameter

        # Create flow matching layers
        if share_parameter:
            # Share parameters across flows
            flow = ConditionalFlowMatcher(
                channels,
                hidden_channels,
                kernel_size,
                n_layers,
                n_flows=1,
                gin_channels=gin_channels,
            )
            self.flows = nn.ModuleList([flow] * n_flows)
        else:
            # Independent parameters for each flow
            self.flows = nn.ModuleList(
                [
                    ConditionalFlowMatcher(
                        channels,
                        hidden_channels,
                        kernel_size,
                        n_layers,
                        n_flows=1,
                        gin_channels=gin_channels,
                    )
                    for _ in range(n_flows)
                ]
            )

    def forward(
        self,
        x: torch.Tensor,
        x_mask: torch.Tensor,
        g: torch.Tensor | None = None,
        reverse: bool = False,
    ) -> torch.Tensor:
        """Apply flow matching transformations.

        Args:
            x: Input tensor [B, C, T]
            x_mask: Mask tensor [B, 1, T]
            g: Global conditioning [B, C_g, T]
            reverse: If True, apply flows in reverse order

        Returns:
            output: Transformed tensor [B, C, T]
        """
        if not reverse:
            for flow in self.flows:
                x, _ = flow(x, x_mask, g=g, reverse=False)
        else:
            for flow in reversed(self.flows):
                x, _ = flow(x, x_mask, g=g, reverse=True)

        return x

    def compute_loss(
        self, x: torch.Tensor, x_mask: torch.Tensor, g: torch.Tensor | None = None
    ) -> torch.Tensor:
        """Compute total flow matching loss.

        Args:
            x: Data samples [B, C, T]
            x_mask: Mask tensor [B, 1, T]
            g: Global conditioning [B, C_g, T]

        Returns:
            loss: Total flow matching loss
        """
        total_loss = 0.0

        for flow in self.flows:
            loss = flow.compute_loss(x, x_mask, g)
            total_loss = total_loss + loss

        return total_loss / len(self.flows)
