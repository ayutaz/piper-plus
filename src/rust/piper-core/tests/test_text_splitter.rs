use piper_plus::text_splitter::{SplitConfig, split_chunks, split_sentences};

// ===========================================================================
// 1. split_sentences — English
// ===========================================================================

#[test]
fn test_single_english_sentence() {
    let result = split_sentences("Hello.");
    assert_eq!(result, vec!["Hello."]);
}

#[test]
fn test_two_english_sentences() {
    let result = split_sentences("Hello. World.");
    assert_eq!(result, vec!["Hello.", "World."]);
}

#[test]
fn test_exclamation_and_question() {
    let result = split_sentences("Hello! World?");
    assert_eq!(result, vec!["Hello!", "World?"]);
}

#[test]
fn test_abbreviation_mr() {
    let result = split_sentences("Mr. Smith went home.");
    assert_eq!(result, vec!["Mr. Smith went home."]);
}

#[test]
fn test_abbreviation_dr_with_quotes() {
    let result = split_sentences("Dr. Brown said \"Hello.\" Then left.");
    // Quoted period should not cause a mid-quote split; the whole thing
    // is treated as a single sentence because the period after "Hello."
    // is inside quotes.
    assert_eq!(result.len(), 1);
    assert!(result[0].starts_with("Dr. Brown"));
}

#[test]
fn test_ellipsis_followed_by_question() {
    let result = split_sentences("Wait... what?");
    // Ellipsis may trigger split at period — implementation-dependent
    assert!(!result.is_empty());
    let joined: String = result.join(" ");
    assert!(joined.contains("Wait") && joined.contains("what?"));
}

#[test]
fn test_three_english_sentences() {
    let result = split_sentences("One. Two. Three.");
    assert_eq!(result, vec!["One.", "Two.", "Three."]);
}

// ===========================================================================
// 2. split_sentences — Japanese
// ===========================================================================

#[test]
fn test_two_japanese_sentences() {
    let result = split_sentences("こんにちは。さようなら。");
    assert_eq!(result, vec!["こんにちは。", "さようなら。"]);
}

#[test]
fn test_japanese_exclamation_and_question() {
    let result = split_sentences("今日は良い天気です！明日も？");
    assert_eq!(result, vec!["今日は良い天気です！", "明日も？"]);
}

#[test]
fn test_japanese_single_sentence_no_punctuation() {
    let result = split_sentences("今日は良い天気です");
    assert_eq!(result, vec!["今日は良い天気です"]);
}

// ===========================================================================
// 3. split_sentences — Mixed languages
// ===========================================================================

#[test]
fn test_english_then_japanese() {
    let result = split_sentences("Hello. こんにちは。");
    assert_eq!(result, vec!["Hello.", "こんにちは。"]);
}

#[test]
fn test_chinese_two_sentences() {
    let result = split_sentences("你好。世界。");
    assert_eq!(result, vec!["你好。", "世界。"]);
}

// ===========================================================================
// 4. split_sentences — Edge cases
// ===========================================================================

#[test]
fn test_empty_string() {
    let result = split_sentences("");
    assert!(result.is_empty());
}

#[test]
fn test_whitespace_only() {
    let result = split_sentences("   ");
    assert!(result.is_empty());
}

#[test]
fn test_no_punctuation() {
    let result = split_sentences("No punctuation here");
    assert_eq!(result, vec!["No punctuation here"]);
}

#[test]
fn test_only_ellipsis() {
    let result = split_sentences("...");
    assert_eq!(result.len(), 1);
    assert_eq!(result[0], "...");
}

#[test]
fn test_multiple_spaces_between_sentences() {
    let result = split_sentences("Hello.  World.");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "Hello.");
    assert_eq!(result[1], "World.");
}

#[test]
fn test_newline_between_sentences() {
    let result = split_sentences("Hello.\nWorld.");
    assert_eq!(result.len(), 2);
    assert_eq!(result[0], "Hello.");
    // Newline may leave leading space on second chunk
    assert!(
        result[1].trim() == "World.",
        "expected 'World.', got '{}'",
        result[1]
    );
}

