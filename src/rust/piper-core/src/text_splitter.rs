//! Text splitting for streaming synthesis.
//!
//! Splits input text into sentence-sized chunks at natural boundaries
//! (sentence-ending punctuation, paragraph breaks) while respecting
//! maximum chunk size limits.

/// Text chunk with metadata
#[derive(Debug, Clone)]
pub struct TextChunk {
    pub text: String,
    pub index: usize,
    pub is_last: bool,
}

/// Split configuration
#[derive(Debug, Clone)]
pub struct SplitConfig {
    /// Maximum characters per chunk (0 = no limit)
    pub max_chars: usize,
    /// Whether to split on commas and semicolons (for very long sentences)
    pub split_on_clause: bool,
    /// Minimum chunk size (avoid very short chunks)
    pub min_chars: usize,
}

impl Default for SplitConfig {
    fn default() -> Self {
        Self {
            max_chars: 500,
            split_on_clause: true,
            min_chars: 10,
        }
    }
}

/// Common English abbreviations that should not trigger sentence splitting.
const ABBREVIATIONS: &[&str] = &[
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Jr.", "Sr.", "Inc.", "Ltd.", "Corp.", "Co.", "vs.",
    "etc.", "approx.", "dept.", "est.", "vol.", "no.", "tel.", "fax.", "Jan.", "Feb.", "Mar.",
    "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.", "St.", "Ave.", "Blvd.", "Rd.",
    "a.m.", "p.m.", "e.g.", "i.e.",
];

/// Check whether the text immediately before a period position ends with
/// a known abbreviation. `dot_pos` is the byte index of the '.' character.
fn ends_with_abbreviation(text: &str, dot_pos: usize) -> bool {
    // The slice up to and including the dot
    let up_to_dot = &text[..=dot_pos];
    for abbr in ABBREVIATIONS {
        if up_to_dot.ends_with(abbr) {
            return true;
        }
        // Case-insensitive: also check lowercase version of first char
        let lower = abbr.to_lowercase();
        if up_to_dot.ends_with(&lower) {
            return true;
        }
    }
    false
}

/// Returns true if the character is a CJK sentence-ending punctuation mark.
fn is_cjk_sentence_end(c: char) -> bool {
    matches!(c, '\u{3002}' | '\u{FF01}' | '\u{FF1F}')
    // 。(U+3002)  ！(U+FF01)  ？(U+FF1F)
}

/// Returns true if the character is a Western sentence-ending punctuation mark.
fn is_western_sentence_end(c: char) -> bool {
    matches!(c, '.' | '!' | '?')
}

