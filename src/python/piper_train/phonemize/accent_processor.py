import re
from dataclasses import dataclass

import numpy as np


@dataclass
class AccentInfo:
    """Container for Japanese accent information."""

    accent_position: int  # Position of accent nucleus (0 = no accent)
    phrase_boundary: int  # Phrase boundary type (0=none, 1=minor, 2=major)
    mora_count: int  # Number of moras in the word
    is_question: bool  # Question intonation marker


class JapaneseAccentProcessor:
    """Enhanced processor for Japanese accent and prosody marks.

    Extends the existing prosody marks with fine-grained accent control
    for improved intonation modeling.
    """

    # Existing prosody marks from japanese.py
    PROSODY_MARKS = {
        "^": "start",
        "$": "end_declarative",
        "?": "end_question",
        "_": "pause",
        "#": "boundary",
        "[": "rising",
        "]": "falling",
    }

    # Extended accent marks for fine control
    ACCENT_MARKS = {
        "↑": "accent_rise",  # Accent nucleus rise
        "↓": "accent_fall",  # Post-accent fall
        "→": "accent_flat",  # Flat intonation
        "⤴": "phrase_rise",  # Phrase-final rise
        "⤵": "phrase_fall",  # Phrase-final fall
        "|": "minor_boundary",  # Minor phrase boundary
        "‖": "major_boundary",  # Major phrase boundary
    }

    # Mora patterns for accent detection
    MORA_PATTERN = re.compile(r"[ァ-ヴー][ャュョゃゅょ]?|[ア-ン][ャュョゃゅょ]?|[a-z]+")

    def __init__(self):
        # Combined mark to ID mapping
        self.mark_to_id = {}
        id_counter = 0

        # Assign IDs to existing prosody marks
        for mark in self.PROSODY_MARKS:
            self.mark_to_id[mark] = id_counter
            id_counter += 1

        # Assign IDs to extended accent marks
        for mark in self.ACCENT_MARKS:
            self.mark_to_id[mark] = id_counter
            id_counter += 1

        # Special tokens
        self.mark_to_id["<PAD>"] = id_counter
        self.mark_to_id["<UNK>"] = id_counter + 1

        # Reverse mapping
        self.id_to_mark = {v: k for k, v in self.mark_to_id.items()}

    def process_text_with_accent(
        self,
        text: str,
        phonemes: list[str],
        accent_dict: dict[str, AccentInfo] | None = None,
    ) -> tuple[list[str], list[int]]:
        """Process text to add detailed accent marks to phonemes.

        Args:
            text: Original Japanese text
            phonemes: List of phonemes from pyopenjtalk
            accent_dict: Optional dictionary of word->accent information

        Returns:
            enhanced_phonemes: Phonemes with accent marks inserted
            prosody_ids: List of prosody/accent mark IDs for F0 predictor
        """
        enhanced_phonemes = []
        prosody_ids = []

        # Parse existing prosody marks from phonemes
        phoneme_idx = 0
        for phoneme in phonemes:
            if phoneme in self.PROSODY_MARKS:
                # Keep existing prosody mark
                enhanced_phonemes.append(phoneme)
                prosody_ids.append(self.mark_to_id[phoneme])
            else:
                # Regular phoneme
                enhanced_phonemes.append(phoneme)
                prosody_ids.append(self.mark_to_id["<PAD>"])  # No prosody

                # Check if we should add accent marks
                if accent_dict and phoneme_idx < len(phonemes) - 1:
                    # Simple heuristic: add accent marks based on position
                    # In practice, this would use the accent_dict
                    if self._should_add_accent_mark(phoneme, phoneme_idx, phonemes):
                        accent_mark = self._get_accent_mark(phoneme_idx, len(phonemes))
                        enhanced_phonemes.append(accent_mark)
                        prosody_ids.append(
                            self.mark_to_id.get(accent_mark, self.mark_to_id["<UNK>"])
                        )

            phoneme_idx += 1

        return enhanced_phonemes, prosody_ids

    def _should_add_accent_mark(
        self, phoneme: str, idx: int, phonemes: list[str]
    ) -> bool:
        """Determine if accent mark should be added after this phoneme."""
        # Simple heuristic - in practice would use linguistic rules
        # Add accent marks at mora boundaries
        if idx > 0 and idx < len(phonemes) - 2:
            # Check if this is a mora boundary
            next_phoneme = phonemes[idx + 1]
            if next_phoneme not in self.PROSODY_MARKS:
                # Simple probability-based insertion
                return np.random.random() < 0.3
        return False

    def _get_accent_mark(self, position: int, total_length: int) -> str:
        """Get appropriate accent mark based on position."""
        relative_pos = position / total_length

        if relative_pos < 0.3:
            return "↑"  # Early accent rise
        elif relative_pos < 0.7:
            return "→"  # Mid-phrase flat
        else:
            return "↓"  # Late accent fall

    def create_accent_embedding_layer(self, embedding_dim: int = 128):
        """Create embedding layer for accent marks."""
        from torch import nn

        num_marks = len(self.mark_to_id)
        embedding = nn.Embedding(
            num_embeddings=num_marks,
            embedding_dim=embedding_dim,
            padding_idx=self.mark_to_id["<PAD>"],
        )

        # Initialize with small values
        nn.init.normal_(embedding.weight, mean=0.0, std=0.02)

        return embedding

    def extract_accent_features(
        self, phonemes: list[str], prosody_ids: list[int]
    ) -> dict[str, float]:
        """Extract statistical features from accent patterns."""
        features = {
            "accent_density": 0.0,
            "rising_ratio": 0.0,
            "falling_ratio": 0.0,
            "boundary_count": 0,
            "phrase_length_mean": 0.0,
            "phrase_length_std": 0.0,
        }

        if not prosody_ids:
            return features

        # Count accent types
        accent_counts = {}
        for pid in prosody_ids:
            if pid != self.mark_to_id["<PAD>"]:
                mark = self.id_to_mark.get(pid, "<UNK>")
                accent_counts[mark] = accent_counts.get(mark, 0) + 1

        total_marks = sum(accent_counts.values())
        if total_marks > 0:
            features["accent_density"] = total_marks / len(prosody_ids)

            # Ratios of different accent types
            rising_marks = ["↑", "[", "⤴"]
            falling_marks = ["↓", "]", "⤵"]

            rising_count = sum(accent_counts.get(m, 0) for m in rising_marks)
            falling_count = sum(accent_counts.get(m, 0) for m in falling_marks)

            features["rising_ratio"] = rising_count / total_marks
            features["falling_ratio"] = falling_count / total_marks

            # Boundary statistics
            boundary_marks = ["#", "|", "‖"]
            features["boundary_count"] = sum(
                accent_counts.get(m, 0) for m in boundary_marks
            )

        return features

    def extract_prosody_ids(self, phonemes: list[str]) -> list[int]:
        """Extract prosody IDs from a list of phonemes.

        Args:
            phonemes: List of phonemes that may contain prosody marks

        Returns:
            List of prosody IDs corresponding to each phoneme
        """
        prosody_ids = []

        for phoneme in phonemes:
            if phoneme in self.PROSODY_MARKS or phoneme in self.ACCENT_MARKS:
                # This is a prosody/accent mark
                prosody_ids.append(
                    self.mark_to_id.get(phoneme, self.mark_to_id["<UNK>"])
                )
            else:
                # Regular phoneme - no prosody
                prosody_ids.append(self.mark_to_id["<PAD>"])

        return prosody_ids
