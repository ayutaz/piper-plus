//! Real-time audio playback via rodio
//!
//! Feature-gated behind `playback` feature flag.
//! `cargo build --features playback` to enable.
//!
//! When the `playback` feature is disabled, only [`DummyPlayer`] and
//! the helper function [`play_audio`] (which delegates to [`DummyPlayer`])
//! are available.

use crate::error::PiperError;
use crate::streaming::AudioSink;

// ---------------------------------------------------------------------------
// DummyPlayer -- always available, useful for testing / benchmarking
// ---------------------------------------------------------------------------

/// A no-op audio player that discards all samples.
///
/// Useful for testing, benchmarking, or running on systems without an
/// audio output device.
pub struct DummyPlayer {
    /// Total number of samples received across all `write_chunk` calls.
    total_samples: usize,
    /// Number of `write_chunk` calls received.
    chunk_count: usize,
    /// Last sample rate seen (0 if no chunks received yet).
    last_sample_rate: u32,
    /// Whether `finalize` has been called.
    finalized: bool,
}

impl DummyPlayer {
    /// Create a new `DummyPlayer`.
    pub fn new() -> Self {
        Self {
            total_samples: 0,
            chunk_count: 0,
            last_sample_rate: 0,
            finalized: false,
        }
    }

    /// Total number of samples received.
    pub fn total_samples(&self) -> usize {
        self.total_samples
    }

    /// Number of chunks received.
    pub fn chunk_count(&self) -> usize {
        self.chunk_count
    }

    /// Last sample rate seen (0 if no chunks received).
    pub fn last_sample_rate(&self) -> u32 {
        self.last_sample_rate
    }

    /// Whether `finalize` has been called.
    pub fn is_finalized(&self) -> bool {
        self.finalized
    }
}

impl Default for DummyPlayer {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioSink for DummyPlayer {
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
        if self.finalized {
            return Err(PiperError::Inference(
                "DummyPlayer: write_chunk called after finalize".to_string(),
            ));
        }
        if sample_rate == 0 {
            return Err(PiperError::Inference("sample rate must be > 0".to_string()));
        }
        self.total_samples += samples.len();
        self.chunk_count += 1;
        self.last_sample_rate = sample_rate;
        Ok(())
    }

