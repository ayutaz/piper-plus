"""Japanese BERT encoder for enhanced text understanding and prosody generation.

This module integrates Japanese BERT models to provide contextual embeddings
that improve prosody and accent prediction for Japanese TTS.
"""


import torch
from torch import nn

try:
    from transformers import AutoModel, AutoTokenizer
    BERT_AVAILABLE = True
except ImportError:
    BERT_AVAILABLE = False
    print("Warning: transformers library not found. BERT encoder will not be available.")


class PhonemeAligner(nn.Module):
    """Aligns BERT token embeddings to phoneme sequences.

    This module handles the non-trivial alignment between BERT subword tokens
    and phoneme sequences, which is crucial for Japanese where one character
    can map to multiple phonemes.
    """

    def __init__(
        self,
        hidden_channels: int,
        kernel_size: int = 3,
        n_layers: int = 2,
        dropout: float = 0.1
    ):
        super().__init__()

        # Attention-based alignment
        self.attention = nn.MultiheadAttention(
            hidden_channels,
            num_heads=4,
            dropout=dropout,
            batch_first=True
        )

        # Refinement layers
        self.refine_layers = nn.ModuleList()
        for _ in range(n_layers):
            self.refine_layers.append(
                nn.Sequential(
                    nn.Conv1d(
                        hidden_channels,
                        hidden_channels,
                        kernel_size,
                        padding=kernel_size // 2
                    ),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                    nn.LayerNorm(hidden_channels)
                )
            )

        # Duration predictor for alignment
        self.duration_predictor = nn.Sequential(
            nn.Linear(hidden_channels, hidden_channels // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels // 2, 1),
            nn.Softplus()  # Ensure positive durations
        )

    def forward(
        self,
        bert_features: torch.Tensor,
        phoneme_lengths: torch.Tensor,
        bert_mask: torch.Tensor | None = None
    ) -> torch.Tensor:
        """Align BERT features to phoneme sequence length.

        Args:
            bert_features: BERT token features [B, T_bert, C]
            phoneme_lengths: Target phoneme sequence lengths [B]
            bert_mask: Mask for valid BERT tokens [B, T_bert]

        Returns:
            aligned_features: Features aligned to phoneme sequences [B, T_phoneme, C]
        """
        batch_size = bert_features.size(0)
        max_phoneme_len = phoneme_lengths.max().item()
        device = bert_features.device

        # Predict durations for each BERT token
        durations = self.duration_predictor(bert_features).squeeze(-1)  # [B, T_bert]

        if bert_mask is not None:
            durations = durations * bert_mask.float()

        # Normalize durations to match target phoneme lengths
        duration_sums = durations.sum(dim=1, keepdim=True)  # [B, 1]
        duration_sums = torch.clamp(duration_sums, min=1e-6)

        normalized_durations = durations * (phoneme_lengths.float().unsqueeze(1) / duration_sums)
        rounded_durations = torch.round(normalized_durations).long()

        # Adjust for rounding errors
        duration_diffs = phoneme_lengths - rounded_durations.sum(dim=1)
        for i in range(batch_size):
            if duration_diffs[i] != 0:
                # Add/subtract from the longest duration
                max_dur_idx = rounded_durations[i].argmax()
                rounded_durations[i, max_dur_idx] += duration_diffs[i]

        # Expand features according to durations
        aligned_features = []
        for i in range(batch_size):
            expanded = []
            for j, dur in enumerate(rounded_durations[i]):
                if dur > 0:
                    expanded.append(
                        bert_features[i, j].unsqueeze(0).expand(dur, -1)
                    )
            if expanded:
                expanded = torch.cat(expanded, dim=0)  # [T_phoneme, C]
                # Pad or truncate to max_phoneme_len
                if expanded.size(0) < max_phoneme_len:
                    padding = torch.zeros(
                        max_phoneme_len - expanded.size(0),
                        expanded.size(1),
                        device=device
                    )
                    expanded = torch.cat([expanded, padding], dim=0)
                else:
                    expanded = expanded[:max_phoneme_len]
                aligned_features.append(expanded)
            else:
                # Empty case
                aligned_features.append(
                    torch.zeros(max_phoneme_len, bert_features.size(-1), device=device)
                )

        aligned_features = torch.stack(aligned_features, dim=0)  # [B, T_phoneme, C]

        # Refine aligned features
        aligned_features = aligned_features.transpose(1, 2)  # [B, C, T_phoneme]
        for layer in self.refine_layers:
            aligned_features = layer(aligned_features) + aligned_features
        aligned_features = aligned_features.transpose(1, 2)  # [B, T_phoneme, C]

        return aligned_features


class JapaneseBERTEncoder(nn.Module):
    """Japanese BERT encoder for contextual text understanding.

    This encoder uses pretrained Japanese BERT models to extract
    rich contextual features that improve prosody generation.
    """

    def __init__(
        self,
        model_name: str = "cl-tohoku/bert-base-japanese-v3",
        hidden_channels: int = 192,
        freeze_layers: int = 8,
        dropout: float = 0.1,
        use_cls_token: bool = True,
        aggregate_method: str = "attention",  # "attention", "mean", "max"
        cache_dir: str | None = None
    ):
        super().__init__()

        if not BERT_AVAILABLE:
            raise ImportError(
                "transformers library is required for BERT encoder. "
                "Please install it with: pip install transformers"
            )

        # Load pretrained model and tokenizer
        self.model_name = model_name
        self.bert = AutoModel.from_pretrained(model_name, cache_dir=cache_dir)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=cache_dir)

        self.bert_hidden_size = self.bert.config.hidden_size
        self.hidden_channels = hidden_channels
        self.use_cls_token = use_cls_token
        self.aggregate_method = aggregate_method

        # Freeze lower layers
        if freeze_layers > 0:
            # Freeze embeddings
            for param in self.bert.embeddings.parameters():
                param.requires_grad = False

            # Freeze encoder layers
            num_layers = len(self.bert.encoder.layer)
            freeze_layers = min(freeze_layers, num_layers)
            for i in range(freeze_layers):
                for param in self.bert.encoder.layer[i].parameters():
                    param.requires_grad = False

        # Projection layers
        self.feature_projection = nn.Sequential(
            nn.Linear(self.bert_hidden_size, hidden_channels * 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_channels * 2, hidden_channels),
            nn.LayerNorm(hidden_channels)
        )

        # CLS token projection (if used)
        if use_cls_token:
            self.cls_projection = nn.Sequential(
                nn.Linear(self.bert_hidden_size, hidden_channels),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(hidden_channels, hidden_channels),
                nn.LayerNorm(hidden_channels)
            )

        # Attention aggregation (if used)
        if aggregate_method == "attention":
            self.attention_weights = nn.Sequential(
                nn.Linear(hidden_channels, 1),
                nn.Softmax(dim=1)
            )

        # Phoneme aligner
        self.aligner = PhonemeAligner(hidden_channels, dropout=dropout)

        # Cache for ONNX export
        self.use_cache = False
        self.cache: dict[str, torch.Tensor] = {}

    def enable_cache(self):
        """Enable caching for ONNX export."""
        self.use_cache = True
        self.cache.clear()

    def disable_cache(self):
        """Disable caching."""
        self.use_cache = False
        self.cache.clear()

    def save_cache(self, path: str):
        """Save cached embeddings to file."""
        torch.save(self.cache, path)

    def load_cache(self, path: str):
        """Load cached embeddings from file."""
        self.cache = torch.load(path)
        self.use_cache = True

    def tokenize_texts(self, texts: list[str]) -> dict[str, torch.Tensor]:
        """Tokenize Japanese texts for BERT input.

        Args:
            texts: List of Japanese text strings

        Returns:
            Dictionary with input_ids, attention_mask, etc.
        """
        # Tokenize with padding and truncation
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        )

        return encoded

    def forward(
        self,
        texts: list[str],
        phoneme_lengths: torch.Tensor,
        cache_key: str | None = None
    ) -> torch.Tensor:
        """Extract BERT features aligned to phoneme sequences.

        Args:
            texts: List of Japanese text strings
            phoneme_lengths: Length of phoneme sequences [B]
            cache_key: Optional key for caching (useful for ONNX)

        Returns:
            aligned_features: BERT features aligned to phonemes [B, T_phoneme, C]
        """
        # Check cache first
        if self.use_cache and cache_key and cache_key in self.cache:
            return self.cache[cache_key]

        # Tokenize texts
        device = next(self.parameters()).device
        inputs = self.tokenize_texts(texts)
        inputs = {k: v.to(device) for k, v in inputs.items()}

        # Get BERT outputs
        with torch.cuda.amp.autocast(enabled=False):
            outputs = self.bert(**inputs, output_hidden_states=True)

        # Extract features
        if self.aggregate_method == "last":
            # Use last hidden state
            bert_features = outputs.last_hidden_state
        else:
            # Use all hidden states
            hidden_states = outputs.hidden_states[1:]  # Exclude embedding layer
            bert_features = torch.stack(hidden_states, dim=1).mean(dim=1)

        # Project features
        bert_features = self.feature_projection(bert_features)

        # Handle CLS token
        if self.use_cls_token:
            cls_features = self.cls_projection(outputs.pooler_output)
            # Add CLS features as global context
            bert_features = bert_features + cls_features.unsqueeze(1)

        # Apply attention aggregation if specified
        if self.aggregate_method == "attention":
            attn_weights = self.attention_weights(bert_features)
            context = (bert_features * attn_weights).sum(dim=1, keepdim=True)
            bert_features = bert_features + context

        # Align to phoneme sequences
        aligned_features = self.aligner(
            bert_features,
            phoneme_lengths,
            inputs.get("attention_mask")
        )

        # Cache if enabled
        if self.use_cache and cache_key:
            self.cache[cache_key] = aligned_features.detach()

        return aligned_features


