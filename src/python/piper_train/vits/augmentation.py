"""Data augmentation for VITS training."""

import random

import torch
import torchaudio


class SpecAugment:
    """SpecAugment: A Simple Data Augmentation Method for ASR.

    Reference: https://arxiv.org/abs/1904.08779
    """

    def __init__(
        self,
        freq_mask_param: int = 27,
        time_mask_param: int = 100,
        freq_mask_num: int = 2,
        time_mask_num: int = 2,
        replace_with_zero: bool = False,
    ):
        """Initialize SpecAugment.

        Args:
            freq_mask_param: Maximum frequency mask length
            time_mask_param: Maximum time mask length
            freq_mask_num: Number of frequency masks
            time_mask_num: Number of time masks
            replace_with_zero: If True, replace with zero; otherwise use mean
        """
        self.freq_mask_param = freq_mask_param
        self.time_mask_param = time_mask_param
        self.freq_mask_num = freq_mask_num
        self.time_mask_num = time_mask_num
        self.replace_with_zero = replace_with_zero

    def __call__(self, spec: torch.Tensor) -> torch.Tensor:
        """Apply SpecAugment to spectrogram.

        Args:
            spec: Spectrogram tensor [B, F, T] or [F, T]

        Returns:
            Augmented spectrogram
        """
        if spec.dim() == 2:
            spec = spec.unsqueeze(0)

        batch_size, n_freq, n_time = spec.shape
        spec_aug = spec.clone()

        # Get replacement value
        if self.replace_with_zero:
            fill_value = 0.0
        else:
            fill_value = spec_aug.mean()

        # Apply frequency masks
        for _ in range(self.freq_mask_num):
            f = random.randint(0, min(self.freq_mask_param, n_freq))
            f0 = random.randint(0, n_freq - f)
            spec_aug[:, f0 : f0 + f, :] = fill_value

        # Apply time masks
        for _ in range(self.time_mask_num):
            t = random.randint(0, min(self.time_mask_param, n_time))
            t0 = random.randint(0, n_time - t)
            spec_aug[:, :, t0 : t0 + t] = fill_value

        return spec_aug.squeeze(0) if batch_size == 1 else spec_aug