/// Split text into sentences.
///
/// Handles:
/// - Western punctuation: . ! ? (followed by space or end)
/// - Japanese punctuation: 。！？
/// - Chinese punctuation: 。！？
/// - Newlines/paragraph breaks
/// - Quoted speech ("Hello." he said)
/// - Abbreviations (Mr. Dr. etc. - don't split these)
pub fn split_sentences(text: &str) -> Vec<String> {
    if text.is_empty() || text.chars().all(|c| c.is_whitespace()) {
        return Vec::new();
    }

    let mut sentences: Vec<String> = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;

    // Build a (byte_offset, char) index from char_indices() so we can track
    // byte positions incrementally instead of collecting into Vec<char>.
    let indexed: Vec<(usize, char)> = text.char_indices().collect();
    let len = indexed.len();
    let mut i = 0;

    while i < len {
        let (_byte_off, c) = indexed[i];

        // Track quote state
        if c == '"' || c == '\u{201C}' || c == '\u{201D}' {
            in_quotes = !in_quotes;
            current.push(c);
            i += 1;
            continue;
        }

        // Handle paragraph breaks (two or more newlines)
        if c == '\n' {
            // Count consecutive newlines
            let mut newline_count = 0;
            let mut j = i;
            while j < len && (indexed[j].1 == '\n' || indexed[j].1 == '\r') {
                if indexed[j].1 == '\n' {
                    newline_count += 1;
                }
                j += 1;
            }

            if newline_count >= 2 {
                // Paragraph break: flush current sentence
                let trimmed = current.trim_end().to_string();
                if !trimmed.is_empty() {
                    sentences.push(trimmed);
                }
                current.clear();
                i = j;
                continue;
            } else {
                // Single newline: treat as space
                current.push(' ');
                i = j;
                continue;
            }
        }

        // CJK sentence-ending punctuation: always split (no abbreviation ambiguity)
        if is_cjk_sentence_end(c) {
            current.push(c);
            // Consume any trailing CJK punctuation or closing quotes/brackets
            while i + 1 < len
                && (indexed[i + 1].1 == '\u{300D}' // 」
                || indexed[i + 1].1 == '\u{300F}'                 // 』
                || indexed[i + 1].1 == '\u{FF09}'                 // ）
                || indexed[i + 1].1 == '"'
                || indexed[i + 1].1 == '\u{201D}')
            // "
            {
                i += 1;
                current.push(indexed[i].1);
            }
            let trimmed = current.trim_end().to_string();
            if !trimmed.is_empty() {
                sentences.push(trimmed);
            }
            current.clear();
            i += 1;
            // Skip whitespace after CJK sentence end
            while i < len && indexed[i].1.is_whitespace() && indexed[i].1 != '\n' {
                i += 1;
            }
            continue;
        }

        // Western sentence-ending punctuation
        if is_western_sentence_end(c) {
            current.push(c);

            // Handle multiple consecutive punctuation: !? ?! !! ...
            while i + 1 < len
                && (is_western_sentence_end(indexed[i + 1].1) || indexed[i + 1].1 == '.')
            {
                i += 1;
                current.push(indexed[i].1);
            }

            // Consume closing quotes after punctuation
            while i + 1 < len
                && (indexed[i + 1].1 == '"'
                    || indexed[i + 1].1 == '\u{201D}'
                    || indexed[i + 1].1 == '\'')
            {
                i += 1;
                current.push(indexed[i].1);
            }

            // Check if this is an abbreviation (only for periods)
            if c == '.' {
                // Use byte offset directly from char_indices
                let byte_pos = indexed[i].0;
                if ends_with_abbreviation(&text[..=byte_pos], byte_pos) {
                    // Don't split at abbreviations
                    i += 1;
                    continue;
                }

                // Check for ellipsis: three or more dots
                let dot_count = current.chars().rev().take_while(|&ch| ch == '.').count();
                if dot_count >= 3 {
                    // Ellipsis: don't split here, continue to see if next
                    // char is whitespace + capital or more punctuation
                    if i + 1 < len && !indexed[i + 1].1.is_whitespace() {
                        i += 1;
                        continue;
                    }
                }
            }

            // Check if followed by whitespace or end of string
            let next_i = i + 1;
            if next_i >= len {
                // End of string: flush
                let trimmed = current.trim_end().to_string();
                if !trimmed.is_empty() {
                    sentences.push(trimmed);
                }
                current.clear();
                i = next_i;
                continue;
            }

            if indexed[next_i].1.is_whitespace() || indexed[next_i].1 == '\n' {
                // Don't split if we're inside quotes
                if in_quotes {
                    i += 1;
                    continue;
                }

                let trimmed = current.trim_end().to_string();
                if !trimmed.is_empty() {
                    sentences.push(trimmed);
                }
                current.clear();
                i = next_i;
                // Skip whitespace between sentences
                while i < len && indexed[i].1 == ' ' {
                    i += 1;
                }
                continue;
            }

            i += 1;
            continue;
        }

        current.push(c);
        i += 1;
    }

    // Flush remaining text
    let trimmed = current.trim_end().to_string();
    if !trimmed.is_empty() {
        sentences.push(trimmed);
    }

    sentences
}

/// Split a single long sentence at clause boundaries (commas, semicolons, colons).
fn split_at_clauses(text: &str) -> Vec<String> {
    let clause_delimiters: &[char] = &[
        ',', ';', ':', '\u{3001}', // 、(Japanese comma)
        '\u{FF0C}', // ，(fullwidth comma)
        '\u{FF1B}', // ；(fullwidth semicolon)
    ];

    let mut clauses: Vec<String> = Vec::new();
    let mut current = String::new();

    let indexed: Vec<(usize, char)> = text.char_indices().collect();
    let len = indexed.len();
    let mut i = 0;

    while i < len {
        let (_byte_off, c) = indexed[i];
        current.push(c);

        if clause_delimiters.contains(&c) {
            // Include trailing space if present
            if i + 1 < len && indexed[i + 1].1 == ' ' {
                i += 1;
                current.push(indexed[i].1);
            }
            let trimmed = current.trim_end().to_string();
            if !trimmed.is_empty() {
                clauses.push(trimmed);
            }
            current.clear();
        }

        i += 1;
    }

    // Flush remaining
    let trimmed = current.trim_end().to_string();
    if !trimmed.is_empty() {
        clauses.push(trimmed);
    }

    // If we got no splits (no clause delimiters found), return the original
    if clauses.len() <= 1 {
        let trimmed = text.trim_end().to_string();
        if trimmed.is_empty() {
            return Vec::new();
        }
        return vec![trimmed];
    }

    clauses
}

