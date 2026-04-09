use piper_plus::error::PiperError;
use piper_plus::streaming::{
    AudioSink, BufferSink, StreamingResult, WavFileSink, crossfade, split_sentences,
};

// ===================================================================
// 1. AudioSink trait -- BufferSink
// ===================================================================

#[test]
fn test_buffer_sink_collects_single_chunk() {
    let mut sink = BufferSink::new();
    sink.write_chunk(&[10, 20, 30], 22050).unwrap();
    sink.finalize().unwrap();
    assert_eq!(sink.get_samples(), &[10, 20, 30]);
}

#[test]
fn test_buffer_sink_multiple_chunks_accumulate() {
    let mut sink = BufferSink::new();
    sink.write_chunk(&[1, 2], 22050).unwrap();
    sink.write_chunk(&[3, 4, 5], 22050).unwrap();
    sink.write_chunk(&[6], 22050).unwrap();
    sink.finalize().unwrap();
    assert_eq!(sink.get_samples(), &[1, 2, 3, 4, 5, 6]);
}

#[test]
fn test_buffer_sink_empty_input() {
    let mut sink = BufferSink::new();
    sink.write_chunk(&[], 22050).unwrap();
    sink.finalize().unwrap();
    assert!(sink.get_samples().is_empty());
}

#[test]
fn test_buffer_sink_finalize_is_idempotent() {
    let mut sink = BufferSink::new();
    sink.write_chunk(&[100, 200], 22050).unwrap();
    sink.finalize().unwrap();
    sink.finalize().unwrap();
    sink.finalize().unwrap();
    // Samples remain intact after repeated finalize calls
    assert_eq!(sink.get_samples(), &[100, 200]);
}

#[test]
fn test_buffer_sink_finalize_without_write() {
    let mut sink = BufferSink::new();
    sink.finalize().unwrap();
    assert!(sink.get_samples().is_empty());
    assert_eq!(sink.sample_rate(), None);
}

#[test]
fn test_buffer_sink_sample_rate_tracking() {
    let mut sink = BufferSink::new();
    assert_eq!(sink.sample_rate(), None);
    sink.write_chunk(&[1], 22050).unwrap();
    assert_eq!(sink.sample_rate(), Some(22050));
    // Sample rate updates to the latest chunk's rate
    sink.write_chunk(&[2], 44100).unwrap();
    assert_eq!(sink.sample_rate(), Some(44100));
}

#[test]
fn test_buffer_sink_default_trait() {
    let sink = BufferSink::default();
    assert!(sink.get_samples().is_empty());
    assert_eq!(sink.sample_rate(), None);
}

#[test]
fn test_buffer_sink_large_chunk() {
    let mut sink = BufferSink::new();
    let samples: Vec<i16> = (0..10_000).map(|i| (i % 1000) as i16).collect();
    sink.write_chunk(&samples, 22050).unwrap();
    sink.finalize().unwrap();
    assert_eq!(sink.get_samples().len(), 10_000);
    assert_eq!(sink.get_samples()[0], 0);
    assert_eq!(sink.get_samples()[999], 999);
    assert_eq!(sink.get_samples()[1000], 0);
}

#[test]
fn test_buffer_sink_as_dyn_audio_sink() {
    // Confirm AudioSink is object-safe and BufferSink works through dyn dispatch
    fn write_via_trait(sink: &mut dyn AudioSink) -> Result<(), PiperError> {
        sink.write_chunk(&[42, 43], 16000)?;
        sink.finalize()
    }
    let mut sink = BufferSink::new();
    write_via_trait(&mut sink).unwrap();
    assert_eq!(sink.get_samples(), &[42, 43]);
}

// ===================================================================
// 2. AudioSink trait -- WavFileSink
// ===================================================================

