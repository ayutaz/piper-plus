#!/usr/bin/env python3
"""Simple test for augmentation modules without pytest."""

import sys

import torch

sys.path.insert(0, '/data/piper/src/python')

from piper_train.vits.augmentation import (
    AudioAugmentation,
    PhonemeAugmentation,
    SpecAugment,
)


def test_spec_augment():
    """Test SpecAugment."""
    print("Testing SpecAugment...")
    augmenter = SpecAugment()
    spec = torch.randn(80, 100)
    augmented = augmenter(spec)
    assert augmented.shape == spec.shape
    print("✓ SpecAugment works")


def test_audio_augmentation():
    """Test AudioAugmentation."""
    print("Testing AudioAugmentation...")
    augmenter = AudioAugmentation(sample_rate=22050)
    audio = torch.randn(22050)
    augmented = augmenter(audio)
    assert augmented.dim() == 1
    print("✓ AudioAugmentation works")


def test_phoneme_augmentation():
    """Test PhonemeAugmentation."""
    print("Testing PhonemeAugmentation...")
    augmenter = PhonemeAugmentation()
    phoneme_ids = torch.randint(1, 50, (100,))
    augmented, _ = augmenter(phoneme_ids)
    assert augmented.shape == phoneme_ids.shape
    print("✓ PhonemeAugmentation works")


if __name__ == "__main__":
    test_spec_augment()
    test_audio_augmentation()
    test_phoneme_augmentation()
    print("\nAll augmentation tests passed!")