class BERTTextEncoder(nn.Module):
    """Wrapper to integrate BERT encoder with VITS text encoder.

    This module combines BERT contextual features with the original
    phoneme embeddings for enhanced text encoding.
    """

    def __init__(
        self,
        original_encoder: nn.Module,
        bert_model_name: str = "cl-tohoku/bert-base-japanese-v3",
        bert_hidden_channels: int = 192,
        bert_weight: float = 0.3,
        **bert_kwargs
    ):
        super().__init__()

        self.original_encoder = original_encoder
        self.bert_encoder = JapaneseBERTEncoder(
            model_name=bert_model_name,
            hidden_channels=bert_hidden_channels,
            **bert_kwargs
        )
        self.bert_weight = bert_weight

        # Projection to match dimensions if needed
        if hasattr(original_encoder, 'hidden_channels'):
            orig_hidden = original_encoder.hidden_channels
            if bert_hidden_channels != orig_hidden:
                self.bert_projection = nn.Linear(bert_hidden_channels, orig_hidden)
            else:
                self.bert_projection = None
        else:
            self.bert_projection = None

    def forward(
        self,
        x: torch.Tensor,
        x_lengths: torch.Tensor,
        texts: list[str] | None = None,
        g: torch.Tensor | None = None
    ):
        """Forward pass combining BERT and original encodings.

        Args:
            x: Phoneme IDs [B, T]
            x_lengths: Phoneme lengths [B]
            texts: Original Japanese texts (required for BERT)
            g: Global conditioning (e.g., speaker embedding)

        Returns:
            Same as original encoder output, but with BERT features integrated
        """
        # Get original encoding
        if g is not None:
            x, m_p, logs_p, x_mask = self.original_encoder(x, x_lengths, g)
        else:
            x, m_p, logs_p, x_mask = self.original_encoder(x, x_lengths)

        # Add BERT features if texts are provided
        if texts is not None and self.bert_weight > 0:
            bert_features = self.bert_encoder(texts, x_lengths)

            # Project if needed
            if self.bert_projection is not None:
                bert_features = self.bert_projection(bert_features)

            # Transpose to match encoder output shape [B, C, T]
            bert_features = bert_features.transpose(1, 2)

            # Combine with original features
            x = x + self.bert_weight * bert_features * x_mask

        return x, m_p, logs_p, x_mask