#[test]
fn test_paragraph_break_double_newline() {
    let result = split_sentences("First paragraph.\n\nSecond paragraph.");
    assert_eq!(result, vec!["First paragraph.", "Second paragraph."]);
}

#[test]
fn test_tab_and_spaces_only() {
    let result = split_sentences("\t  \t");
    assert!(result.is_empty());
}

// ===========================================================================
// 5. split_chunks — basic behaviour
// ===========================================================================

#[test]
fn test_short_text_single_chunk() {
    let config = SplitConfig {
        max_chars: 500,
        split_on_clause: true,
        min_chars: 0,
    };
    let chunks = split_chunks("Hello world.", &config);
    assert_eq!(chunks.len(), 1);
    assert_eq!(chunks[0].text, "Hello world.");
    assert_eq!(chunks[0].index, 0);
    assert!(chunks[0].is_last);
}

#[test]
fn test_long_text_multiple_chunks() {
    // Build text that exceeds a small max_chars limit.
    let text = "First sentence here. Second sentence here. Third sentence here.";
    let config = SplitConfig {
        max_chars: 25,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks(text, &config);
    assert!(
        chunks.len() > 1,
        "expected multiple chunks, got {}",
        chunks.len()
    );
}

#[test]
fn test_chunk_index_sequential() {
    let text = "One. Two. Three. Four. Five.";
    let config = SplitConfig {
        max_chars: 0,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks(text, &config);
    for (i, chunk) in chunks.iter().enumerate() {
        assert_eq!(
            chunk.index, i,
            "chunk index should be {}, got {}",
            i, chunk.index
        );
    }
}

#[test]
fn test_chunk_is_last_only_on_final() {
    let text = "Alpha. Bravo. Charlie.";
    let config = SplitConfig {
        max_chars: 0,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks(text, &config);
    let total = chunks.len();
    assert!(total >= 2, "need at least 2 chunks for this test");
    for (i, chunk) in chunks.iter().enumerate() {
        if i == total - 1 {
            assert!(chunk.is_last, "last chunk must have is_last=true");
        } else {
            assert!(!chunk.is_last, "non-last chunk must have is_last=false");
        }
    }
}

#[test]
fn test_min_chars_merging() {
    // "Hi." is 3 chars which is below min_chars=10, so it should be merged.
    let text = "Hi. Go. Run.";
    let config = SplitConfig {
        max_chars: 500,
        split_on_clause: true,
        min_chars: 10,
    };
    let chunks = split_chunks(text, &config);
    assert!(
        chunks.len() < 3,
        "short sentences should be merged, got {} chunks: {:?}",
        chunks.len(),
        chunks.iter().map(|c| &c.text).collect::<Vec<_>>()
    );
}

#[test]
fn test_default_split_config_behaviour() {
    // With default config (max_chars=500, min_chars=10, split_on_clause=true)
    // a moderate text should come out as a small number of chunks.
    let text = "Hello. World. This is a test.";
    let chunks = split_chunks(text, &SplitConfig::default());
    assert!(!chunks.is_empty());
    // All sentences together are well under 500 chars and each is short,
    // so they should be merged into a single chunk due to min_chars=10.
    // Regardless of exact merging, verify structural invariants.
    let last = chunks.last().unwrap();
    assert!(last.is_last);
    assert_eq!(last.index, chunks.len() - 1);
}

// ===========================================================================
// 6. SplitConfig
// ===========================================================================

#[test]
fn test_default_config_values() {
    let config = SplitConfig::default();
    assert_eq!(config.max_chars, 500);
    assert!(config.split_on_clause);
    assert_eq!(config.min_chars, 10);
}

#[test]
fn test_custom_config() {
    let config = SplitConfig {
        max_chars: 100,
        split_on_clause: false,
        min_chars: 5,
    };
    assert_eq!(config.max_chars, 100);
    assert!(!config.split_on_clause);
    assert_eq!(config.min_chars, 5);
}

#[test]
fn test_max_chars_zero_no_limit() {
    let text = "First. Second. Third.";
    let config = SplitConfig {
        max_chars: 0,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks(text, &config);
    // With no max limit, sentences should be split but may merge
    assert!(
        chunks.len() >= 2,
        "expected at least 2 chunks, got {:?}",
        chunks.iter().map(|c| &c.text).collect::<Vec<_>>()
    );
}

// ===========================================================================
// 7. Additional integration tests
// ===========================================================================

#[test]
fn test_chunks_empty_input() {
    let chunks = split_chunks("", &SplitConfig::default());
    assert!(chunks.is_empty());
}

#[test]
fn test_chunks_whitespace_input() {
    let chunks = split_chunks("   ", &SplitConfig::default());
    assert!(chunks.is_empty());
}

#[test]
fn test_no_trailing_whitespace_in_sentences() {
    let result = split_sentences("Hello.   World.   ");
    for s in &result {
        assert_eq!(s, s.trim_end(), "trailing whitespace found in: {:?}", s);
    }
}

#[test]
fn test_no_trailing_whitespace_in_chunks() {
    let chunks = split_chunks("Hello.   World.   ", &SplitConfig::default());
    for chunk in &chunks {
        assert_eq!(
            chunk.text,
            chunk.text.trim_end(),
            "trailing whitespace in chunk: {:?}",
            chunk.text
        );
    }
}

#[test]
fn test_split_preserves_all_text_content() {
    let text = "First sentence. Second sentence. Third sentence.";
    let config = SplitConfig {
        max_chars: 0,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks(text, &config);
    let rejoined: String = chunks
        .iter()
        .map(|c| c.text.as_str())
        .collect::<Vec<_>>()
        .join(" ");
    assert_eq!(rejoined, text);
}

#[test]
fn test_period_not_followed_by_space_no_split() {
    // A period mid-word (like a URL) should not trigger a sentence split.
    let result = split_sentences("Visit example.com today.");
    assert_eq!(result.len(), 1);
}

#[test]
fn test_multiple_punctuation_marks() {
    let result = split_sentences("Really?! Yes.");
    assert_eq!(result, vec!["Really?!", "Yes."]);
}

#[test]
fn test_clause_splitting_in_chunks() {
    // A single long sentence with clause delimiters should be split when
    // max_chars is small and split_on_clause is enabled.
    let long = "Alpha bravo charlie, delta echo foxtrot; golf hotel india.";
    let config = SplitConfig {
        max_chars: 30,
        split_on_clause: true,
        min_chars: 1,
    };
    let chunks = split_chunks(long, &config);
    assert!(
        chunks.len() > 1,
        "clause splitting should produce multiple chunks, got {}",
        chunks.len()
    );
    for chunk in &chunks {
        assert!(!chunk.text.is_empty());
    }
}

#[test]
fn test_single_chunk_has_correct_metadata() {
    let config = SplitConfig {
        max_chars: 0,
        split_on_clause: false,
        min_chars: 0,
    };
    let chunks = split_chunks("Only one.", &config);
    assert_eq!(chunks.len(), 1);
    assert_eq!(chunks[0].index, 0);
    assert!(chunks[0].is_last);
    assert_eq!(chunks[0].text, "Only one.");
}

#[test]
fn test_abbreviation_eg_no_split() {
    let result = split_sentences("Use tools e.g. a hammer. Done.");
    assert_eq!(result, vec!["Use tools e.g. a hammer.", "Done."]);
}

#[test]
fn test_abbreviation_etc_no_split() {
    let result = split_sentences("Apples, oranges, etc. are fruits. Eat them.");
    assert_eq!(
        result,
        vec!["Apples, oranges, etc. are fruits.", "Eat them."]
    );
}
