//! Streaming synthesis pipeline
//!
//! テキストをセンテンス単位に分割し、逐次合成してAudioSinkに送出する。

use std::io::{Seek, Write};
use std::path::Path;

use crate::error::PiperError;

// ---------------------------------------------------------------------------
// AudioSink trait
// ---------------------------------------------------------------------------

/// Audio output sink trait for receiving synthesized audio chunks.
///
/// Implementations include WAV file, in-memory buffer, rodio playback, etc.
/// Object-safe: no generics in methods.
pub trait AudioSink {
    /// Called for each audio chunk produced by the synthesizer.
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError>;

    /// Called when synthesis is complete.
    fn finalize(&mut self) -> Result<(), PiperError>;
}

// ---------------------------------------------------------------------------
// StreamingResult
// ---------------------------------------------------------------------------

/// Streaming synthesis result summary
#[derive(Debug, Clone)]
pub struct StreamingResult {
    /// Total audio duration in seconds across all chunks
    pub total_audio_seconds: f64,
    /// Total inference wall-clock time in seconds across all chunks
    pub total_infer_seconds: f64,
    /// Number of chunks synthesized
    pub chunk_count: usize,
}

// ---------------------------------------------------------------------------
// BufferSink
// ---------------------------------------------------------------------------

/// In-memory buffer sink that collects all audio chunks into a single Vec.
pub struct BufferSink {
    samples: Vec<i16>,
    sample_rate: Option<u32>,
}

impl BufferSink {
    /// Create a new empty buffer sink.
    pub fn new() -> Self {
        Self {
            samples: Vec::new(),
            sample_rate: None,
        }
    }

    /// Return accumulated samples.
    pub fn get_samples(&self) -> &[i16] {
        &self.samples
    }

    /// Return the sample rate from the last written chunk, if any.
    pub fn sample_rate(&self) -> Option<u32> {
        self.sample_rate
    }
}

impl Default for BufferSink {
    fn default() -> Self {
        Self::new()
    }
}

