"""Type definitions for Japanese phonemization.

This module defines types used in OpenJTalk/jpreprocess NJD feature processing.

Original source:
- kabosu-core (https://github.com/q9uri/kabosu-core)
- jpreprocess (https://github.com/jpreprocess/jpreprocess)

License: MIT
"""

from typing import TypedDict


class NjdObject(TypedDict):
    """Represents an NJD (Nihongo no Keitai-so Kaiseki) feature object.

    This is the data structure used by OpenJTalk and jpreprocess for
    morphological analysis and prosody information of Japanese text.

    Attributes:
        string: Surface form of the word
        pos: Part of speech (品詞)
        pos_group1: POS group level 1
        pos_group2: POS group level 2
        pos_group3: POS group level 3
        ctype: Conjugation type (活用型)
        cform: Conjugation form (活用形)
        orig: Original form of the word
        read: Reading in katakana
        pron: Pronunciation in katakana
        acc: Accent nucleus position (0 = flat/heiban)
        mora_size: Number of morae
        chain_rule: Chaining rule
        chain_flag: Accent phrase boundary flag (0 = boundary, -1 = chain)
    """

    string: str
    pos: str
    pos_group1: str
    pos_group2: str
    pos_group3: str
    ctype: str
    cform: str
    orig: str
    read: str
    pron: str
    acc: int
    mora_size: int
    chain_rule: str
    chain_flag: int


__all__ = ["NjdObject"]
