"""Utilities for inference with accent and prosody control."""

import logging

from torch import LongTensor

from .phonemize.accent_processor import JapaneseAccentProcessor
from .phonemize.japanese import phonemize_japanese

_LOGGER = logging.getLogger("piper_train.inference_utils")


def prepare_text_for_inference(
    text: str,
    phoneme_id_map: dict[str, list[int]],
    language: str = "ja_JP",
    use_accent_processor: bool = True,
) -> tuple[LongTensor, LongTensor | None]:
    """Prepare text for inference with optional prosody processing.

    Args:
        text: Input text
        phoneme_id_map: Mapping from phonemes to IDs
        language: Language code (currently only ja_JP supports accent processing)
        use_accent_processor: Whether to use accent processor

    Returns:
        phoneme_ids: Tensor of phoneme IDs
        prosody_ids: Tensor of prosody IDs (if accent processor is used)
    """
    if language.startswith("ja") and use_accent_processor:
        # Japanese with accent processing
        base_phonemes = phonemize_japanese(text)

        accent_processor = JapaneseAccentProcessor()
        enhanced_phonemes, prosody_ids_list = accent_processor.process_text_with_accent(
            text,
            base_phonemes,
        )

        # Convert phonemes to IDs
        phoneme_ids_list = []
        for phoneme in enhanced_phonemes:
            if phoneme in phoneme_id_map:
                phoneme_ids_list.extend(phoneme_id_map[phoneme])
            else:
                _LOGGER.warning(f"Unknown phoneme: {phoneme}")
                # Use a default ID or skip

        phoneme_ids = LongTensor(phoneme_ids_list)
        prosody_ids = LongTensor(prosody_ids_list)

        return phoneme_ids, prosody_ids

    # Other languages or no accent processing
    # This would need to be implemented based on the language
    # For now, return empty prosody IDs
    _LOGGER.warning(f"Accent processing not implemented for language: {language}")

    # Placeholder - should use appropriate phonemizer
    phoneme_ids = LongTensor([0])  # Dummy
    prosody_ids = None

    return phoneme_ids, prosody_ids


def apply_accent_modifications(
    text: str,
    accent_strength: float = 1.0,
    question_intonation: bool = None,
) -> str:
    """Apply accent modifications to Japanese text.

    Args:
        text: Input text
        accent_strength: Strength of accent (0.0-2.0)
        question_intonation: Force question intonation (None = auto-detect)

    Returns:
        Modified text with accent markers
    """
    if question_intonation is None:
        # Auto-detect question
        question_intonation = text.rstrip().endswith("？") or text.rstrip().endswith(
            "?",
        )

    # Add accent markers based on strength
    if accent_strength > 1.5:
        # Strong accent
        text = text.replace("は", "は↑").replace("が", "が↑")
        text = text.replace("です", "で↓す")
        text = text.replace("ます", "ま↓す")
    elif accent_strength > 0.5:
        # Normal accent
        text = text.replace("です", "です→")
        text = text.replace("ます", "ます→")

    # Add question intonation
    if question_intonation:
        if text.rstrip().endswith("か"):
            text = text[:-1] + "⤴か"
        elif text.rstrip().endswith("？"):
            text = text[:-1] + "⤴？"

    return text


class AccentController:
    """Controller for fine-grained accent and prosody control during inference."""

    def __init__(self, phoneme_id_map: dict[str, list[int]]):
        self.phoneme_id_map = phoneme_id_map
        self.accent_processor = JapaneseAccentProcessor()

    def process_with_style(
        self,
        text: str,
        style: str = "neutral",
        emotion: str = "neutral",
    ) -> tuple[LongTensor, LongTensor]:
        """Process text with specific speaking style and emotion.

        Args:
            text: Input text
            style: Speaking style (neutral, formal, casual, emphatic)
            emotion: Emotion (neutral, happy, sad, angry, surprised)

        Returns:
            phoneme_ids: Tensor of phoneme IDs
            prosody_ids: Tensor of prosody IDs with style/emotion encoding
        """
        # Apply style-specific modifications
        if style == "formal":
            text = apply_accent_modifications(text, accent_strength=0.8)
        elif style == "casual":
            text = apply_accent_modifications(text, accent_strength=1.2)
        elif style == "emphatic":
            text = apply_accent_modifications(text, accent_strength=2.0)

        # Get base phonemes
        base_phonemes = phonemize_japanese(text)

        # Process with accent
        enhanced_phonemes, prosody_ids_list = (
            self.accent_processor.process_text_with_accent(text, base_phonemes)
        )

        # Modify prosody IDs based on emotion
        if emotion != "neutral":
            prosody_ids_list = self._apply_emotion_to_prosody(prosody_ids_list, emotion)

        # Convert to tensors
        phoneme_ids_list = []
        for phoneme in enhanced_phonemes:
            if phoneme in self.phoneme_id_map:
                phoneme_ids_list.extend(self.phoneme_id_map[phoneme])

        return LongTensor(phoneme_ids_list), LongTensor(prosody_ids_list)

    def _apply_emotion_to_prosody(
        self,
        prosody_ids: list[int],
        emotion: str,
    ) -> list[int]:
        """Apply emotion-specific modifications to prosody IDs."""
        # This is a simplified example - in practice would use more sophisticated mapping
        emotion_offset = {
            "happy": 1,
            "sad": -1,
            "angry": 2,
            "surprised": 3,
        }.get(emotion, 0)

        # Apply offset to non-padding prosody marks
        modified_ids = []
        for pid in prosody_ids:
            if pid != self.accent_processor.mark_to_id["<PAD>"]:
                # Apply emotion offset while keeping in valid range
                modified_pid = max(
                    0,
                    min(
                        pid + emotion_offset,
                        len(self.accent_processor.mark_to_id) - 1,
                    ),
                )
                modified_ids.append(modified_pid)
            else:
                modified_ids.append(pid)

        return modified_ids
