"""WavLM-based Discriminator for enhanced perceptual quality evaluation.

Based on StyleTTS2 and recent TTS research showing significant improvements
in prosody and naturalness when using pretrained speech models as discriminators.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils import spectral_norm, weight_norm

try:
    from transformers import WavLMModel, WavLMConfig
    WAVLM_AVAILABLE = True
except ImportError:
    WAVLM_AVAILABLE = False
    print("Warning: transformers library not found. WavLM discriminator will not be available.")


class DiscriminatorHead(nn.Module):
    """Single discriminator head for multi-scale discrimination."""
    
    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        kernel_size: int = 5,
        pool_size: int = 4,
        pool_stride: int = 2,
        norm_type: str = "spectral"
    ):
        super().__init__()
        
        # Pooling for different temporal resolutions
        self.pool = nn.AvgPool1d(kernel_size=pool_size, stride=pool_stride)
        
        # Convolutional layers
        self.convs = nn.ModuleList()
        
        # Layer dimensions
        dims = [input_dim, hidden_dim, hidden_dim // 2, hidden_dim // 4, 1]
        
        for in_dim, out_dim in zip(dims[:-1], dims[1:]):
            if norm_type == "spectral":
                conv = spectral_norm(
                    nn.Conv1d(in_dim, out_dim, kernel_size, padding=kernel_size // 2)
                )
            elif norm_type == "weight":
                conv = weight_norm(
                    nn.Conv1d(in_dim, out_dim, kernel_size, padding=kernel_size // 2)
                )
            else:
                conv = nn.Conv1d(in_dim, out_dim, kernel_size, padding=kernel_size // 2)
            
            self.convs.append(conv)
        
        self.activation = nn.LeakyReLU(0.2)
        
    def forward(self, x):
        """Forward pass returning both predictions and feature maps.
        
        Args:
            x: Input features [B, C, T]
            
        Returns:
            predictions: Discriminator predictions [B, 1, T']
            feature_maps: List of intermediate feature maps
        """
        feature_maps = []
        
        # Apply pooling
        x = self.pool(x)
        
        # Pass through convolutional layers
        for i, conv in enumerate(self.convs):
            x = conv(x)
            if i < len(self.convs) - 1:
                x = self.activation(x)
            feature_maps.append(x)
            
        return x, feature_maps


class WavLMDiscriminator(nn.Module):
    """Multi-scale discriminator using pretrained WavLM features.
    
    This discriminator leverages the powerful representations learned by WavLM
    to better evaluate speech quality, particularly for prosody and naturalness.
    """
    
    def __init__(
        self,
        pretrained_model: str = "microsoft/wavlm-base",
        freeze_feature_extractor: bool = True,
        freeze_encoder_layers: int = 10,
        hidden_size: int = 768,
        use_weighted_sum: bool = True,
        norm_type: str = "spectral",
        disc_hidden_dim: int = 256,
        num_disc_layers: int = 3
    ):
        super().__init__()
        
        if not WAVLM_AVAILABLE:
            raise ImportError(
                "transformers library is required for WavLM discriminator. "
                "Please install it with: pip install transformers"
            )
        
        # Load pretrained WavLM
        self.wavlm = WavLMModel.from_pretrained(pretrained_model)
        self.hidden_size = self.wavlm.config.hidden_size
        
        # Freeze feature extractor
        if freeze_feature_extractor:
            for param in self.wavlm.feature_extractor.parameters():
                param.requires_grad = False
            for param in self.wavlm.feature_projection.parameters():
                param.requires_grad = False
        
        # Freeze encoder layers
        num_layers = len(self.wavlm.encoder.layers)
        freeze_encoder_layers = min(freeze_encoder_layers, num_layers - 2)
        for i in range(freeze_encoder_layers):
            for param in self.wavlm.encoder.layers[i].parameters():
                param.requires_grad = False
        
        # Learnable weighted sum of hidden states
        self.use_weighted_sum = use_weighted_sum
        if use_weighted_sum:
            self.layer_weights = nn.Parameter(torch.ones(num_layers) / num_layers)
        
        # Multi-scale discriminator heads
        # Different pooling sizes create different temporal resolutions
        self.discriminators = nn.ModuleList([
            DiscriminatorHead(
                self.hidden_size, 
                disc_hidden_dim, 
                kernel_size=5,
                pool_size=1,  # No pooling - finest resolution
                pool_stride=1,
                norm_type=norm_type
            ),
            DiscriminatorHead(
                self.hidden_size, 
                disc_hidden_dim, 
                kernel_size=5,
                pool_size=4,  # 4x downsampling
                pool_stride=2,
                norm_type=norm_type
            ),
            DiscriminatorHead(
                self.hidden_size, 
                disc_hidden_dim, 
                kernel_size=5,
                pool_size=8,  # 8x downsampling
                pool_stride=4,
                norm_type=norm_type
            )
        ])
        
        # Projection for combining features
        self.feature_projection = nn.Linear(self.hidden_size, self.hidden_size)
        
    def extract_features(self, audio):
        """Extract WavLM features from audio.
        
        Args:
            audio: Input audio [B, T] or [B, 1, T]
            
        Returns:
            features: Extracted features [B, C, T']
        """
        # Handle different input shapes
        if audio.dim() == 3:
            audio = audio.squeeze(1)
        
        # Extract features with gradient computation where needed
        outputs = self.wavlm(audio, output_hidden_states=True)
        hidden_states = outputs.hidden_states  # List of [B, T', C]
        
        if self.use_weighted_sum:
            # Weighted sum of all layers
            weights = F.softmax(self.layer_weights, dim=0)
            features = sum(
                w * h for w, h in zip(weights, hidden_states)
            )
        else:
            # Use last 4 layers
            features = torch.stack(hidden_states[-4:], dim=1).mean(dim=1)
        
        # Project features
        features = self.feature_projection(features)
        
        # Transpose for conv layers [B, T', C] -> [B, C, T']
        features = features.transpose(1, 2)
        
        return features
        
    def forward(self, y, y_hat):
        """Forward pass for discrimination.
        
        Args:
            y: Real audio [B, 1, T]
            y_hat: Generated audio [B, 1, T]
            
        Returns:
            y_d_rs: List of real audio discriminator outputs
            y_d_gs: List of generated audio discriminator outputs  
            fmap_rs: List of real audio feature maps
            fmap_gs: List of generated audio feature maps
        """
        # Extract features
        with torch.cuda.amp.autocast(enabled=False):
            y_features = self.extract_features(y.float())
            y_hat_features = self.extract_features(y_hat.float())
        
        # Multi-scale discrimination
        y_d_rs = []
        y_d_gs = []
        fmap_rs = []
        fmap_gs = []
        
        for disc in self.discriminators:
            y_d_r, fmap_r = disc(y_features)
            y_d_g, fmap_g = disc(y_hat_features)
            
            y_d_rs.append(y_d_r)
            y_d_gs.append(y_d_g)
            fmap_rs.append(fmap_r)
            fmap_gs.append(fmap_g)
            
        return y_d_rs, y_d_gs, fmap_rs, fmap_gs


class WavLMMultiPeriodDiscriminator(nn.Module):
    """Combined discriminator using both WavLM and Multi-Period discriminators.
    
    This provides both the perceptual benefits of WavLM and the 
    periodic pattern detection of MPD.
    """
    
    def __init__(
        self,
        use_spectral_norm: bool = False,
        wavlm_model: str = "microsoft/wavlm-base",
        wavlm_weight: float = 0.5,
        **wavlm_kwargs
    ):
        super().__init__()
        
        # Import existing discriminators
        from .models import MultiPeriodDiscriminator
        from .stft_discriminator import MultiResolutionSTFTDiscriminator
        
        # Original discriminators
        self.mpd = MultiPeriodDiscriminator(use_spectral_norm)
        self.mrd = MultiResolutionSTFTDiscriminator()
        
        # WavLM discriminator
        self.wavlm_disc = WavLMDiscriminator(
            pretrained_model=wavlm_model,
            norm_type="spectral" if use_spectral_norm else "weight",
            **wavlm_kwargs
        )
        
        # Weight for balancing WavLM vs traditional discriminators
        self.wavlm_weight = wavlm_weight
        
    def forward(self, y, y_hat):
        """Forward pass combining all discriminators.
        
        Args:
            y: Real audio [B, 1, T]
            y_hat: Generated audio [B, 1, T]
            
        Returns:
            y_d_rs: Combined real audio discriminator outputs
            y_d_gs: Combined generated audio discriminator outputs
            fmap_rs: Combined real audio feature maps
            fmap_gs: Combined generated audio feature maps
        """
        # Multi-Period Discriminator
        mpd_y_d_rs, mpd_y_d_gs, mpd_fmap_rs, mpd_fmap_gs = self.mpd(y, y_hat)
        
        # Multi-Resolution STFT Discriminator  
        mrd_y_d_rs, mrd_y_d_gs, mrd_fmap_rs, mrd_fmap_gs = self.mrd(y, y_hat)
        
        # WavLM Discriminator
        wavlm_y_d_rs, wavlm_y_d_gs, wavlm_fmap_rs, wavlm_fmap_gs = self.wavlm_disc(y, y_hat)
        
        # Combine outputs
        y_d_rs = mpd_y_d_rs + mrd_y_d_rs + wavlm_y_d_rs
        y_d_gs = mpd_y_d_gs + mrd_y_d_gs + wavlm_y_d_gs
        fmap_rs = mpd_fmap_rs + mrd_fmap_rs + wavlm_fmap_rs
        fmap_gs = mpd_fmap_gs + mrd_fmap_gs + wavlm_fmap_gs
        
        return y_d_rs, y_d_gs, fmap_rs, fmap_gs