#[test]
fn test_wav_file_sink_creates_valid_wav() {
    let dir = tempfile::tempdir().unwrap();
    let wav_path = dir.path().join("output.wav");

    {
        let mut sink = WavFileSink::new(&wav_path).unwrap();
        let samples: Vec<i16> = (0..256).collect();
        sink.write_chunk(&samples, 22050).unwrap();
        sink.finalize().unwrap();
    }

    // Validate using the hound crate (available as a dependency)
    let reader = hound::WavReader::open(&wav_path).unwrap();
    let spec = reader.spec();
    assert_eq!(spec.channels, 1);
    assert_eq!(spec.sample_rate, 22050);
    assert_eq!(spec.bits_per_sample, 16);
    assert_eq!(spec.sample_format, hound::SampleFormat::Int);
    let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
    let expected: Vec<i16> = (0..256).collect();
    assert_eq!(read_samples, expected);
}

#[test]
fn test_wav_file_sink_multiple_chunks() {
    let dir = tempfile::tempdir().unwrap();
    let wav_path = dir.path().join("multi_chunk.wav");

    {
        let mut sink = WavFileSink::new(&wav_path).unwrap();
        sink.write_chunk(&[10, 20, 30], 16000).unwrap();
        sink.write_chunk(&[40, 50], 16000).unwrap();
        sink.write_chunk(&[60, 70, 80, 90], 16000).unwrap();
        sink.finalize().unwrap();
    }

    let reader = hound::WavReader::open(&wav_path).unwrap();
    assert_eq!(reader.spec().sample_rate, 16000);
    let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
    assert_eq!(read_samples, vec![10, 20, 30, 40, 50, 60, 70, 80, 90]);
}

#[test]
fn test_wav_file_sink_with_zero_samples() {
    let dir = tempfile::tempdir().unwrap();
    let wav_path = dir.path().join("zero.wav");

    let mut sink = WavFileSink::new(&wav_path).unwrap();
    // Finalize without writing any chunks -- should not panic
    sink.finalize().unwrap();
    // File should exist (created during new()) but may not be a valid WAV
    assert!(wav_path.exists());
}

#[test]
fn test_wav_file_sink_sample_data_integrity() {
    let dir = tempfile::tempdir().unwrap();
    let wav_path = dir.path().join("integrity.wav");

    let samples: Vec<i16> = vec![-32768, -1000, 0, 1000, 32767];
    {
        let mut sink = WavFileSink::new(&wav_path).unwrap();
        sink.write_chunk(&samples, 44100).unwrap();
        sink.finalize().unwrap();
    }

    let reader = hound::WavReader::open(&wav_path).unwrap();
    assert_eq!(reader.spec().sample_rate, 44100);
    let read_samples: Vec<i16> = reader.into_samples::<i16>().map(|s| s.unwrap()).collect();
    assert_eq!(read_samples, samples);
}

// ===================================================================
// 3. Crossfade algorithm
// ===================================================================

#[test]
fn test_crossfade_equal_length_slices() {
    let prev = vec![1000i16; 8];
    let next = vec![0i16; 8];
    let result = crossfade(&prev, &next, 4);
    assert_eq!(result.len(), 4);
    // New formula: alpha = i / (overlap - 1) = i / 3
    // i=0: alpha=0/3=0.0   -> 1000*1.0 + 0*0.0 = 1000
    assert_eq!(result[0], 1000);
    // i=1: alpha=1/3=0.333 -> 1000*0.667 + 0*0.333 = 666
    assert_eq!(result[1], 666);
    // i=2: alpha=2/3=0.667 -> 1000*0.333 + 0*0.667 = 333
    assert_eq!(result[2], 333);
    // i=3: alpha=3/3=1.0   -> 1000*0.0 + 0*1.0 = 0
    assert_eq!(result[3], 0);
}

#[test]
fn test_crossfade_overlap_zero_returns_empty() {
    let prev = vec![100i16; 10];
    let next = vec![200i16; 10];
    let result = crossfade(&prev, &next, 0);
    assert!(result.is_empty());
}

#[test]
fn test_crossfade_overlap_exceeds_input_length_clamped() {
    let prev = vec![500i16; 3];
    let next = vec![0i16; 10];
    let result = crossfade(&prev, &next, 100);
    // Clamped to min(100, 3, 10) = 3
    assert_eq!(result.len(), 3);
}

#[test]
fn test_crossfade_overlap_exceeds_next_clamped() {
    let prev = vec![500i16; 10];
    let next = vec![0i16; 2];
    let result = crossfade(&prev, &next, 50);
    // Clamped to min(50, 10, 2) = 2
    assert_eq!(result.len(), 2);
}