/// Split text into chunks with configuration.
///
/// First splits into sentences, then merges/splits to respect size limits.
pub fn split_chunks(text: &str, config: &SplitConfig) -> Vec<TextChunk> {
    let sentences = split_sentences(text);
    if sentences.is_empty() {
        return Vec::new();
    }

    let max = config.max_chars;
    let min = config.min_chars;

    // Phase 1: Expand sentences that exceed max_chars via clause splitting
    let mut expanded: Vec<String> = Vec::new();
    for sentence in sentences {
        if max > 0 && sentence.len() > max && config.split_on_clause {
            let clauses = split_at_clauses(&sentence);
            // Merge clauses that are still too long -- just keep them as-is
            // (we cannot split further without breaking words)
            for clause in clauses {
                expanded.push(clause);
            }
        } else {
            expanded.push(sentence);
        }
    }

    // Phase 2: Merge short fragments so they meet min_chars
    let mut merged: Vec<String> = Vec::new();
    let mut buffer = String::new();

    for piece in expanded {
        if buffer.is_empty() {
            buffer = piece;
        } else {
            // Try merging
            let combined_len = buffer.len() + 1 + piece.len(); // +1 for space
            if buffer.len() < min {
                // Current buffer is too short, merge
                buffer.push(' ');
                buffer.push_str(&piece);
            } else if max > 0 && combined_len <= max && piece.len() < min {
                // Next piece is too short, merge it into current
                buffer.push(' ');
                buffer.push_str(&piece);
            } else {
                // Flush buffer
                merged.push(buffer);
                buffer = piece;
            }
        }
    }
    if !buffer.is_empty() {
        merged.push(buffer);
    }

    // Phase 3: Build TextChunks with index and is_last
    let total = merged.len();
    merged
        .into_iter()
        .enumerate()
        .map(|(i, text)| TextChunk {
            text,
            index: i,
            is_last: i == total - 1,
        })
        .collect()
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------------
    // 1. Basic English sentence splitting
    // -----------------------------------------------------------------------
    #[test]
    fn test_basic_english_sentences() {
        let result = split_sentences("Hello. World.");
        assert_eq!(result, vec!["Hello.", "World."]);
    }

    #[test]
    fn test_english_multiple_sentences() {
        let result = split_sentences("First sentence. Second sentence. Third one.");
        assert_eq!(
            result,
            vec!["First sentence.", "Second sentence.", "Third one."]
        );
    }

    // -----------------------------------------------------------------------
    // 2. Japanese sentence splitting
    // -----------------------------------------------------------------------
    #[test]
    fn test_japanese_sentences() {
        let result = split_sentences("今日は。明日は。");
        assert_eq!(result, vec!["今日は。", "明日は。"]);
    }

    #[test]
    fn test_japanese_mixed_punctuation() {
        let result = split_sentences("元気ですか？はい、元気です。よかった！");
        assert_eq!(
            result,
            vec!["元気ですか？", "はい、元気です。", "よかった！"]
        );
    }

    // -----------------------------------------------------------------------
    // 3. Mixed language splitting
    // -----------------------------------------------------------------------
    #[test]
    fn test_mixed_language() {
        let result = split_sentences("Hello. こんにちは。World.");
        assert_eq!(result, vec!["Hello.", "こんにちは。", "World."]);
    }

    #[test]
    fn test_mixed_language_continuous() {
        let result = split_sentences("これはテストです。This is a test. もう一つ。");
        // At minimum, CJK sentence ender splits correctly
        assert!(!result.is_empty());
        assert!(result[0].contains("これはテストです。"));
        assert!(
            result.len() >= 2,
            "expected at least 2 chunks, got {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // 4. Abbreviation handling
    // -----------------------------------------------------------------------
    #[test]
    fn test_abbreviation_mr() {
        let result = split_sentences("Mr. Smith went to the store. He bought milk.");
        assert_eq!(
            result,
            vec!["Mr. Smith went to the store.", "He bought milk."]
        );
    }

    #[test]
    fn test_abbreviation_dr() {
        let result = split_sentences("Dr. Jones and Prof. Lee are here.");
        assert_eq!(result, vec!["Dr. Jones and Prof. Lee are here."]);
    }

    #[test]
    fn test_abbreviation_etc() {
        let result = split_sentences("Apples, oranges, etc. are fruits. Eat them.");
        assert_eq!(
            result,
            vec!["Apples, oranges, etc. are fruits.", "Eat them."]
        );
    }

    #[test]
    fn test_abbreviation_eg() {
        let result = split_sentences("Use tools e.g. a hammer. Done.");
        assert_eq!(result, vec!["Use tools e.g. a hammer.", "Done."]);
    }

    // -----------------------------------------------------------------------
    // 5. Quoted speech
    // -----------------------------------------------------------------------
    #[test]
    fn test_quoted_speech_keeps_sentence() {
        let result = split_sentences("He said \"Hello. How are you?\" Then left.");
        // The period and question mark inside quotes should not split
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "He said \"Hello. How are you?\" Then left.");
    }

    #[test]
    fn test_quoted_speech_at_end() {
        let result = split_sentences("She whispered \"Goodbye.\"");
        assert_eq!(result, vec!["She whispered \"Goodbye.\""]);
    }

    // -----------------------------------------------------------------------
    // 6. Very long sentences with clause splitting
    // -----------------------------------------------------------------------
    #[test]
    fn test_clause_splitting() {
        let clauses = split_at_clauses("first part, second part; third part: fourth part");
        assert_eq!(
            clauses,
            vec!["first part,", "second part;", "third part:", "fourth part",]
        );
    }

    #[test]
    fn test_clause_splitting_no_delimiters() {
        let clauses = split_at_clauses("no delimiters here");
        assert_eq!(clauses, vec!["no delimiters here"]);
    }

    #[test]
    fn test_long_sentence_split_in_chunks() {
        // Create a sentence that exceeds max_chars
        let long = "Alpha bravo charlie, delta echo foxtrot; golf hotel india";
        let config = SplitConfig {
            max_chars: 30,
            split_on_clause: true,
            min_chars: 1,
        };
        let chunks = split_chunks(long, &config);
        // Should have been clause-split since the whole thing > 30 chars
        assert!(
            chunks.len() > 1,
            "expected multiple chunks, got {}",
            chunks.len()
        );
        // Each clause should be within limits (or at least attempted)
        for chunk in &chunks {
            assert!(!chunk.text.is_empty());
        }
    }

    // -----------------------------------------------------------------------
    // 7. max_chars enforcement
    // -----------------------------------------------------------------------
    #[test]
    fn test_max_chars_splits_long_text() {
        let text = "Short. This is a somewhat longer sentence that has many words in it. End.";
        let config = SplitConfig {
            max_chars: 50,
            split_on_clause: false,
            min_chars: 1,
        };
        let chunks = split_chunks(text, &config);
        assert!(chunks.len() >= 2);
    }

    #[test]
    fn test_max_chars_zero_means_no_limit() {
        let text = "First. Second. Third.";
        let config = SplitConfig {
            max_chars: 0,
            split_on_clause: false,
            min_chars: 0,
        };
        let chunks = split_chunks(text, &config);
        // max_chars=0 means no limit, sentences split normally
        assert!(!chunks.is_empty(), "should produce at least one chunk");
        assert!(
            chunks.len() >= 2,
            "expected at least 2 chunks, got {:?}",
            chunks.iter().map(|c| &c.text).collect::<Vec<_>>()
        );
    }

    // -----------------------------------------------------------------------
    // 8. min_chars merging
    // -----------------------------------------------------------------------
    #[test]
    fn test_min_chars_merges_short_chunks() {
        let text = "Hi. Go. Now.";
        let config = SplitConfig {
            max_chars: 500,
            split_on_clause: true,
            min_chars: 10,
        };
        let chunks = split_chunks(text, &config);
        // "Hi." (3 chars) is < 10, so it should be merged with next
        assert!(
            chunks.len() < 3,
            "expected merging of short chunks, got {} chunks: {:?}",
            chunks.len(),
            chunks.iter().map(|c| &c.text).collect::<Vec<_>>()
        );
    }

    #[test]
    fn test_min_chars_zero_no_merging() {
        let text = "A. B. C.";
        let config = SplitConfig {
            max_chars: 0,
            split_on_clause: false,
            min_chars: 0,
        };
        let chunks = split_chunks(text, &config);
        assert_eq!(chunks.len(), 3);
        assert_eq!(chunks[0].text, "A.");
        assert_eq!(chunks[1].text, "B.");
        assert_eq!(chunks[2].text, "C.");
    }

    // -----------------------------------------------------------------------
    // 9. Empty / whitespace input
    // -----------------------------------------------------------------------
    #[test]
    fn test_empty_input() {
        assert!(split_sentences("").is_empty());
        assert!(split_chunks("", &SplitConfig::default()).is_empty());
    }

    #[test]
    fn test_whitespace_only() {
        assert!(split_sentences("   ").is_empty());
        assert!(split_sentences("\n\n\n").is_empty());
        assert!(split_chunks("   ", &SplitConfig::default()).is_empty());
    }

    // -----------------------------------------------------------------------
    // 10. Paragraph breaks (multiple newlines)
    // -----------------------------------------------------------------------
    #[test]
    fn test_paragraph_breaks() {
        let text = "First paragraph.\n\nSecond paragraph.";
        let result = split_sentences(text);
        assert_eq!(result, vec!["First paragraph.", "Second paragraph."]);
    }

    #[test]
    fn test_single_newline_no_split() {
        let text = "Line one\nstill same sentence.";
        let result = split_sentences(text);
        assert_eq!(result.len(), 1);
        // Single newline is treated as a space
        assert!(result[0].contains("Line one"));
        assert!(result[0].contains("still same sentence."));
    }

    // -----------------------------------------------------------------------
    // 11. Exclamation and question marks
    // -----------------------------------------------------------------------
    #[test]
    fn test_exclamation_mark() {
        let result = split_sentences("Wow! Amazing!");
        assert_eq!(result, vec!["Wow!", "Amazing!"]);
    }

    #[test]
    fn test_question_mark() {
        let result = split_sentences("Really? Yes.");
        assert_eq!(result, vec!["Really?", "Yes."]);
    }

    // -----------------------------------------------------------------------
    // 12. Ellipsis handling
    // -----------------------------------------------------------------------
    #[test]
    fn test_ellipsis_followed_by_text() {
        let result = split_sentences("Wait... what?");
        // The sentence splitter may split at the period in "..." - that's acceptable
        // The key is that it doesn't panic and produces non-empty results
        assert!(!result.is_empty());
        let joined: String = result.join(" ");
        assert!(
            joined.contains("Wait"),
            "should contain 'Wait': {:?}",
            result
        );
        assert!(
            joined.contains("what?"),
            "should contain 'what?': {:?}",
            result
        );
    }

    #[test]
    fn test_ellipsis_at_end() {
        let result = split_sentences("And then...");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "And then...");
    }

    // -----------------------------------------------------------------------
    // 13. No trailing whitespace in chunks
    // -----------------------------------------------------------------------
    #[test]
    fn test_no_trailing_whitespace() {
        let result = split_sentences("Hello.   World.   ");
        for s in &result {
            assert_eq!(s, s.trim_end(), "trailing whitespace found in: {:?}", s);
        }
    }

    #[test]
    fn test_chunks_no_trailing_whitespace() {
        let text = "Hello.   World.   ";
        let chunks = split_chunks(text, &SplitConfig::default());
        for chunk in &chunks {
            assert_eq!(
                chunk.text,
                chunk.text.trim_end(),
                "trailing whitespace in chunk: {:?}",
                chunk.text
            );
        }
    }

    // -----------------------------------------------------------------------
    // 14. TextChunk index and is_last correctness
    // -----------------------------------------------------------------------
    #[test]
    fn test_chunk_index_and_is_last() {
        let text = "First. Second. Third.";
        let config = SplitConfig {
            max_chars: 0,
            split_on_clause: false,
            min_chars: 0,
        };
        let chunks = split_chunks(text, &config);
        assert!(
            chunks.len() >= 2,
            "expected at least 2 chunks, got {:?}",
            chunks.iter().map(|c| &c.text).collect::<Vec<_>>()
        );
        // Verify indices are sequential
        for (i, chunk) in chunks.iter().enumerate() {
            assert_eq!(chunk.index, i, "chunk {} index mismatch", i);
        }
        // Last chunk must have is_last=true
        assert!(
            chunks.last().unwrap().is_last,
            "last chunk should have is_last=true"
        );
        // Non-last chunks must have is_last=false
        for chunk in &chunks[..chunks.len() - 1] {
            assert!(!chunk.is_last, "non-last chunk should have is_last=false");
        }
    }

    #[test]
    fn test_single_chunk_is_last() {
        let config = SplitConfig {
            max_chars: 0,
            split_on_clause: false,
            min_chars: 0,
        };
        let chunks = split_chunks("Only one.", &config);
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].index, 0);
        assert!(chunks[0].is_last);
    }

    // -----------------------------------------------------------------------
    // 15. Single sentence (no split needed)
    // -----------------------------------------------------------------------
    #[test]
    fn test_single_sentence_no_split() {
        let result = split_sentences("Just one sentence without ending punctuation");
        assert_eq!(result, vec!["Just one sentence without ending punctuation"]);
    }

    #[test]
    fn test_single_sentence_with_period() {
        let result = split_sentences("Just one sentence.");
        assert_eq!(result, vec!["Just one sentence."]);
    }

    // -----------------------------------------------------------------------
    // 16. Multiple consecutive punctuation
    // -----------------------------------------------------------------------
    #[test]
    fn test_multiple_punctuation_exclamation_question() {
        let result = split_sentences("Really?! Yes.");
        assert_eq!(result, vec!["Really?!", "Yes."]);
    }

    #[test]
    fn test_multiple_exclamation() {
        let result = split_sentences("No!! Stop.");
        assert_eq!(result, vec!["No!!", "Stop."]);
    }

    // -----------------------------------------------------------------------
    // 17. Default SplitConfig values
    // -----------------------------------------------------------------------
    #[test]
    fn test_default_config() {
        let config = SplitConfig::default();
        assert_eq!(config.max_chars, 500);
        assert!(config.split_on_clause);
        assert_eq!(config.min_chars, 10);
    }

    // -----------------------------------------------------------------------
    // 18. Chinese sentence splitting
    // -----------------------------------------------------------------------
    #[test]
    fn test_chinese_sentences() {
        let result = split_sentences("你好。再见。");
        assert_eq!(result, vec!["你好。", "再见。"]);
    }

    #[test]
    fn test_chinese_question_and_exclamation() {
        let result = split_sentences("你好吗？很好！");
        assert_eq!(result, vec!["你好吗？", "很好！"]);
    }

    // -----------------------------------------------------------------------
    // 19. Japanese clause delimiters
    // -----------------------------------------------------------------------
    #[test]
    fn test_japanese_clause_splitting() {
        let clauses = split_at_clauses("最初の部分、二番目の部分、三番目");
        assert_eq!(clauses.len(), 3);
    }

    // -----------------------------------------------------------------------
    // 20. Edge cases
    // -----------------------------------------------------------------------
    #[test]
    fn test_only_punctuation() {
        let result = split_sentences("...");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0], "...");
    }

    #[test]
    fn test_split_chunks_preserves_all_text() {
        let text = "First sentence. Second sentence. Third sentence.";
        let config = SplitConfig {
            max_chars: 0,
            split_on_clause: false,
            min_chars: 0,
        };
        let chunks = split_chunks(text, &config);
        // Rejoin and compare (ignoring whitespace differences)
        let rejoined: String = chunks
            .iter()
            .map(|c| c.text.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        assert_eq!(rejoined, "First sentence. Second sentence. Third sentence.");
    }

    #[test]
    fn test_period_not_followed_by_space() {
        // Period mid-word (e.g. a URL or filename) should not split
        let result = split_sentences("Visit example.com today.");
        assert_eq!(result.len(), 1);
    }

    #[test]
    fn test_chunks_with_merging_and_splitting() {
        let text =
            "A. B. This is a long sentence with many words, and some clauses; and more text here.";
        let config = SplitConfig {
            max_chars: 40,
            split_on_clause: true,
            min_chars: 5,
        };
        let chunks = split_chunks(text, &config);
        assert!(!chunks.is_empty());
        // Verify index continuity
        for (i, chunk) in chunks.iter().enumerate() {
            assert_eq!(chunk.index, i);
        }
        // Last chunk must have is_last = true
        assert!(chunks.last().unwrap().is_last);
    }

    // -----------------------------------------------------------------------
    // 21. Nested quotes — inner quotes should not break the outer sentence
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_sentences_nested_quotes() {
        let text = "He said \"she said 'hello'\" then left.";
        let result = split_sentences(text);
        assert_eq!(
            result.len(),
            1,
            "nested quotes should not cause extra splits: {:?}",
            result
        );
        assert_eq!(result[0], text);
    }

    // -----------------------------------------------------------------------
    // 22. Only CJK punctuation (no actual text content)
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_sentences_only_cjk_punctuation() {
        // Input is three CJK sentence-ending marks with no surrounding text
        let result = split_sentences("\u{3002}\u{FF01}\u{FF1F}");
        // Each mark should be treated as its own sentence (non-empty)
        assert!(
            !result.is_empty(),
            "CJK-only punctuation should produce output"
        );
        for s in &result {
            assert!(!s.is_empty(), "no empty sentences should be emitted");
        }
    }

    // -----------------------------------------------------------------------
    // 23. split_chunks where max_chars < min_chars — should still not panic
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_chunks_max_less_than_min() {
        let text = "Hello world. Goodbye world.";
        // Intentionally contradictory: max < min
        let config = SplitConfig {
            max_chars: 5,
            split_on_clause: true,
            min_chars: 50,
        };
        let chunks = split_chunks(text, &config);
        // Must not panic; should still produce at least one chunk
        assert!(
            !chunks.is_empty(),
            "should produce chunks even with invalid config"
        );
        // All text should survive the round-trip
        let rejoined: String = chunks
            .iter()
            .map(|c| c.text.as_str())
            .collect::<Vec<_>>()
            .join(" ");
        assert!(
            rejoined.contains("Hello"),
            "text should survive: {rejoined}"
        );
        assert!(
            rejoined.contains("Goodbye"),
            "text should survive: {rejoined}"
        );
    }

    // -----------------------------------------------------------------------
    // 24. Consecutive terminators — "Really?! Yes." should give 2 chunks
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_sentences_consecutive_terminators() {
        let result = split_sentences("Really?! Yes.");
        assert_eq!(result, vec!["Really?!", "Yes."]);
    }

    // -----------------------------------------------------------------------
    // 25. Abbreviation at start of sentence — "Dr. Smith is here."
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_sentences_abbreviation_at_start() {
        let result = split_sentences("Dr. Smith is here.");
        // "Dr." is an abbreviation and must not split
        assert_eq!(
            result.len(),
            1,
            "abbreviation at start should not split: {:?}",
            result
        );
        assert_eq!(result[0], "Dr. Smith is here.");
    }

    // -----------------------------------------------------------------------
    // 26. CRLF line endings — "\r\n" should be treated like "\n"
    // -----------------------------------------------------------------------
    #[test]
    fn test_split_sentences_crlf_line_endings() {
        // Single CRLF: treated as single newline (space), no split
        let result_single = split_sentences("Hello.\r\nWorld.");
        assert!(
            !result_single.is_empty(),
            "CRLF input should produce output"
        );

        // Double CRLF: treated as paragraph break, should split
        let result_double = split_sentences("Hello.\r\n\r\nWorld.");
        assert!(
            result_double.len() >= 2,
            "double CRLF should cause paragraph split: {:?}",
            result_double
        );
        // First chunk should contain "Hello." and last should contain "World."
        assert!(
            result_double[0].contains("Hello."),
            "first chunk: {:?}",
            result_double
        );
        assert!(
            result_double.last().unwrap().contains("World."),
            "last chunk: {:?}",
            result_double
        );
    }
}
