import torch
import torch.nn as nn
import torch.nn.functional as F
from .modules import ConvReluNorm, WN


class F0Predictor(nn.Module):
    """F0 predictor module for improving intonation and accent control.
    
    Based on FastSpeech2 architecture with modifications for Japanese prosody.
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
        
        # F0 encoder layers
        self.encoder_layers = nn.ModuleList()
        for _ in range(n_layers):
            self.encoder_layers.append(
                ConvReluNorm(
                    hidden_channels,
                    hidden_channels,
                    kernel_size,
                    p_dropout=p_dropout
                )
            )
        
        # Multi-head self-attention for context modeling
        self.attention = nn.MultiheadAttention(
            hidden_channels,
            n_heads,
            dropout=p_dropout,
            batch_first=True
        )
        
        # Prosody embedding for Japanese accent marks
        # Maps prosody symbols to learned embeddings
        self.prosody_embed = nn.Embedding(16, hidden_channels)  # 16 prosody types
        
        # F0 prediction head
        self.f0_proj = nn.Sequential(
            nn.Conv1d(hidden_channels, filter_channels, kernel_size, padding=kernel_size//2),
            nn.ReLU(),
            nn.Dropout(p_dropout),
            nn.Conv1d(filter_channels, hidden_channels, kernel_size, padding=kernel_size//2),
            nn.ReLU(),
            nn.Dropout(p_dropout),
            nn.Conv1d(hidden_channels, n_bins, 1)  # Output discrete F0 bins
        )
        
        # Variance predictor for F0 uncertainty
        self.variance_proj = nn.Conv1d(hidden_channels, 1, 1)
        
        # Speaker conditioning if multi-speaker
        if gin_channels > 0:
            self.cond = nn.Conv1d(gin_channels, hidden_channels, 1)
            
    def forward(self, x, x_mask=None, prosody_ids=None, g=None):
        """
        Args:
            x: Input features [B, hidden_channels, T]
            x_mask: Mask for valid positions [B, 1, T]
            prosody_ids: Prosody mark IDs [B, T]
            g: Speaker embedding [B, gin_channels, 1]
        
        Returns:
            f0_prediction: Discrete F0 bins [B, n_bins, T]
            f0_values: Continuous F0 values [B, 1, T]
            variance: F0 variance for uncertainty [B, 1, T]
        """
        # Apply speaker conditioning
        if g is not None:
            x = x + self.cond(g)
            
        # Add prosody embeddings if provided
        if prosody_ids is not None:
            prosody_emb = self.prosody_embed(prosody_ids)  # [B, T, hidden]
            prosody_emb = prosody_emb.transpose(1, 2)  # [B, hidden, T]
            x = x + prosody_emb
            
        # Encoder layers with residual connections
        for layer in self.encoder_layers:
            residual = x
            x = layer(x * x_mask if x_mask is not None else x)
            x = x + residual
            
        # Self-attention for long-range dependencies
        x_seq = x.transpose(1, 2)  # [B, T, hidden]
        x_att, _ = self.attention(x_seq, x_seq, x_seq,
                                  key_padding_mask=x_mask.squeeze(1) == 0 if x_mask is not None else None)
        x = x + x_att.transpose(1, 2)
        
        # F0 prediction
        f0_prediction = self.f0_proj(x)  # [B, n_bins, T]
        
        # Convert to continuous F0 values
        f0_values = self._bins_to_f0(f0_prediction)
        
        # Predict variance for uncertainty
        variance = F.softplus(self.variance_proj(x))
        
        if x_mask is not None:
            f0_prediction = f0_prediction * x_mask
            f0_values = f0_values * x_mask
            variance = variance * x_mask
            
        return f0_prediction, f0_values, variance
    
    def _bins_to_f0(self, f0_bins):
        """Convert discrete F0 bins to continuous F0 values."""
        # Apply softmax to get probabilities
        f0_probs = F.softmax(f0_bins, dim=1)  # [B, n_bins, T]
        
        # Create bin centers
        if self.use_log_f0:
            min_val = torch.log(torch.tensor(self.min_f0))
            max_val = torch.log(torch.tensor(self.max_f0))
        else:
            min_val = self.min_f0
            max_val = self.max_f0
            
        bin_centers = torch.linspace(min_val, max_val, self.n_bins, device=f0_bins.device)
        bin_centers = bin_centers.view(1, -1, 1)  # [1, n_bins, 1]
        
        # Weighted sum to get continuous F0
        f0_continuous = torch.sum(f0_probs * bin_centers, dim=1, keepdim=True)  # [B, 1, T]
        
        # Convert back from log space if needed
        if self.use_log_f0:
            f0_continuous = torch.exp(f0_continuous)
            
        return f0_continuous


class F0Loss(nn.Module):
    """Combined loss for F0 prediction."""
    def __init__(self, lambda_ce=1.0, lambda_mse=0.5, lambda_var=0.1):
        super().__init__()
        self.lambda_ce = lambda_ce
        self.lambda_mse = lambda_mse
        self.lambda_var = lambda_var
        
    def forward(self, f0_pred_bins, f0_pred_values, f0_variance, f0_true, x_mask=None):
        """
        Args:
            f0_pred_bins: Predicted F0 bins [B, n_bins, T]
            f0_pred_values: Predicted continuous F0 [B, 1, T]
            f0_variance: Predicted variance [B, 1, T]
            f0_true: Ground truth F0 values [B, 1, T]
            x_mask: Valid position mask [B, 1, T]
        """
        if x_mask is not None:
            # Apply mask
            f0_true = f0_true * x_mask
            f0_pred_values = f0_pred_values * x_mask
            f0_variance = f0_variance * x_mask
            mask_sum = x_mask.sum()
        else:
            mask_sum = f0_true.numel()
            
        # MSE loss for continuous F0
        mse_loss = F.mse_loss(f0_pred_values, f0_true, reduction='sum') / mask_sum
        
        # Variance-weighted loss (uncertainty awareness)
        weighted_mse = ((f0_pred_values - f0_true) ** 2 / (2 * f0_variance) + 
                       0.5 * torch.log(f0_variance))
        if x_mask is not None:
            weighted_mse = weighted_mse * x_mask
        var_loss = weighted_mse.sum() / mask_sum
        
        # Total loss
        total_loss = self.lambda_mse * mse_loss + self.lambda_var * var_loss
        
        return total_loss, {
            'f0_mse': mse_loss.item(),
            'f0_var': var_loss.item()
        }