#[test]
fn test_crossfade_empty_inputs() {
    assert!(crossfade(&[], &[], 10).is_empty());
    assert!(crossfade(&[100], &[], 5).is_empty());
    assert!(crossfade(&[], &[200], 5).is_empty());
}

#[test]
fn test_crossfade_values_linearly_interpolated() {
    // prev_tail = [100, 100, 100, 100], next_head = [200, 200, 200, 200]
    let prev = vec![100i16; 4];
    let next = vec![200i16; 4];
    let result = crossfade(&prev, &next, 4);
    assert_eq!(result.len(), 4);
    // New formula: alpha = i / (overlap - 1) = i / 3
    // i=0: alpha=0/3=0.0   -> 100*1.0   + 200*0.0   = 100
    assert_eq!(result[0], 100);
    // i=1: alpha=1/3=0.333 -> 100*0.667 + 200*0.333 = 66.7 + 66.6 = 133
    assert_eq!(result[1], 133);
    // i=2: alpha=2/3=0.667 -> 100*0.333 + 200*0.667 = 33.3 + 133.4 = 166
    assert_eq!(result[2], 166);
    // i=3: alpha=3/3=1.0   -> 100*0.0   + 200*1.0   = 200
    assert_eq!(result[3], 200);
}

#[test]
fn test_crossfade_single_sample() {
    let prev = vec![1000i16];
    let next = vec![0i16];
    let result = crossfade(&prev, &next, 1);
    assert_eq!(result.len(), 1);
    // Single sample: alpha = 1.0 (full transition to next)
    assert_eq!(result[0], 0);
}

#[test]
fn test_crossfade_uses_tail_of_prev() {
    // prev has 6 elements but overlap is 3; crossfade should use the LAST 3
    let prev = vec![0, 0, 0, 300, 300, 300];
    let next = vec![600i16; 6];
    let result = crossfade(&prev, &next, 3);
    assert_eq!(result.len(), 3);
    // New formula: alpha = i / (overlap - 1) = i / 2
    // i=0: alpha=0/2=0.0 -> 300*1.0 + 600*0.0 = 300
    assert_eq!(result[0], 300);
    // i=1: alpha=1/2=0.5 -> 300*0.5 + 600*0.5 = 150 + 300 = 450
    assert_eq!(result[1], 450);
    // i=2: alpha=2/2=1.0 -> 300*0.0 + 600*1.0 = 600
    assert_eq!(result[2], 600);
}

#[test]
fn test_crossfade_clamp_prevents_overflow() {
    // Near-max values that, when blended, stay within i16 range
    let prev = vec![32767i16; 4];
    let next = vec![-32768i16; 4];
    let result = crossfade(&prev, &next, 4);
    assert_eq!(result.len(), 4);
    // crossfade completed without overflow — verify expected boundary value
    // i=0: alpha=0.0 -> 32767
    assert_eq!(result[0], 32767);
}

// ===================================================================
// 4. Sentence splitting
// ===================================================================

#[test]
fn test_split_sentences_english_basic() {
    let result = split_sentences("Hello. World.");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "Hello.");
    assert_eq!(result[1], "World.");
}

#[test]
fn test_split_sentences_japanese_basic() {
    let result = split_sentences("こんにちは。さようなら。");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "こんにちは。");
    assert_eq!(result[1], "さようなら。");
}

#[test]
fn test_split_sentences_question_marks() {
    let result = split_sentences("How are you? I am fine.");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "How are you?");
    assert_eq!(result[1], "I am fine.");
}

#[test]
fn test_split_sentences_exclamation_marks() {
    let result = split_sentences("Wow! That is great!");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "Wow!");
    assert_eq!(result[1], "That is great!");
}

#[test]
fn test_split_sentences_mixed_punctuation() {
    let result = split_sentences("First. Second! Third?");
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], "First.");
    assert_eq!(result[1], "Second!");
    assert_eq!(result[2], "Third?");
}

#[test]
fn test_split_sentences_empty_string() {
    let result = split_sentences("");
    assert!(result.is_empty());
}

