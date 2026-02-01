"""Abstract base class and common types for language phonemizers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProsodyInfo:
    """共通prosody情報 (全言語共通).

    Attributes
    ----------
    a1 : int
        Language-dependent prosody dimension 1.
        Japanese: relative position from accent nucleus.
        English: fixed at 0.
    a2 : int
        Language-dependent prosody dimension 2.
        Japanese: mora position in accent phrase (1-based).
        English: stress level (0=none, 1=secondary, 2=primary).
    a3 : int
        Language-dependent prosody dimension 3.
        Japanese: total morae in accent phrase.
        English: number of phonemes in the word.
    """

    a1: int
    a2: int
    a3: int


class Phonemizer(ABC):
    """言語phonemizerの抽象基底クラス."""

    @abstractmethod
    def phonemize(self, text: str) -> list[str]:
        """テキスト→音素リスト."""

    @abstractmethod
    def phonemize_with_prosody(
        self, text: str
    ) -> tuple[list[str], list[ProsodyInfo | None]]:
        """テキスト→(音素リスト, prosody情報リスト)."""

    @abstractmethod
    def get_phoneme_id_map(self) -> dict[str, list[int]] | None:
        """言語固有のphoneme_id_mapを返す。Noneならconfig由来のmapを使用."""

    def post_process_ids(
        self,
        phoneme_ids: list[int],
        prosody_features: list[dict | None],
        phoneme_id_map: dict[str, list[int]],
    ) -> tuple[list[int], list[dict | None]]:
        """BOS/EOS/パディング等の後処理。デフォルトはno-op."""
        return phoneme_ids, prosody_features
