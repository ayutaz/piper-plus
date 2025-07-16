"""ONNX export utilities for BERT encoder.

This module provides utilities to export BERT embeddings for ONNX inference,
allowing the use of precomputed embeddings during inference to avoid
the need for the full BERT model at runtime.
"""

import json
from pathlib import Path

import torch
from torch import nn
from tqdm import tqdm

from .bert_encoder import JapaneseBERTEncoder


class PrecomputedBERTEncoder(nn.Module):
    """BERT encoder that uses precomputed embeddings for ONNX export.

    This encoder loads precomputed BERT embeddings from a cache file
    and uses them during inference, eliminating the need for the full
    BERT model at runtime.
    """

    def __init__(
        self,
        embedding_cache_path: str,
        hidden_channels: int = 192,
        fallback_embedding: torch.Tensor | None = None
    ):
        super().__init__()

        # Load precomputed embeddings
        self.embedding_cache = torch.load(embedding_cache_path)
        self.hidden_channels = hidden_channels

        # Fallback for unseen texts
        if fallback_embedding is None:
            self.register_buffer(
                "fallback_embedding",
                torch.zeros(1, hidden_channels)
            )
        else:
            self.register_buffer("fallback_embedding", fallback_embedding)

        # Text to index mapping
        self.text_to_idx = {text: idx for idx, text in enumerate(self.embedding_cache.keys())}

        # Convert cache to tensor for efficient lookup
        embeddings_list = list(self.embedding_cache.values())
        if embeddings_list:
            self.register_buffer(
                "embeddings",
                torch.stack(embeddings_list, dim=0)
            )
        else:
            self.register_buffer(
                "embeddings",
                torch.zeros(1, 1, hidden_channels)
            )

    def forward(
        self,
        text_indices: torch.Tensor,
        phoneme_lengths: torch.Tensor
    ) -> torch.Tensor:
        """Look up precomputed embeddings by index.

        Args:
            text_indices: Indices corresponding to texts [B]
            phoneme_lengths: Target phoneme lengths [B]

        Returns:
            aligned_features: Precomputed BERT features [B, T_phoneme, C]
        """
        batch_size = text_indices.size(0)
        max_phoneme_len = phoneme_lengths.max().item()

        aligned_features = []
        for i in range(batch_size):
            idx = text_indices[i].item()
            if 0 <= idx < self.embeddings.size(0):
                features = self.embeddings[idx]
            else:
                # Use fallback for unknown texts
                features = self.fallback_embedding.expand(max_phoneme_len, -1)

            # Ensure correct length
            if features.size(0) < max_phoneme_len:
                padding = torch.zeros(
                    max_phoneme_len - features.size(0),
                    self.hidden_channels,
                    device=features.device
                )
                features = torch.cat([features, padding], dim=0)
            else:
                features = features[:max_phoneme_len]

            aligned_features.append(features)

        return torch.stack(aligned_features, dim=0)


def precompute_bert_embeddings(
    bert_encoder: JapaneseBERTEncoder,
    texts: list[str],
    phoneme_lengths: list[int],
    output_path: str,
    batch_size: int = 32,
    show_progress: bool = True
) -> dict[str, torch.Tensor]:
    """Precompute BERT embeddings for a list of texts.

    Args:
        bert_encoder: Trained BERT encoder
        texts: List of Japanese texts
        phoneme_lengths: Corresponding phoneme lengths
        output_path: Path to save the embedding cache
        batch_size: Batch size for processing
        show_progress: Whether to show progress bar

    Returns:
        Dictionary mapping texts to their embeddings
    """
    bert_encoder.eval()
    embedding_cache = {}

    # Process in batches
    # num_batches = (len(texts) + batch_size - 1) // batch_size  # Not used currently

    iterator = range(0, len(texts), batch_size)
    if show_progress:
        iterator = tqdm(iterator, desc="Precomputing BERT embeddings")

    with torch.no_grad():
        for i in iterator:
            batch_texts = texts[i:i + batch_size]
            batch_lengths = phoneme_lengths[i:i + batch_size]

            # Convert to tensor
            length_tensor = torch.tensor(batch_lengths, device=next(bert_encoder.parameters()).device)

            # Get embeddings
            embeddings = bert_encoder(batch_texts, length_tensor)

            # Store in cache
            for j, text in enumerate(batch_texts):
                embedding_cache[text] = embeddings[j].cpu()

    # Save cache
    torch.save(embedding_cache, output_path)

    # Also save text mapping for easy lookup
    text_mapping = {text: idx for idx, text in enumerate(texts)}
    with open(Path(output_path).with_suffix('.json'), 'w', encoding='utf-8') as f:
        json.dump(text_mapping, f, ensure_ascii=False, indent=2)

    return embedding_cache