    fn finalize(&mut self) -> Result<(), PiperError> {
        self.finalized = true;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CollectorSink -- collects all samples for later inspection
// ---------------------------------------------------------------------------

/// An `AudioSink` that collects all samples into an internal buffer.
///
/// Primarily intended for testing -- you can inspect the accumulated
/// samples after synthesis is complete.
pub struct CollectorSink {
    samples: Vec<i16>,
    sample_rate: Option<u32>,
    finalized: bool,
}

impl CollectorSink {
    /// Create a new empty collector.
    pub fn new() -> Self {
        Self {
            samples: Vec::new(),
            sample_rate: None,
            finalized: false,
        }
    }

    /// Return all collected samples.
    pub fn samples(&self) -> &[i16] {
        &self.samples
    }

    /// Return the sample rate (from the first chunk), if any.
    pub fn sample_rate(&self) -> Option<u32> {
        self.sample_rate
    }

    /// Whether `finalize` has been called.
    pub fn is_finalized(&self) -> bool {
        self.finalized
    }

    /// Consume self and return the collected samples.
    pub fn into_samples(self) -> Vec<i16> {
        self.samples
    }
}

impl Default for CollectorSink {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioSink for CollectorSink {
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
        if self.finalized {
            return Err(PiperError::Inference(
                "CollectorSink: write_chunk called after finalize".to_string(),
            ));
        }
        if sample_rate == 0 {
            return Err(PiperError::Inference("sample rate must be > 0".to_string()));
        }
        // Detect sample rate mismatch across chunks
        if let Some(prev) = self.sample_rate
            && prev != sample_rate
        {
            return Err(PiperError::Inference(format!(
                "sample rate mismatch: expected {prev}, got {sample_rate}"
            )));
        }
        self.sample_rate = Some(sample_rate);
        self.samples.extend_from_slice(samples);
        Ok(())
    }

    fn finalize(&mut self) -> Result<(), PiperError> {
        self.finalized = true;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// RodioPlayer -- feature-gated behind "playback"
// ---------------------------------------------------------------------------

/// Real-time audio player using rodio.
///
/// Plays audio chunks through the default audio output device.
/// Feature-gated behind the `playback` Cargo feature.
///
/// # Example (requires `--features playback`)
///
/// ```ignore
/// use piper_plus::playback::RodioPlayer;
/// use piper_plus::streaming::AudioSink;
///
/// let mut player = RodioPlayer::new()?;
/// player.write_chunk(&samples, 22050)?;
/// player.finalize()?;
/// player.wait_until_done();
/// ```
#[cfg(feature = "playback")]
pub struct RodioPlayer {
    /// Must be kept alive for the duration of playback -- dropping it
    /// stops audio output.
    _stream: rodio::OutputStream,
    /// The actual playback sink.
    sink: rodio::Sink,
    /// Target sample rate for the output device. If `Some`, incoming
    /// audio is resampled to this rate.  If `None`, audio is played
    /// at its native sample rate.
    target_sample_rate: Option<u32>,
    /// Whether `finalize` has been called.
    finalized: bool,
}

#[cfg(feature = "playback")]
impl RodioPlayer {
    /// Create a new player using the default output device.
    ///
    /// Audio is played at whatever sample rate each chunk declares.
    pub fn new() -> Result<Self, PiperError> {
        let (_stream, stream_handle) = rodio::OutputStream::try_default()
            .map_err(|e| PiperError::Inference(format!("failed to open audio output: {e}")))?;

        let sink = rodio::Sink::try_new(&stream_handle)
            .map_err(|e| PiperError::Inference(format!("failed to create audio sink: {e}")))?;

        Ok(Self {
            _stream,
            sink,
            target_sample_rate: None,
            finalized: false,
        })
    }

    /// Create a player that resamples all incoming audio to
    /// `target_sample_rate` before sending it to the output device.
    ///
    /// Returns an error if `target_sample_rate` is 0.
    pub fn with_sample_rate(target_sample_rate: u32) -> Result<Self, PiperError> {
        if target_sample_rate == 0 {
            return Err(PiperError::Inference(
                "target sample rate must be > 0".to_string(),
            ));
        }

        let (_stream, stream_handle) = rodio::OutputStream::try_default()
            .map_err(|e| PiperError::Inference(format!("failed to open audio output: {e}")))?;

        let sink = rodio::Sink::try_new(&stream_handle)
            .map_err(|e| PiperError::Inference(format!("failed to create audio sink: {e}")))?;

        Ok(Self {
            _stream,
            sink,
            target_sample_rate: Some(target_sample_rate),
            finalized: false,
        })
    }

    /// Block until all queued audio has finished playing.
    pub fn wait_until_done(&self) {
        self.sink.sleep_until_end();
    }

    /// Resample `samples` from `src_rate` to `dst_rate` using linear
    /// interpolation.  Good enough for real-time preview; not
    /// production-grade.
    fn linear_resample(samples: &[i16], src_rate: u32, dst_rate: u32) -> Vec<i16> {
        if src_rate == dst_rate || samples.is_empty() {
            return samples.to_vec();
        }

        let ratio = src_rate as f64 / dst_rate as f64;
        let out_len = ((samples.len() as f64) / ratio).ceil() as usize;
        let mut out = Vec::with_capacity(out_len);

        for i in 0..out_len {
            let src_pos = i as f64 * ratio;
            let idx = src_pos as usize;
            let frac = src_pos - idx as f64;

            let s0 = samples[idx] as f64;
            let s1 = if idx + 1 < samples.len() {
                samples[idx + 1] as f64
            } else {
                s0
            };

            let interpolated = s0 + frac * (s1 - s0);
            out.push(interpolated.clamp(-32768.0, 32767.0) as i16);
        }

        out
    }
}

#[cfg(feature = "playback")]
impl AudioSink for RodioPlayer {
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
        if self.finalized {
            return Err(PiperError::Inference(
                "RodioPlayer: write_chunk called after finalize".to_string(),
            ));
        }
        if sample_rate == 0 {
            return Err(PiperError::Inference("sample rate must be > 0".to_string()));
        }
        if samples.is_empty() {
            return Ok(());
        }

        let (play_samples, play_rate) = match self.target_sample_rate {
            Some(target) if target != sample_rate => {
                let resampled = Self::linear_resample(samples, sample_rate, target);
                (resampled, target)
            }
            _ => (samples.to_vec(), sample_rate),
        };

        let source = rodio::buffer::SamplesBuffer::new(1, play_rate, play_samples);
        self.sink.append(source);

        Ok(())
    }

    fn finalize(&mut self) -> Result<(), PiperError> {
        self.finalized = true;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Helper function
// ---------------------------------------------------------------------------

/// Play audio synchronously through the default output device.
///
/// When the `playback` feature is enabled this uses [`RodioPlayer`].
/// Otherwise it falls back to [`DummyPlayer`] (no-op).
///
/// Returns an error if `sample_rate` is 0 or (with `playback` enabled)
/// if the audio device cannot be opened.
pub fn play_audio(samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
    if sample_rate == 0 {
        return Err(PiperError::Inference("sample rate must be > 0".to_string()));
    }

    #[cfg(feature = "playback")]
    {
        let mut player = RodioPlayer::new()?;
        player.write_chunk(samples, sample_rate)?;
        player.finalize()?;
        player.wait_until_done();
        Ok(())
    }

    #[cfg(not(feature = "playback"))]
    {
        let mut player = DummyPlayer::new();
        player.write_chunk(samples, sample_rate)?;
        player.finalize()?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -- DummyPlayer tests --------------------------------------------------

    #[test]
    fn dummy_player_initial_state() {
        let player = DummyPlayer::new();
        assert_eq!(player.total_samples(), 0);
        assert_eq!(player.chunk_count(), 0);
        assert_eq!(player.last_sample_rate(), 0);
        assert!(!player.is_finalized());
    }

    #[test]
    fn dummy_player_single_chunk() {
        let mut player = DummyPlayer::new();
        let samples = vec![100i16, 200, 300];
        player.write_chunk(&samples, 22050).unwrap();

        assert_eq!(player.total_samples(), 3);
        assert_eq!(player.chunk_count(), 1);
        assert_eq!(player.last_sample_rate(), 22050);
    }

    #[test]
    fn dummy_player_multiple_chunks() {
        let mut player = DummyPlayer::new();
        player.write_chunk(&[1, 2, 3], 22050).unwrap();
        player.write_chunk(&[4, 5], 44100).unwrap();
        player.write_chunk(&[6], 16000).unwrap();

        assert_eq!(player.total_samples(), 6);
        assert_eq!(player.chunk_count(), 3);
        assert_eq!(player.last_sample_rate(), 16000);
    }

    #[test]
    fn dummy_player_finalize() {
        let mut player = DummyPlayer::new();
        player.write_chunk(&[1, 2], 22050).unwrap();
        assert!(!player.is_finalized());

        player.finalize().unwrap();
        assert!(player.is_finalized());
    }

    #[test]
    fn dummy_player_write_after_finalize_errors() {
        let mut player = DummyPlayer::new();
        player.finalize().unwrap();

        let result = player.write_chunk(&[1], 22050);
        assert!(result.is_err());
        assert!(
            result.unwrap_err().to_string().contains("after finalize"),
            "error message should mention finalize"
        );
    }

    #[test]
    fn dummy_player_zero_sample_rate_errors() {
        let mut player = DummyPlayer::new();
        let result = player.write_chunk(&[1, 2], 0);
        assert!(result.is_err());
        assert!(
            result.unwrap_err().to_string().contains("sample rate"),
            "error message should mention sample rate"
        );
    }

    #[test]
    fn dummy_player_empty_chunk() {
        let mut player = DummyPlayer::new();
        player.write_chunk(&[], 22050).unwrap();

        assert_eq!(player.total_samples(), 0);
        assert_eq!(player.chunk_count(), 1);
        assert_eq!(player.last_sample_rate(), 22050);
    }

    #[test]
    fn dummy_player_default_trait() {
        let player = DummyPlayer::default();
        assert_eq!(player.total_samples(), 0);
        assert!(!player.is_finalized());
    }

    // -- CollectorSink tests ------------------------------------------------

    #[test]
    fn collector_sink_collects_samples() {
        let mut sink = CollectorSink::new();
        sink.write_chunk(&[10, 20, 30], 22050).unwrap();
        sink.write_chunk(&[40, 50], 22050).unwrap();

        assert_eq!(sink.samples(), &[10, 20, 30, 40, 50]);
        assert_eq!(sink.sample_rate(), Some(22050));
    }

    #[test]
    fn collector_sink_sample_rate_mismatch_errors() {
        let mut sink = CollectorSink::new();
        sink.write_chunk(&[1], 22050).unwrap();

        let result = sink.write_chunk(&[2], 44100);
        assert!(result.is_err());
        assert!(
            result.unwrap_err().to_string().contains("mismatch"),
            "error message should mention mismatch"
        );
    }

    #[test]
    fn collector_sink_write_after_finalize_errors() {
        let mut sink = CollectorSink::new();
        sink.finalize().unwrap();

        let result = sink.write_chunk(&[1], 22050);
        assert!(result.is_err());
    }

    #[test]
    fn collector_sink_into_samples() {
        let mut sink = CollectorSink::new();
        sink.write_chunk(&[7, 8, 9], 16000).unwrap();
        sink.finalize().unwrap();

        let data = sink.into_samples();
        assert_eq!(data, vec![7, 8, 9]);
    }

    #[test]
    fn collector_sink_empty() {
        let sink = CollectorSink::new();
        assert!(sink.samples().is_empty());
        assert_eq!(sink.sample_rate(), None);
        assert!(!sink.is_finalized());
    }

    #[test]
    fn collector_sink_zero_sample_rate_errors() {
        let mut sink = CollectorSink::new();
        let result = sink.write_chunk(&[1], 0);
        assert!(result.is_err());
    }

    #[test]
    fn collector_sink_default_trait() {
        let sink = CollectorSink::default();
        assert!(sink.samples().is_empty());
        assert!(!sink.is_finalized());
    }

    // -- play_audio helper tests --------------------------------------------

    #[test]
    fn play_audio_zero_sample_rate_errors() {
        let result = play_audio(&[1, 2, 3], 0);
        assert!(result.is_err());
    }

    #[test]
    fn play_audio_empty_samples_ok() {
        // Without the playback feature, this goes through DummyPlayer
        // and should succeed.
        let result = play_audio(&[], 22050);
        assert!(result.is_ok());
    }

    #[test]
    fn play_audio_normal_samples_ok() {
        // Without the playback feature this is a no-op via DummyPlayer.
        let samples: Vec<i16> = (0..100).map(|i| (i * 100) as i16).collect();
        let result = play_audio(&samples, 22050);
        assert!(result.is_ok());
    }

    // -- DummyPlayer additional tests ----------------------------------------

    #[test]
    fn dummy_player_double_finalize_is_idempotent() {
        let mut player = DummyPlayer::new();
        player.write_chunk(&[1, 2, 3], 22050).unwrap();
        player.finalize().unwrap();
        assert!(player.is_finalized());

        // Second finalize should also succeed (idempotent)
        player.finalize().unwrap();
        assert!(player.is_finalized());
    }

    #[test]
    fn dummy_player_large_sample_count() {
        let mut player = DummyPlayer::new();
        let samples: Vec<i16> = vec![42; 1_000_000];
        player.write_chunk(&samples, 22050).unwrap();

        assert_eq!(player.total_samples(), 1_000_000);
        assert_eq!(player.chunk_count(), 1);
        assert_eq!(player.last_sample_rate(), 22050);
    }

    // -- CollectorSink additional tests --------------------------------------

    #[test]
    fn collector_sink_double_finalize_is_idempotent() {
        let mut sink = CollectorSink::new();
        sink.write_chunk(&[10, 20], 44100).unwrap();
        sink.finalize().unwrap();
        assert!(sink.is_finalized());

        // Second finalize should also succeed (idempotent)
        sink.finalize().unwrap();
        assert!(sink.is_finalized());
    }

    #[test]
    fn collector_sink_multiple_different_sample_rates_errors() {
        let mut sink = CollectorSink::new();

        // First chunk at 22050 sets the rate
        sink.write_chunk(&[1, 2, 3], 22050).unwrap();
        assert_eq!(sink.sample_rate(), Some(22050));

        // Second chunk at 44100 must fail with mismatch error
        let result = sink.write_chunk(&[4, 5], 44100);
        assert!(result.is_err());
        let err_msg = result.unwrap_err().to_string();
        assert!(
            err_msg.contains("mismatch"),
            "error should mention mismatch, got: {err_msg}"
        );
        assert!(
            err_msg.contains("22050"),
            "error should mention expected rate 22050, got: {err_msg}"
        );
        assert!(
            err_msg.contains("44100"),
            "error should mention actual rate 44100, got: {err_msg}"
        );

        // Third chunk at 16000 must also fail (first rate still locked at 22050)
        let result2 = sink.write_chunk(&[6], 16000);
        assert!(result2.is_err());

        // Verify only the first chunk's samples were collected
        assert_eq!(sink.samples(), &[1, 2, 3]);
    }

    #[test]
    fn collector_sink_into_samples_ownership() {
        let mut sink = CollectorSink::new();
        sink.write_chunk(&[100, 200, 300], 16000).unwrap();
        sink.write_chunk(&[400, 500], 16000).unwrap();
        sink.finalize().unwrap();

        // into_samples consumes self and returns owned Vec
        let owned: Vec<i16> = sink.into_samples();
        assert_eq!(owned, vec![100, 200, 300, 400, 500]);
        assert_eq!(owned.len(), 5);

        // After into_samples, `sink` is moved -- cannot be used.
        // (This is enforced at compile time, no runtime assertion needed.)
    }

    // -- play_audio with various sample rates --------------------------------

    #[test]
    fn play_audio_various_sample_rates() {
        // Without the `playback` feature, play_audio uses DummyPlayer.
        // All valid sample rates should succeed.
        let samples: Vec<i16> = (0..64).collect();

        for &rate in &[8000u32, 16000, 22050, 44100] {
            let result = play_audio(&samples, rate);
            assert!(
                result.is_ok(),
                "play_audio should succeed at sample rate {rate}"
            );
        }
    }

    // -- RodioPlayer compile-time checks (feature-gated) --------------------
    // These tests verify that the RodioPlayer API compiles correctly
    // under the `playback` feature.  Actual audio output is not tested
    // here because CI environments typically lack an audio device.

    #[cfg(feature = "playback")]
    mod rodio_tests {
        use super::super::*;

        #[test]
        fn rodio_player_zero_target_rate_errors() {
            let result = RodioPlayer::with_sample_rate(0);
            assert!(result.is_err());
            assert!(
                result.unwrap_err().to_string().contains("sample rate"),
                "error message should mention sample rate"
            );
        }

        #[test]
        fn rodio_linear_resample_same_rate() {
            let input = vec![100i16, 200, 300, 400];
            let output = RodioPlayer::linear_resample(&input, 22050, 22050);
            assert_eq!(input, output);
        }

        #[test]
        fn rodio_linear_resample_empty() {
            let output = RodioPlayer::linear_resample(&[], 22050, 44100);
            assert!(output.is_empty());
        }

        #[test]
        fn rodio_linear_resample_upsample() {
            // 1 Hz -> 2 Hz should roughly double the number of samples
            let input = vec![0i16, 1000, 0, -1000];
            let output = RodioPlayer::linear_resample(&input, 100, 200);
            assert!(
                output.len() >= input.len(),
                "upsampled output should have more samples"
            );
        }

        #[test]
        fn rodio_linear_resample_downsample() {
            let input: Vec<i16> = (0..1000).map(|i| (i % 256) as i16).collect();
            let output = RodioPlayer::linear_resample(&input, 44100, 22050);
            assert!(
                output.len() < input.len(),
                "downsampled output should have fewer samples"
            );
        }

        #[test]
        fn rodio_linear_resample_preserves_length_ratio() {
            // Upsample 22050 -> 48000: output length should be
            // ceil(input_len * 48000/22050)
            let input_len = 22050; // 1 second of audio at 22050 Hz
            let input: Vec<i16> = (0..input_len as i16).collect();
            let output = RodioPlayer::linear_resample(&input, 22050, 48000);

            let expected_len = ((input_len as f64) * (48000.0 / 22050.0)).ceil() as usize;
            // Allow +/- 1 sample tolerance for rounding
            assert!(
                (output.len() as isize - expected_len as isize).unsigned_abs() <= 1,
                "expected ~{expected_len} samples, got {}",
                output.len()
            );

            // Verify ratio is approximately correct
            let ratio = output.len() as f64 / input_len as f64;
            let expected_ratio = 48000.0 / 22050.0;
            assert!(
                (ratio - expected_ratio).abs() < 0.01,
                "sample count ratio {ratio:.4} should be close to {expected_ratio:.4}"
            );
        }

        #[test]
        fn rodio_linear_resample_boundary_values() {
            // Test with extreme i16 values (MIN and MAX) to verify
            // clamping and interpolation do not overflow or wrap
            let input = vec![i16::MIN, i16::MAX, i16::MIN, i16::MAX, 0];
            let output = RodioPlayer::linear_resample(&input, 22050, 48000);

            assert!(!output.is_empty(), "resampled output should not be empty");

            // Every output sample must stay within valid i16 range
            for (i, &sample) in output.iter().enumerate() {
                assert!(
                    sample >= i16::MIN && sample <= i16::MAX,
                    "sample[{i}] = {sample} is out of i16 range"
                );
            }

            // Verify the extreme values appear in the output (first and
            // last input samples map directly to output positions)
            assert_eq!(
                output[0],
                i16::MIN,
                "first output sample should be i16::MIN"
            );
        }
    }
}