#[test]
fn test_split_sentences_no_punctuation_returns_whole_text() {
    let result = split_sentences("This has no ending punctuation");
    assert_eq!(result.len(), 1);
    assert_eq!(result[0], "This has no ending punctuation");
}

#[test]
fn test_split_sentences_preserves_punctuation() {
    // Each sentence should retain its terminator
    let result = split_sentences("A. B! C?");
    assert_eq!(result[0], "A.");
    assert_eq!(result[1], "B!");
    assert_eq!(result[2], "C?");
}

#[test]
fn test_split_sentences_multiple_spaces_between() {
    let result = split_sentences("First.    Second.     Third.");
    assert_eq!(result.len(), 3);
    // Leading/trailing whitespace is trimmed from each sentence
    assert_eq!(result[0], "First.");
    assert_eq!(result[1], "Second.");
    assert_eq!(result[2], "Third.");
}

#[test]
fn test_split_sentences_whitespace_only() {
    let result = split_sentences("    ");
    assert!(result.is_empty());
}

#[test]
fn test_split_sentences_fullwidth_japanese_punctuation() {
    // Using fullwidth exclamation and question (U+FF01, U+FF1F)
    let result = split_sentences("すごい！本当ですか？はい。");
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], "すごい\u{FF01}");
    assert_eq!(result[1], "本当ですか\u{FF1F}");
    assert_eq!(result[2], "はい。");
}

#[test]
fn test_split_sentences_with_closing_brackets() {
    // Closing bracket 」 after terminator should stay with the sentence
    let result = split_sentences("「こんにちは。」次の文。");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "「こんにちは。」");
    assert_eq!(result[1], "次の文。");
}

#[test]
fn test_split_sentences_single_sentence() {
    let result = split_sentences("One sentence.");
    assert_eq!(result.len(), 1);
    assert_eq!(result[0], "One sentence.");
}

#[test]
fn test_split_sentences_japanese_three_sentences() {
    let text = "こんにちは。今日は良い天気ですね。明日も晴れるでしょう。";
    let result = split_sentences(text);
    assert_eq!(result.len(), 3);
    assert_eq!(result[0], "こんにちは。");
    assert_eq!(result[1], "今日は良い天気ですね。");
    assert_eq!(result[2], "明日も晴れるでしょう。");
}

// ===================================================================
// 5. StreamingResult
// ===================================================================

#[test]
fn test_streaming_result_construction_and_fields() {
    let result = StreamingResult {
        total_audio_seconds: 5.5,
        total_infer_seconds: 1.2,
        chunk_count: 3,
    };
    assert!((result.total_audio_seconds - 5.5).abs() < f64::EPSILON);
    assert!((result.total_infer_seconds - 1.2).abs() < f64::EPSILON);
    assert_eq!(result.chunk_count, 3);
}

#[test]
fn test_streaming_result_clone() {
    let original = StreamingResult {
        total_audio_seconds: 10.0,
        total_infer_seconds: 2.5,
        chunk_count: 4,
    };
    let cloned = original.clone();
    assert!((cloned.total_audio_seconds - original.total_audio_seconds).abs() < f64::EPSILON);
    assert!((cloned.total_infer_seconds - original.total_infer_seconds).abs() < f64::EPSILON);
    assert_eq!(cloned.chunk_count, original.chunk_count);
}

#[test]
fn test_streaming_result_debug_format() {
    let result = StreamingResult {
        total_audio_seconds: 3.15,
        total_infer_seconds: 1.0,
        chunk_count: 2,
    };
    let debug = format!("{:?}", result);
    assert!(debug.contains("total_audio_seconds"));
    assert!(debug.contains("total_infer_seconds"));
    assert!(debug.contains("chunk_count"));
}

#[test]
fn test_streaming_result_zero_values() {
    let result = StreamingResult {
        total_audio_seconds: 0.0,
        total_infer_seconds: 0.0,
        chunk_count: 0,
    };
    assert_eq!(result.chunk_count, 0);
    assert!((result.total_audio_seconds - 0.0).abs() < f64::EPSILON);
    assert!((result.total_infer_seconds - 0.0).abs() < f64::EPSILON);
}