def create_onnx_compatible_encoder(
    original_encoder: nn.Module,
    embedding_cache_path: str,
    bert_hidden_channels: int = 192
) -> nn.Module:
    """Create an ONNX-compatible version of the BERT text encoder.

    This replaces the BERT encoder with a precomputed embedding lookup
    that can be exported to ONNX.

    Args:
        original_encoder: Original BERTTextEncoder
        embedding_cache_path: Path to precomputed embeddings
        bert_hidden_channels: Hidden size of BERT embeddings

    Returns:
        ONNX-compatible encoder
    """

    class ONNXTextEncoder(nn.Module):
        def __init__(self, original_encoder, precomputed_bert):
            super().__init__()
            self.original_encoder = original_encoder.original_encoder
            self.precomputed_bert = precomputed_bert
            self.bert_weight = original_encoder.bert_weight

            # Copy projection if it exists
            if hasattr(original_encoder, 'bert_projection'):
                self.bert_projection = original_encoder.bert_projection
            else:
                self.bert_projection = None

        def forward(
            self,
            x: torch.Tensor,
            x_lengths: torch.Tensor,
            text_indices: torch.Tensor | None = None
        ):
            """Forward pass using precomputed embeddings.

            Args:
                x: Phoneme IDs [B, T]
                x_lengths: Phoneme lengths [B]
                text_indices: Indices for text lookup [B]

            Returns:
                Same as original encoder
            """
            # Get original encoding
            x, m_p, logs_p, x_mask = self.original_encoder(x, x_lengths)

            # Add precomputed BERT features if indices provided
            if text_indices is not None and self.bert_weight > 0:
                bert_features = self.precomputed_bert(text_indices, x_lengths)

                # Project if needed
                if self.bert_projection is not None:
                    bert_features = self.bert_projection(bert_features)

                # Transpose to match encoder output shape [B, C, T]
                bert_features = bert_features.transpose(1, 2)

                # Combine with original features
                x = x + self.bert_weight * bert_features * x_mask

            return x, m_p, logs_p, x_mask

    # Create precomputed BERT encoder
    precomputed_bert = PrecomputedBERTEncoder(
        embedding_cache_path,
        hidden_channels=bert_hidden_channels
    )

    # Create ONNX-compatible encoder
    return ONNXTextEncoder(original_encoder, precomputed_bert)


def export_model_with_bert_cache(
    model: nn.Module,
    texts: list[str],
    phoneme_lengths: list[int],
    bert_cache_path: str,
    onnx_path: str,
    opset_version: int = 15,
    **export_kwargs
):
    """Export VITS model with precomputed BERT embeddings.

    Args:
        model: VITS model with BERTTextEncoder
        texts: List of texts to precompute
        phoneme_lengths: Corresponding phoneme lengths
        bert_cache_path: Path to save BERT embedding cache
        onnx_path: Path to save ONNX model
        opset_version: ONNX opset version
        **export_kwargs: Additional arguments for torch.onnx.export
    """
    # First, precompute BERT embeddings
    if hasattr(model.model_g.enc_p, 'bert_encoder'):
        print("Precomputing BERT embeddings...")
        precompute_bert_embeddings(
            model.model_g.enc_p.bert_encoder,
            texts,
            phoneme_lengths,
            bert_cache_path
        )

        # Replace encoder with ONNX-compatible version
        print("Creating ONNX-compatible encoder...")
        model.model_g.enc_p = create_onnx_compatible_encoder(
            model.model_g.enc_p,
            bert_cache_path,
            bert_hidden_channels=model.model_g.hidden_channels
        )

    # Export to ONNX
    print("Exporting to ONNX...")
    # Create dummy inputs
    batch_size = 1
    max_phoneme_len = max(phoneme_lengths)

    dummy_phoneme_ids = torch.randint(0, 100, (batch_size, max_phoneme_len))
    dummy_phoneme_lengths = torch.tensor([max_phoneme_len])
    dummy_scales = torch.tensor([0.667, 1.0, 0.8])

    # Add text indices for BERT lookup
    dummy_text_indices = torch.tensor([0])  # Index of first text

    # Set to eval mode
    model.eval()

    # Export
    torch.onnx.export(
        model,
        (dummy_phoneme_ids, dummy_phoneme_lengths, dummy_scales, None, None, dummy_text_indices),
        onnx_path,
        opset_version=opset_version,
        input_names=['phoneme_ids', 'phoneme_lengths', 'scales', 'speaker_id', 'prosody_ids', 'text_indices'],
        output_names=['audio'],
        dynamic_axes={
            'phoneme_ids': {0: 'batch_size', 1: 'phoneme_length'},
            'phoneme_lengths': {0: 'batch_size'},
            'audio': {0: 'batch_size', 2: 'audio_length'},
        },
        **export_kwargs
    )

    print(f"Model exported to {onnx_path}")
    print(f"BERT embeddings cached at {bert_cache_path}")
    print("Don't forget to include both files for inference!")