class AudioAugmentation:
    """Audio-level augmentation for TTS training."""

    def __init__(
        self,
        sample_rate: int = 22050,
        speed_perturb_range: tuple[float, float] = (0.9, 1.1),
        pitch_shift_range: tuple[int, int] = (-2, 2),
        enable_speed_perturb: bool = True,
        enable_pitch_shift: bool = True,
        enable_random_gain: bool = True,
        gain_range: tuple[float, float] = (0.8, 1.2),
    ):
        """Initialize audio augmentation.

        Args:
            sample_rate: Audio sample rate
            speed_perturb_range: Range for speed perturbation factors
            pitch_shift_range: Range for pitch shift in semitones
            enable_speed_perturb: Enable speed perturbation
            enable_pitch_shift: Enable pitch shifting
            enable_random_gain: Enable random gain adjustment
            gain_range: Range for gain adjustment
        """
        self.sample_rate = sample_rate
        self.speed_perturb_range = speed_perturb_range
        self.pitch_shift_range = pitch_shift_range
        self.enable_speed_perturb = enable_speed_perturb
        self.enable_pitch_shift = enable_pitch_shift
        self.enable_random_gain = enable_random_gain
        self.gain_range = gain_range

    def speed_perturb(self, audio: torch.Tensor, factor: float) -> torch.Tensor:
        """Apply speed perturbation to audio.

        Args:
            audio: Audio tensor [T] or [1, T]
            factor: Speed factor (e.g., 0.9 = 90% speed)

        Returns:
            Speed-perturbed audio
        """
        if audio.dim() == 1:
            audio = audio.unsqueeze(0)

        # Resample to achieve speed change
        orig_freq = self.sample_rate
        new_freq = int(self.sample_rate / factor)

        resampler = torchaudio.transforms.Resample(orig_freq, new_freq)
        audio_resampled = resampler(audio)

        # Resample back to original sample rate
        resampler_back = torchaudio.transforms.Resample(new_freq, orig_freq)
        audio_final = resampler_back(audio_resampled)

        return audio_final.squeeze(0)

    def pitch_shift(self, audio: torch.Tensor, n_steps: int) -> torch.Tensor:
        """Apply pitch shifting to audio.

        Args:
            audio: Audio tensor [T] or [1, T]
            n_steps: Number of semitones to shift

        Returns:
            Pitch-shifted audio
        """
        if n_steps == 0:
            return audio

        if audio.dim() == 1:
            audio = audio.unsqueeze(0)

        # Use torchaudio's pitch shift
        pitch_shift = torchaudio.transforms.PitchShift(
            self.sample_rate,
            n_steps,
        )
        audio_shifted = pitch_shift(audio)

        return audio_shifted.squeeze(0)

    def random_gain(self, audio: torch.Tensor, gain: float) -> torch.Tensor:
        """Apply random gain to audio.

        Args:
            audio: Audio tensor
            gain: Gain factor

        Returns:
            Gain-adjusted audio
        """
        return audio * gain

    def __call__(self, audio: torch.Tensor) -> torch.Tensor:
        """Apply random augmentation to audio.

        Args:
            audio: Audio tensor [T] or [1, T]

        Returns:
            Augmented audio
        """
        # Speed perturbation
        if self.enable_speed_perturb and random.random() < 0.5:
            speed_factor = random.uniform(*self.speed_perturb_range)
            audio = self.speed_perturb(audio, speed_factor)

        # Pitch shifting
        if self.enable_pitch_shift and random.random() < 0.3:
            n_steps = random.randint(*self.pitch_shift_range)
            audio = self.pitch_shift(audio, n_steps)

        # Random gain
        if self.enable_random_gain and random.random() < 0.5:
            gain = random.uniform(*self.gain_range)
            audio = self.random_gain(audio, gain)

        return audio


class PhonemeAugmentation:
    """Phoneme-level augmentation for robustness."""

    def __init__(
        self,
        phoneme_dropout_prob: float = 0.1,
        phoneme_mask_token: int = 0,  # Padding token
        prosody_dropout_prob: float = 0.05,
        prosody_mask_token: int = 0,
    ):
        """Initialize phoneme augmentation.

        Args:
            phoneme_dropout_prob: Probability of dropping a phoneme
            phoneme_mask_token: Token ID to use for masking
            prosody_dropout_prob: Probability of dropping prosody marks
            prosody_mask_token: Token ID for prosody masking
        """
        self.phoneme_dropout_prob = phoneme_dropout_prob
        self.phoneme_mask_token = phoneme_mask_token
        self.prosody_dropout_prob = prosody_dropout_prob
        self.prosody_mask_token = prosody_mask_token

    def __call__(
        self,
        phoneme_ids: torch.Tensor,
        prosody_ids: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        """Apply phoneme augmentation.

        Args:
            phoneme_ids: Phoneme ID tensor [B, T] or [T]
            prosody_ids: Optional prosody ID tensor

        Returns:
            Augmented phoneme_ids and prosody_ids
        """
        # Phoneme dropout
        if self.phoneme_dropout_prob > 0:
            dropout_mask = (
                torch.rand_like(phoneme_ids.float()) < self.phoneme_dropout_prob
            )
            phoneme_ids = phoneme_ids.masked_fill(dropout_mask, self.phoneme_mask_token)

        # Prosody dropout
        if prosody_ids is not None and self.prosody_dropout_prob > 0:
            dropout_mask = (
                torch.rand_like(prosody_ids.float()) < self.prosody_dropout_prob
            )
            prosody_ids = prosody_ids.masked_fill(dropout_mask, self.prosody_mask_token)

        return phoneme_ids, prosody_ids