impl AudioSink for BufferSink {
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
        self.sample_rate = Some(sample_rate);
        self.samples.extend_from_slice(samples);
        Ok(())
    }

    fn finalize(&mut self) -> Result<(), PiperError> {
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// WavFileSink
// ---------------------------------------------------------------------------

/// WAV file sink that writes audio incrementally.
///
/// Writes the WAV header on the first `write_chunk` call with a placeholder
/// data size, then appends sample data on each chunk. On `finalize`, seeks
/// back to update the RIFF file size and data chunk size fields.
pub struct WavFileSink {
    file: std::fs::File,
    sample_rate: u32,
    total_samples: usize,
    header_written: bool,
}

impl WavFileSink {
    /// Create a new WAV file sink.
    ///
    /// The file is created immediately but the WAV header is written on the
    /// first call to `write_chunk` (so that we know the sample rate).
    pub fn new(path: &Path) -> Result<Self, PiperError> {
        let file = std::fs::File::create(path)?;
        Ok(Self {
            file,
            sample_rate: 0,
            total_samples: 0,
            header_written: false,
        })
    }

    /// Write the 44-byte WAV header with placeholder sizes.
    fn write_header(&mut self, sample_rate: u32) -> Result<(), PiperError> {
        let placeholder_data_size: u32 = 0;
        let placeholder_file_size: u32 = 36; // 44 - 8

        // RIFF header
        self.file.write_all(b"RIFF")?;
        self.file.write_all(&placeholder_file_size.to_le_bytes())?;
        self.file.write_all(b"WAVE")?;

        // fmt chunk
        self.file.write_all(b"fmt ")?;
        self.file.write_all(&16u32.to_le_bytes())?; // chunk size
        self.file.write_all(&1u16.to_le_bytes())?; // PCM format
        self.file.write_all(&1u16.to_le_bytes())?; // mono
        self.file.write_all(&sample_rate.to_le_bytes())?;
        self.file.write_all(&(sample_rate * 2).to_le_bytes())?; // byte rate
        self.file.write_all(&2u16.to_le_bytes())?; // block align
        self.file.write_all(&16u16.to_le_bytes())?; // bits per sample

        // data chunk header
        self.file.write_all(b"data")?;
        self.file.write_all(&placeholder_data_size.to_le_bytes())?;

        self.sample_rate = sample_rate;
        self.header_written = true;
        Ok(())
    }

    /// Update the RIFF and data chunk sizes in the WAV header.
    fn update_sizes(&mut self) -> Result<(), PiperError> {
        let data_size_u64 = (self.total_samples as u64) * 2;
        if data_size_u64 > u32::MAX as u64 {
            return Err(PiperError::Streaming(
                "WAV file exceeds 4GB limit".to_string(),
            ));
        }
        let data_size = data_size_u64 as u32;
        let file_size = data_size + 36;

        // Update RIFF chunk size at offset 4
        self.file.seek(std::io::SeekFrom::Start(4))?;
        self.file.write_all(&file_size.to_le_bytes())?;

        // Update data chunk size at offset 40
        self.file.seek(std::io::SeekFrom::Start(40))?;
        self.file.write_all(&data_size.to_le_bytes())?;

        // Flush
        self.file.flush()?;
        Ok(())
    }
}

impl Drop for WavFileSink {
    fn drop(&mut self) {
        // Ensure the WAV header is updated even if the caller forgets to
        // call finalize(). Errors are intentionally ignored during drop.
        let _ = self.finalize();
    }
}

impl AudioSink for WavFileSink {
    fn write_chunk(&mut self, samples: &[i16], sample_rate: u32) -> Result<(), PiperError> {
        if !self.header_written {
            self.write_header(sample_rate)?;
        }

        // Reject mismatched sample rates after the header has been written
        if self.sample_rate != sample_rate {
            return Err(PiperError::Streaming(format!(
                "sample rate mismatch: expected {}, got {}",
                self.sample_rate, sample_rate
            )));
        }

        // Write raw PCM sample data (batched to avoid per-sample syscalls)
        let mut buf = Vec::with_capacity(samples.len() * 2);
        for &sample in samples {
            buf.extend_from_slice(&sample.to_le_bytes());
        }
        self.file.write_all(&buf)?;
        self.total_samples += samples.len();
        Ok(())
    }

    fn finalize(&mut self) -> Result<(), PiperError> {
        if self.header_written {
            self.update_sizes()?;
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// crossfade
// ---------------------------------------------------------------------------

/// Crossfade between two audio chunks using linear interpolation (overlap-add).
///
/// `prev_tail` is the end of the previous chunk, `next_head` is the start of
/// the next chunk. `overlap_samples` controls how many samples are blended.
///
/// If `overlap_samples` exceeds the length of either slice, it is clamped to
/// the shorter of the two.
///
/// Returns a Vec containing the blended overlap region.
pub fn crossfade(prev_tail: &[i16], next_head: &[i16], overlap_samples: usize) -> Vec<i16> {
    let actual_overlap = overlap_samples.min(prev_tail.len()).min(next_head.len());

    if actual_overlap == 0 {
        return Vec::new();
    }

    let mut blended = Vec::with_capacity(actual_overlap);
    for i in 0..actual_overlap {
        // Linear fade: prev fades out, next fades in
        let alpha = if actual_overlap <= 1 {
            1.0
        } else {
            (i as f64) / ((actual_overlap - 1) as f64)
        };
        let prev_sample = prev_tail[prev_tail.len() - actual_overlap + i] as f64;
        let next_sample = next_head[i] as f64;
        let mixed = prev_sample * (1.0 - alpha) + next_sample * alpha;
        blended.push(mixed.clamp(-32768.0, 32767.0) as i16);
    }
    blended
}

// ---------------------------------------------------------------------------
// split_sentences
// ---------------------------------------------------------------------------

/// Split text into sentence-sized chunks suitable for streaming synthesis.
///
/// Splits on sentence-ending punctuation while preserving the punctuation at
/// the end of each chunk. Handles both Japanese (。！？) and Western (.!?)
/// sentence terminators.
///
/// Consecutive whitespace between sentences is trimmed.
/// Empty text returns an empty Vec.
pub fn split_sentences(text: &str) -> Vec<String> {
    if text.is_empty() {
        return Vec::new();
    }

    let mut sentences = Vec::new();
    let mut current = String::new();

    let mut chars = text.chars().peekable();

    while let Some(ch) = chars.next() {
        current.push(ch);

        // Check if this character is a sentence terminator
        if is_sentence_terminator(ch) {
            // Consume any trailing closing punctuation that belongs with this sentence
            // (e.g., 」、）, closing quotes)
            while let Some(&next_ch) = chars.peek() {
                if is_closing_punctuation(next_ch) {
                    current.push(chars.next().unwrap());
                } else {
                    break;
                }
            }

            // Push the completed sentence (trimmed)
            let trimmed = current.trim().to_string();
            if !trimmed.is_empty() {
                sentences.push(trimmed);
            }
            current.clear();

            // Skip leading whitespace before the next sentence
            while let Some(&next_ch) = chars.peek() {
                if next_ch.is_whitespace() {
                    chars.next();
                } else {
                    break;
                }
            }
        }
    }

    // Handle any remaining text (no trailing terminator)
    let trimmed = current.trim().to_string();
    if !trimmed.is_empty() {
        sentences.push(trimmed);
    }

    sentences
}

/// Check whether a character is a sentence-ending terminator.
fn is_sentence_terminator(ch: char) -> bool {
    matches!(
        ch,
        '.' | '!' | '?' | '\u{3002}' // 。
        | '\u{FF01}' // ！
        | '\u{FF1F}' // ？
    )
}

/// Check whether a character is closing punctuation that follows a sentence
/// terminator (e.g., closing brackets, quotation marks).
fn is_closing_punctuation(ch: char) -> bool {
    matches!(
        ch,
        ')' | ']'
            | '}'
            | '"'
            | '\''
            | '\u{300D}' // 」
            | '\u{300F}' // 』
            | '\u{FF09}' // ）
            | '\u{FF3D}' // ］
            | '\u{3011}' // 】
            | '\u{FF63}' // ｣ (half-width)
            | '\u{201D}' // " right double quotation mark
            | '\u{2019}' // ' right single quotation mark
            | '\u{00BB}' // » right-pointing double angle quotation mark
    )
}

// ---------------------------------------------------------------------------
// テスト
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // ===================================================================
    // AudioSink: BufferSink
    // ===================================================================

    #[test]
    fn test_buffer_sink_collects_samples() {
        let mut sink = BufferSink::new();
        sink.write_chunk(&[1, 2, 3], 22050).unwrap();
        sink.write_chunk(&[4, 5], 22050).unwrap();
        sink.finalize().unwrap();
        assert_eq!(sink.get_samples(), &[1, 2, 3, 4, 5]);
    }

    #[test]
    fn test_buffer_sink_empty() {
        let mut sink = BufferSink::new();
        sink.finalize().unwrap();
        assert!(sink.get_samples().is_empty());
        assert_eq!(sink.sample_rate(), None);
    }

    #[test]
    fn test_buffer_sink_sample_rate() {
        let mut sink = BufferSink::new();
        assert_eq!(sink.sample_rate(), None);
        sink.write_chunk(&[100], 44100).unwrap();
        assert_eq!(sink.sample_rate(), Some(44100));
    }

    #[test]
    fn test_buffer_sink_default() {
        let sink = BufferSink::default();
        assert!(sink.get_samples().is_empty());
    }

    // ===================================================================
    // AudioSink: WavFileSink
    // ===================================================================

    #[cfg(feature = "onnx")]
    #[test]
    fn test_wav_file_sink_writes_valid_wav() {
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("test.wav");

        {
            let mut sink = WavFileSink::new(&wav_path).unwrap();
            let samples: Vec<i16> = (0..100).collect();
            sink.write_chunk(&samples, 22050).unwrap();
            sink.finalize().unwrap();
        }

        // Verify with hound
        let reader = hound::WavReader::open(&wav_path).unwrap();
        let spec = reader.spec();
        assert_eq!(spec.channels, 1);
        assert_eq!(spec.sample_rate, 22050);
        assert_eq!(spec.bits_per_sample, 16);
        let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
        let expected: Vec<i16> = (0..100).collect();
        assert_eq!(read_samples, expected);
    }

    #[cfg(feature = "onnx")]
    #[test]
    fn test_wav_file_sink_multiple_chunks() {
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("multi.wav");

        {
            let mut sink = WavFileSink::new(&wav_path).unwrap();
            sink.write_chunk(&[10, 20, 30], 16000).unwrap();
            sink.write_chunk(&[40, 50], 16000).unwrap();
            sink.write_chunk(&[60], 16000).unwrap();
            sink.finalize().unwrap();
        }

        let reader = hound::WavReader::open(&wav_path).unwrap();
        assert_eq!(reader.spec().sample_rate, 16000);
        let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
        assert_eq!(read_samples, vec![10, 20, 30, 40, 50, 60]);
    }

    #[test]
    fn test_wav_file_sink_finalize_without_write() {
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("empty.wav");

        let mut sink = WavFileSink::new(&wav_path).unwrap();
        // Finalize without writing any chunks should not panic
        sink.finalize().unwrap();
    }

    // ===================================================================
    // crossfade
    // ===================================================================

    #[test]
    fn test_crossfade_basic() {
        // prev_tail fades out, next_head fades in
        let prev = vec![1000i16; 10];
        let next = vec![0i16; 10];
        let result = crossfade(&prev, &next, 4);
        assert_eq!(result.len(), 4);
        // At i=0: alpha=0.0 -> 1000*(1.0) + 0*0.0 = 1000
        assert_eq!(result[0], 1000);
        // At i=3: alpha=1.0 -> 1000*0.0 + 0*1.0 = 0
        assert_eq!(result[3], 0);
    }

    #[test]
    fn test_crossfade_equal_blend() {
        let prev = vec![100i16; 4];
        let next = vec![200i16; 4];
        let result = crossfade(&prev, &next, 4);
        assert_eq!(result.len(), 4);
        // i=0: alpha=0.0 -> 100
        assert_eq!(result[0], 100);
        // i=2: alpha=2/3 -> 100*(1/3) + 200*(2/3) = 166.67 -> 166
        assert_eq!(result[2], 166);
    }

    #[test]
    fn test_crossfade_zero_overlap() {
        let prev = vec![100i16; 5];
        let next = vec![200i16; 5];
        let result = crossfade(&prev, &next, 0);
        assert!(result.is_empty());
    }

    #[test]
    fn test_crossfade_overlap_exceeds_prev() {
        let prev = vec![500i16; 3];
        let next = vec![0i16; 10];
        let result = crossfade(&prev, &next, 100);
        // Clamped to min(100, 3, 10) = 3
        assert_eq!(result.len(), 3);
    }

    #[test]
    fn test_crossfade_overlap_exceeds_next() {
        let prev = vec![500i16; 10];
        let next = vec![0i16; 2];
        let result = crossfade(&prev, &next, 100);
        // Clamped to min(100, 10, 2) = 2
        assert_eq!(result.len(), 2);
    }

    #[test]
    fn test_crossfade_empty_slices() {
        let result = crossfade(&[], &[], 10);
        assert!(result.is_empty());
    }

    #[test]
    fn test_crossfade_one_sample() {
        let prev = vec![1000i16];
        let next = vec![0i16];
        let result = crossfade(&prev, &next, 1);
        assert_eq!(result.len(), 1);
        // overlap=1: alpha=1.0 -> 1000*(0.0) + 0*(1.0) = 0
        assert_eq!(result[0], 0);
    }

    // ===================================================================
    // split_sentences
    // ===================================================================

    #[test]
    fn test_split_sentences_japanese() {
        let text = "こんにちは。今日は良い天気ですね。明日も晴れるでしょう。";
        let result = split_sentences(text);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], "こんにちは。");
        assert_eq!(result[1], "今日は良い天気ですね。");
        assert_eq!(result[2], "明日も晴れるでしょう。");
    }

    #[test]
    fn test_split_sentences_english() {
        let text = "Hello world. How are you? I am fine!";
        let result = split_sentences(text);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], "Hello world.");
        assert_eq!(result[1], "How are you?");
        assert_eq!(result[2], "I am fine!");
    }

    #[test]
    fn test_split_sentences_mixed_punctuation() {
        let text = "日本語のテスト。English test! 混合テスト？";
        let result = split_sentences(text);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], "日本語のテスト。");
        assert_eq!(result[1], "English test!");
        assert_eq!(result[2], "混合テスト？");
    }

    #[test]
    fn test_split_sentences_fullwidth_punctuation() {
        let text = "すごい！本当ですか？はい。";
        let result = split_sentences(text);
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], "すごい！");
        assert_eq!(result[1], "本当ですか？");
        assert_eq!(result[2], "はい。");
    }

    #[test]
    fn test_split_sentences_empty() {
        let result = split_sentences("");
        assert!(result.is_empty());
    }

    #[test]
    fn test_split_sentences_no_terminator() {
        let text = "This has no ending punctuation";
        let result = split_sentences(text);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "This has no ending punctuation");
    }

    #[test]
    fn test_split_sentences_whitespace_only() {
        let result = split_sentences("   ");
        assert!(result.is_empty());
    }

    #[test]
    fn test_split_sentences_with_closing_brackets() {
        let text = "「こんにちは。」次の文。";
        let result = split_sentences(text);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "「こんにちは。」");
        assert_eq!(result[1], "次の文。");
    }

    #[test]
    fn test_split_sentences_with_right_double_quote() {
        // U+201C / U+201D: "Hello." should stay in the first chunk
        let text = "She said \u{201C}Hello.\u{201D} Then left.";
        let result = split_sentences(text);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "She said \u{201C}Hello.\u{201D}");
        assert_eq!(result[1], "Then left.");
    }

    #[test]
    fn test_split_sentences_with_right_single_quote() {
        // U+2018 / U+2019: 'Hi.' should stay in the first chunk
        let text = "She said \u{2018}Hi.\u{2019} Then left.";
        let result = split_sentences(text);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "She said \u{2018}Hi.\u{2019}");
        assert_eq!(result[1], "Then left.");
    }

    #[test]
    fn test_split_sentences_with_guillemet() {
        // U+00AB / U+00BB: «Bonjour.» should stay in the first chunk
        let text = "Il a dit \u{00AB}Bonjour.\u{00BB} Ensuite.";
        let result = split_sentences(text);
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "Il a dit \u{00AB}Bonjour.\u{00BB}");
        assert_eq!(result[1], "Ensuite.");
    }

    #[test]
    fn test_split_sentences_single_sentence() {
        let text = "一つだけ。";
        let result = split_sentences(text);
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "一つだけ。");
    }

    // ===================================================================
    // StreamingResult
    // ===================================================================

    #[test]
    fn test_streaming_result_construction() {
        let result = StreamingResult {
            total_audio_seconds: 5.0,
            total_infer_seconds: 1.5,
            chunk_count: 3,
        };
        assert!((result.total_audio_seconds - 5.0).abs() < 1e-9);
        assert!((result.total_infer_seconds - 1.5).abs() < 1e-9);
        assert_eq!(result.chunk_count, 3);
    }

    #[test]
    fn test_streaming_result_clone() {
        let result = StreamingResult {
            total_audio_seconds: 2.0,
            total_infer_seconds: 0.8,
            chunk_count: 1,
        };
        let cloned = result.clone();
        assert_eq!(cloned.chunk_count, result.chunk_count);
        assert!((cloned.total_audio_seconds - result.total_audio_seconds).abs() < 1e-9);
    }

    #[test]
    fn test_streaming_result_debug() {
        let result = StreamingResult {
            total_audio_seconds: 3.15,
            total_infer_seconds: 1.0,
            chunk_count: 2,
        };
        let debug = format!("{:?}", result);
        assert!(debug.contains("total_audio_seconds"));
        assert!(debug.contains("chunk_count"));
    }

    // ===================================================================
    // AudioSink object safety
    // ===================================================================

    #[test]
    fn test_audio_sink_object_safety() {
        // Verify AudioSink can be used as a trait object (dyn)
        fn accept_sink(sink: &mut dyn AudioSink) -> Result<(), PiperError> {
            sink.write_chunk(&[1, 2, 3], 22050)?;
            sink.finalize()
        }
        let mut buffer = BufferSink::new();
        accept_sink(&mut buffer).unwrap();
        assert_eq!(buffer.get_samples(), &[1, 2, 3]);
    }

    // ===================================================================
    // TDD追加テスト: WavFileSink error paths
    // ===================================================================

    #[cfg(feature = "onnx")]
    #[test]
    fn test_wav_file_sink_drop_finalizes() {
        // Drop without calling finalize() should still produce a valid WAV.
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("drop_test.wav");

        {
            let mut sink = WavFileSink::new(&wav_path).unwrap();
            let samples: Vec<i16> = vec![100, 200, 300, -100, -200];
            sink.write_chunk(&samples, 22050).unwrap();
            // Intentionally NOT calling finalize(); drop should handle it.
        }

        // Read back with hound and verify the WAV is valid
        let reader = hound::WavReader::open(&wav_path).unwrap();
        let spec = reader.spec();
        assert_eq!(spec.channels, 1);
        assert_eq!(spec.sample_rate, 22050);
        assert_eq!(spec.bits_per_sample, 16);
        let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
        assert_eq!(read_samples, vec![100, 200, 300, -100, -200]);
    }

    #[test]
    fn test_wav_file_sink_sample_rate_mismatch_rejected() {
        // Writing chunks with different sample rates must return an error.
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("rate_mismatch.wav");

        let mut sink = WavFileSink::new(&wav_path).unwrap();
        sink.write_chunk(&[10, 20], 16000).unwrap();
        let err = sink.write_chunk(&[30, 40], 44100).unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("sample rate mismatch"),
            "expected sample rate mismatch error, got: {}",
            msg
        );
    }

    #[cfg(feature = "onnx")]
    #[test]
    fn test_wav_file_sink_same_sample_rate_ok() {
        // Multiple chunks with the same sample rate should succeed.
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("same_rate.wav");

        {
            let mut sink = WavFileSink::new(&wav_path).unwrap();
            sink.write_chunk(&[10, 20], 16000).unwrap();
            sink.write_chunk(&[30, 40], 16000).unwrap();
            sink.finalize().unwrap();
        }

        let reader = hound::WavReader::open(&wav_path).unwrap();
        assert_eq!(reader.spec().sample_rate, 16000);
        let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
        assert_eq!(read_samples, vec![10, 20, 30, 40]);
    }

    #[test]
    fn test_wav_file_sink_overflow_rejected() {
        // Simulate a total_samples count that would overflow u32 when
        // converted to byte size. We cannot actually write 2B+ samples in a
        // test, so we poke the internal state via a helper.
        let dir = tempfile::tempdir().unwrap();
        let wav_path = dir.path().join("overflow.wav");

        let mut sink = WavFileSink::new(&wav_path).unwrap();
        sink.write_chunk(&[1], 22050).unwrap();
        // Manually set total_samples to a value that overflows u32 * 2
        sink.total_samples = (u32::MAX as usize) / 2 + 2;
        let err = sink.finalize().unwrap_err();
        let msg = err.to_string();
        assert!(
            msg.contains("4GB"),
            "expected 4GB limit error, got: {}",
            msg
        );
    }

    // ===================================================================
    // TDD追加テスト: crossfade edge cases
    // ===================================================================

    #[test]
    fn test_crossfade_negative_samples() {
        // Realistic negative audio values: linear blend between two negative/positive regions
        let prev = vec![-10000i16, -5000];
        let next = vec![5000i16, 10000];
        let result = crossfade(&prev, &next, 2);
        assert_eq!(result.len(), 2);
        // i=0: alpha=0.0 -> -10000*(1.0) + 5000*(0.0) = -10000
        assert_eq!(result[0], -10000);
        // i=1: alpha=1.0 -> -5000*(0.0) + 10000*(1.0) = 10000
        assert_eq!(result[1], 10000);
    }

    #[test]
    fn test_crossfade_max_i16_values() {
        // Verify no overflow when blending i16::MAX and i16::MIN.
        // The computation is done in f64 and clamped to [-32768, 32767].
        let prev = vec![i16::MAX, i16::MAX];
        let next = vec![i16::MIN, i16::MIN];
        let result = crossfade(&prev, &next, 2);
        assert_eq!(result.len(), 2);
        // i=0: alpha=0.0 -> 32767*(1.0) + (-32768)*(0.0) = 32767
        assert_eq!(result[0], i16::MAX);
        // i=1: alpha=1.0 -> 32767*0.0 + (-32768)*1.0 = -32768 = i16::MIN
        assert_eq!(result[1], i16::MIN);
    }

    // ===================================================================
    // TDD追加テスト: split_sentences edge cases
    // ===================================================================

    #[test]
    fn test_split_sentences_consecutive_terminators() {
        // "Really?! Yes." — '?' and '!' are each sentence terminators.
        // '?' triggers the first split -> "Really?"
        // '!' is consumed as a new char, immediately triggers a split -> "!"
        // " Yes." is the third chunk -> "Yes."
        let result = split_sentences("Really?! Yes.");
        assert_eq!(result.len(), 3);
        assert_eq!(result[0], "Really?");
        assert_eq!(result[1], "!");
        assert_eq!(result[2], "Yes.");
    }

    #[test]
    fn test_split_sentences_single_char_sentence() {
        // "A. B." should produce 2 chunks: "A." and "B."
        let result = split_sentences("A. B.");
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "A.");
        assert_eq!(result[1], "B.");
    }

    #[test]
    fn test_split_sentences_newline_separator() {
        // Newlines between sentences should be treated as whitespace and trimmed.
        let result = split_sentences("Hello.\nWorld.");
        assert_eq!(result.len(), 2);
        assert_eq!(result[0], "Hello.");
        assert_eq!(result[1], "World.");
    }

    // ===================================================================
    // TDD追加テスト: BufferSink large data
    // ===================================================================

    #[test]
    fn test_buffer_sink_large_chunks() {
        // Write 1M samples and verify total count.
        let mut sink = BufferSink::new();
        let chunk: Vec<i16> = (0..10_000).map(|i| (i % 1000) as i16).collect();
        for _ in 0..100 {
            sink.write_chunk(&chunk, 22050).unwrap();
        }
        sink.finalize().unwrap();
        assert_eq!(sink.get_samples().len(), 1_000_000);
        assert_eq!(sink.sample_rate(), Some(22050));
    }
}
