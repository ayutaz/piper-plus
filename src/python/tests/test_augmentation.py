"""Tests for data augmentation modules."""

import torch
import pytest

from piper_train.vits.augmentation import (
    SpecAugment,
    AudioAugmentation,
    PhonemeAugmentation,
)


class TestSpecAugment:
    """Test SpecAugment augmentation."""

    def test_spec_augment_basic(self):
        """Test basic SpecAugment functionality."""
        augmenter = SpecAugment(
            freq_mask_param=10,
            time_mask_param=20,
            freq_mask_num=1,
            time_mask_num=1,
        )
        
        # Create dummy spectrogram
        spec = torch.randn(80, 100)  # [F, T]
        augmented = augmenter(spec)
        
        assert augmented.shape == spec.shape
        assert not torch.equal(augmented, spec)  # Should be different

    def test_spec_augment_batch(self):
        """Test SpecAugment with batch input."""
        augmenter = SpecAugment()
        
        # Create batch of spectrograms
        spec = torch.randn(4, 80, 100)  # [B, F, T]
        augmented = augmenter(spec)
        
        assert augmented.shape == spec.shape


class TestAudioAugmentation:
    """Test AudioAugmentation."""

    def test_audio_augmentation_basic(self):
        """Test basic audio augmentation."""
        augmenter = AudioAugmentation(
            sample_rate=22050,
            enable_speed_perturb=True,
            enable_pitch_shift=True,
            enable_random_gain=True,
        )
        
        # Create dummy audio
        audio = torch.randn(22050)  # 1 second of audio
        augmented = augmenter(audio)
        
        assert augmented.dim() == 1
        # Length might change due to speed perturbation
        assert augmented.shape[0] > 0

    def test_speed_perturb(self):
        """Test speed perturbation."""
        augmenter = AudioAugmentation(sample_rate=22050)
        audio = torch.randn(22050)
        
        # Test with specific speed factor
        perturbed = augmenter.speed_perturb(audio, 0.9)
        assert perturbed.shape[0] > 0

    def test_pitch_shift(self):
        """Test pitch shifting."""
        augmenter = AudioAugmentation(sample_rate=22050)
        audio = torch.randn(22050)
        
        # Test with specific pitch shift
        shifted = augmenter.pitch_shift(audio, 2)
        assert shifted.shape == audio.shape


class TestPhonemeAugmentation:
    """Test PhonemeAugmentation."""

    def test_phoneme_dropout(self):
        """Test phoneme dropout."""
        augmenter = PhonemeAugmentation(
            phoneme_dropout_prob=0.5,  # High prob for testing
            phoneme_mask_token=0,
        )
        
        # Create dummy phoneme ids
        phoneme_ids = torch.randint(1, 50, (100,))
        augmented, _ = augmenter(phoneme_ids)
        
        assert augmented.shape == phoneme_ids.shape
        # Some tokens should be masked
        assert (augmented == 0).any()

    def test_prosody_dropout(self):
        """Test prosody dropout."""
        augmenter = PhonemeAugmentation(
            prosody_dropout_prob=0.5,
            prosody_mask_token=0,
        )
        
        phoneme_ids = torch.randint(1, 50, (100,))
        prosody_ids = torch.randint(1, 10, (100,))
        
        _, augmented_prosody = augmenter(phoneme_ids, prosody_ids)
        
        assert augmented_prosody is not None
        assert augmented_prosody.shape == prosody_ids.shape
        # Some prosody tokens should be masked
        assert (augmented_prosody == 0).any()