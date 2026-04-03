//! Chinese (Mandarin) phonemizer for Piper TTS.
//!
//! Converts Chinese text to IPA phonemes via pinyin intermediate representation.
//! Uses pypinyin-format JSON dictionaries for character-to-pinyin conversion,
//! then applies normalization, tone sandhi, and IPA mapping identical to the
//! Python and C++ pipelines.
//!
//! No runtime Python dependency — dictionaries are loaded from JSON at startup.

use std::collections::{HashMap, HashSet};
use std::path::Path;
use std::sync::{LazyLock, OnceLock};

use super::token_map::token_to_pua;
use super::{Phonemizer, ProsodyFeature, ProsodyInfo};
use crate::config::PhonemeIdMap;
use crate::error::PiperError;

// =========================================================================
// IPA token strings (matching Python _INITIAL_TO_IPA / _FINAL_TO_IPA)
// =========================================================================

/// Pinyin initial -> IPA string mapping.
/// In Mandarin phonology: b=[p], p=[p\u{02b0}], d=[t], t=[t\u{02b0}], etc.
static INITIAL_TO_IPA: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
    [
        ("b", "p"),
        ("p", "p\u{02b0}"),
        ("m", "m"),
        ("f", "f"),
        ("d", "t"),
        ("t", "t\u{02b0}"),
        ("n", "n"),
        ("l", "l"),
        ("g", "k"),
        ("k", "k\u{02b0}"),
        ("h", "x"),
        ("j", "t\u{0255}"),
        ("q", "t\u{0255}\u{02b0}"),
        ("x", "\u{0255}"),
        ("zh", "t\u{0282}"),
        ("ch", "t\u{0282}\u{02b0}"),
        ("sh", "\u{0282}"),
        ("r", "\u{027b}"),
        ("z", "ts"),
        ("c", "ts\u{02b0}"),
        ("s", "s"),
    ]
    .into_iter()
    .collect()
});

/// Pinyin final -> IPA string mapping (compound finals as single tokens).
static FINAL_TO_IPA: LazyLock<HashMap<&'static str, &'static str>> = LazyLock::new(|| {
    [
        // Simple vowels
        ("a", "a"),
        ("o", "o"),
        ("e", "\u{0264}"), // ɤ close-mid back unrounded
        ("i", "i"),
        ("u", "u"),
        ("\u{00fc}", "y_vowel"), // ü -> y_vowel
        ("v", "y_vowel"),
        // Diphthongs
        ("ai", "a\u{026a}"), // aɪ
        ("ei", "e\u{026a}"), // eɪ
        ("ao", "a\u{028a}"), // aʊ
        ("ou", "o\u{028a}"), // oʊ
        // Nasal finals
        ("an", "an"),
        ("en", "\u{0259}n"),         // ən
        ("ang", "a\u{014b}"),        // aŋ
        ("eng", "\u{0259}\u{014b}"), // əŋ
        ("ong", "u\u{014b}"),        // uŋ
        // Retroflex final
        ("er", "\u{025a}"), // ɚ
        // i-compound finals (齐齿呼)
        ("ia", "ia"),
        ("ie", "i\u{025b}"),   // iɛ
        ("iao", "ia\u{028a}"), // iaʊ
        ("iu", "iou"),
        ("iou", "iou"),
        ("ian", "i\u{025b}n"), // iɛn
        ("in", "in"),
        ("iang", "ia\u{014b}"), // iaŋ
        ("ing", "i\u{014b}"),   // iŋ
        ("iong", "iu\u{014b}"), // iuŋ
        // u-compound finals (合口呼)
        ("ua", "ua"),
        ("uo", "uo"),
        ("uai", "ua\u{026a}"), // uaɪ
        ("ui", "ue\u{026a}"),  // ueɪ
        ("uei", "ue\u{026a}"), // ueɪ
        ("uan", "uan"),
        ("un", "u\u{0259}n"),          // uən
        ("uen", "u\u{0259}n"),         // uən
        ("uang", "ua\u{014b}"),        // uaŋ
        ("ueng", "u\u{0259}\u{014b}"), // uəŋ
        // ü-compound finals (撮口呼) — using actual ü char
        ("\u{00fc}e", "y\u{025b}"), // yɛ
        ("ve", "y\u{025b}"),
        ("\u{00fc}an", "y\u{025b}n"), // yɛn
        ("van", "y\u{025b}n"),
        ("\u{00fc}n", "yn"), // yn
        ("vn", "yn"),
        // Syllabic consonants (internal keys from split_pinyin)
        ("-i_retroflex", "\u{027b}\u{0329}"), // ɻ̩
        ("-i_alveolar", "\u{0268}"),          // ɨ
    ]
    .into_iter()
    .collect()
});

/// Ordered list of consonant initials (two-char first for prefix matching).
const INITIALS_ORDER: &[&str] = &[
    "zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r",
    "z", "c", "s",
];

static RETROFLEX_INITIALS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| ["zh", "ch", "sh", "r"].into_iter().collect());

static ALVEOLAR_INITIALS: LazyLock<HashSet<&'static str>> =
    LazyLock::new(|| ["z", "c", "s"].into_iter().collect());

// =========================================================================
// Chinese punctuation mapping (fullwidth -> ASCII equivalent)
// =========================================================================

fn map_zh_punct(cp: char) -> Option<char> {
    match cp {
        '\u{3002}' => Some('.'),  // 。
        '\u{ff0c}' => Some(','),  // ，
        '\u{ff01}' => Some('!'),  // ！
        '\u{ff1f}' => Some('?'),  // ？
        '\u{3001}' => Some(','),  // 、
        '\u{ff1b}' => Some(';'),  // ；
        '\u{ff1a}' => Some(':'),  // ：
        '\u{2026}' => Some('.'),  // …
        '\u{2014}' => Some(','),  // —
        '\u{201c}' => Some('"'),  // "
        '\u{201d}' => Some('"'),  // "
        '\u{2018}' => Some('\''), // '
        '\u{2019}' => Some('\''), // '
        _ => None,
    }
}

fn is_zh_punctuation(cp: char) -> bool {
    matches!(
        cp,
        ',' | '.'
            | ';'
            | ':'
            | '!'
            | '?'
            | '\u{3002}'
            | '\u{ff0c}'
            | '\u{ff01}'
            | '\u{ff1f}'
            | '\u{3001}'
            | '\u{ff1b}'
            | '\u{ff1a}'
            | '\u{201c}'
            | '\u{201d}'
            | '\u{2018}'
            | '\u{2019}'
            | '\u{2026}'
            | '\u{2014}'
    )
}

// =========================================================================
// CJK detection
// =========================================================================

fn is_cjk(cp: char) -> bool {
    let c = cp as u32;
    (0x4E00..=0x9FFF).contains(&c) || (0x3400..=0x4DBF).contains(&c)
}

// =========================================================================
// Pinyin normalization
// =========================================================================

/// Normalize pinyin y/w conventions and v->ü to canonical form.
fn normalize_pinyin(py: &str) -> String {
    // v -> ü
    let s = py.replace('v', "\u{00fc}");

    // y- initial
    if let Some(rest) = s.strip_prefix("yu") {
        if rest.is_empty() {
            return "\u{00fc}".to_string();
        }
        return format!("\u{00fc}{rest}");
    }
    if let Some(rest) = s.strip_prefix('y') {
        if rest.starts_with('i') {
            return rest.to_string(); // yi->i, yin->in, ying->ing
        }
        return format!("i{rest}"); // ya->ia, ye->ie, yan->ian
    }

    // w- initial
    if let Some(rest) = s.strip_prefix('w') {
        if rest.starts_with('u') {
            return rest.to_string(); // wu->u
        }
        return format!("u{rest}"); // wa->ua, wo->uo, wai->uai
    }

    s
}

// =========================================================================
// Split normalized pinyin into (initial, final)
// =========================================================================

fn split_pinyin(pinyin: &str) -> (&'static str, String) {
    for &init in INITIALS_ORDER {
        if let Some(rest) = pinyin.strip_prefix(init) {
            let mut final_part = rest.to_string();

            // Syllabic consonant: bare "i" after retroflex or alveolar initials
            if final_part == "i" {
                if RETROFLEX_INITIALS.contains(init) {
                    return (init, "-i_retroflex".to_string());
                }
                if ALVEOLAR_INITIALS.contains(init) {
                    return (init, "-i_alveolar".to_string());
                }
            }

            // After j/q/x, u represents ü
            if matches!(init, "j" | "q" | "x") && final_part.starts_with('u') {
                final_part = format!("\u{00fc}{}", &final_part[1..]);
            }

            return (init, final_part);
        }
    }

    // No consonant initial
    ("", pinyin.to_string())
}

// =========================================================================
// Pinyin -> IPA conversion (single syllable)
// =========================================================================

/// Convert a single pinyin syllable (without tone number) to IPA tokens.
fn pinyin_to_ipa(syllable: &str, tone: u8) -> Vec<String> {
    let (initial, final_part) = split_pinyin(syllable);
    let mut tokens: Vec<String> = Vec::new();

    // Initial consonant
    if !initial.is_empty()
        && let Some(&ipa) = INITIAL_TO_IPA.get(initial)
    {
        tokens.push(ipa.to_string());
    }

    // Final vowel(s) as a single compound token
    if !final_part.is_empty() {
        if let Some(&ipa) = FINAL_TO_IPA.get(final_part.as_str()) {
            tokens.push(ipa.to_string());
        } else {
            // Fallback: decompose unknown finals character by character
            for ch in final_part.chars() {
                if ch.is_ascii_lowercase() {
                    let ch_str = ch.to_string();
                    if let Some(&ipa) = FINAL_TO_IPA.get(ch_str.as_str()) {
                        tokens.push(ipa.to_string());
                    } else {
                        tokens.push(ch_str);
                    }
                }
            }
        }
    }

    // Tone marker
    if (1..=5).contains(&tone) {
        tokens.push(format!("tone{tone}"));
    }

    tokens
}

// =========================================================================
// Tone sandhi
// =========================================================================

/// Apply basic Mandarin tone sandhi rules.
///
/// Rules:
///   1. T3 + T3 -> T2 + T3
///   2. 一(yi, normalized to "i") T1 + T4 -> T2 + T4
///   3. 一(yi) T1 + T1/T2/T3 -> T4 + Tn
///   4. 不(bu) T4 + T4 -> T2 + T4
fn apply_tone_sandhi(syllable_tones: &mut [(String, u8)]) {
    let n = syllable_tones.len();
    for i in 0..n.saturating_sub(1) {
        let tone_i = syllable_tones[i].1;
        let tone_next = syllable_tones[i + 1].1;

        // Rule 1: T3 + T3 -> T2 + T3
        if tone_i == 3 && tone_next == 3 {
            syllable_tones[i].1 = 2;
            continue;
        }

        // Rule 2 & 3: yi tone sandhi
        if syllable_tones[i].0 == "i" && tone_i == 1 {
            if tone_next == 4 {
                syllable_tones[i].1 = 2; // T1 -> T2 before T4
            } else if (1..=3).contains(&tone_next) {
                syllable_tones[i].1 = 4; // T1 -> T4 before T1/T2/T3
            }
            continue;
        }

        // Rule 4: bu T4 + T4 -> T2 + T4
        if syllable_tones[i].0 == "bu" && tone_i == 4 && tone_next == 4 {
            syllable_tones[i].1 = 2;
        }
    }
}

// =========================================================================
// Helper: extract tone digit from pinyin syllable string
// =========================================================================

/// Extract tone number (1-5) from the end of a pinyin syllable.
/// Returns (base_syllable, tone). Default tone is 5 (neutral).
fn extract_tone(syllable: &str) -> (&str, u8) {
    if let Some(last) = syllable.bytes().last()
        && (b'1'..=b'5').contains(&last)
    {
        return (&syllable[..syllable.len() - 1], last - b'0');
    }
    (syllable, 5)
}

/// For a single-char dict entry that may have comma-separated alternatives,
/// return the first alternative.
fn first_alternative(s: &str) -> &str {
    s.split(',').next().unwrap_or(s)
}

// =========================================================================
// PUA mapping for multi-char IPA tokens
// =========================================================================

/// Map multi-character IPA tokens to single PUA codepoints where possible.
fn map_sequence(tokens: Vec<String>) -> Vec<String> {
    tokens
        .into_iter()
        .map(|t| {
            if let Some(pua_char) = token_to_pua(&t) {
                pua_char.to_string()
            } else {
                t
            }
        })
        .collect()
}

// =========================================================================
// Word boundary info for prosody
// =========================================================================

/// Build word position info from contiguous CJK character groups.
/// Returns a map from character index -> (syllable_position, word_length).
fn build_word_info(text: &str) -> HashMap<usize, (i32, i32)> {
    let mut info = HashMap::new();
    let mut group_indices: Vec<usize> = Vec::new();

    for (i, ch) in text.chars().enumerate() {
        if is_cjk(ch) {
            group_indices.push(i);
        } else if !group_indices.is_empty() {
            let word_len = group_indices.len() as i32;
            for (pos, &idx) in group_indices.iter().enumerate() {
                info.insert(idx, (pos as i32 + 1, word_len));
            }
            group_indices.clear();
        }
    }

    // Handle trailing group
    if !group_indices.is_empty() {
        let word_len = group_indices.len() as i32;
        for (pos, &idx) in group_indices.iter().enumerate() {
            info.insert(idx, (pos as i32 + 1, word_len));
        }
    }

    info
}

// =========================================================================
// CharPinyin — intermediate representation during text-to-pinyin
// =========================================================================

struct CharPinyin {
    _codepoint: char,
    is_chinese: bool,
    normalized: String,
    tone: u8,
}

// =========================================================================
// Text -> pinyin conversion using dictionaries
// =========================================================================

/// Attempt longest-prefix phrase match starting at position `pos`.
fn phrase_match(
    chars: &[char],
    pos: usize,
    phrase_dict: &HashMap<String, Vec<String>>,
) -> Option<(usize, Vec<String>)> {
    let max_len = std::cmp::min(chars.len() - pos, 8);
    for len in (2..=max_len).rev() {
        let key: String = chars[pos..pos + len].iter().collect();
        if let Some(pinyins) = phrase_dict.get(&key) {
            return Some((len, pinyins.clone()));
        }
    }
    None
}

/// Convert text to a list of CharPinyin entries using the dictionaries.
fn text_to_pinyin(
    text: &str,
    single_dict: &HashMap<char, String>,
    phrase_dict: &HashMap<String, Vec<String>>,
) -> Vec<CharPinyin> {
    let chars: Vec<char> = text.chars().collect();
    let n = chars.len();
    let mut result = Vec::new();
    let mut i = 0;

    while i < n {
        let cp = chars[i];

        if !is_cjk(cp) {
            result.push(CharPinyin {
                _codepoint: cp,
                is_chinese: false,
                normalized: String::new(),
                tone: 0,
            });
            i += 1;
            continue;
        }

        // Try phrase match first
        if let Some((match_len, pinyins)) = phrase_match(&chars, i, phrase_dict) {
            for j in 0..match_len {
                let (base, tone) = if j < pinyins.len() {
                    extract_tone(&pinyins[j])
                } else {
                    ("", 5)
                };
                let normalized = normalize_pinyin(base);
                result.push(CharPinyin {
                    _codepoint: chars[i + j],
                    is_chinese: true,
                    normalized,
                    tone,
                });
            }
            i += match_len;
            continue;
        }

        // Single character lookup
        if let Some(raw) = single_dict.get(&cp) {
            let first = first_alternative(raw);
            let (base, tone) = extract_tone(first);
            let normalized = normalize_pinyin(base);
            result.push(CharPinyin {
                _codepoint: cp,
                is_chinese: true,
                normalized,
                tone,
            });
        } else {
            // Unknown CJK character
            result.push(CharPinyin {
                _codepoint: cp,
                is_chinese: false,
                normalized: String::new(),
                tone: 0,
            });
        }
        i += 1;
    }

    result
}

// =========================================================================
// Group consecutive Chinese characters for tone sandhi
// =========================================================================

fn apply_tone_sandhi_to_chars(chars: &mut [CharPinyin]) {
    let n = chars.len();
    let mut i = 0;

    while i < n {
        if !chars[i].is_chinese {
            i += 1;
            continue;
        }

        // Find the end of this consecutive Chinese character group
        let group_start = i;
        while i < n && chars[i].is_chinese {
            i += 1;
        }
        let group_end = i;

        if group_end - group_start < 2 {
            continue;
        }

        // Build (syllable, tone) vector for this group
        let mut st: Vec<(String, u8)> = chars[group_start..group_end]
            .iter()
            .map(|c| (c.normalized.clone(), c.tone))
            .collect();

        apply_tone_sandhi(&mut st);

        // Write back
        for (j, (_, tone)) in st.into_iter().enumerate() {
            chars[group_start + j].tone = tone;
        }
    }
}

// =========================================================================
// Core phonemization
// =========================================================================

/// Phonemize Chinese text to IPA tokens with prosody info.
///
/// Pipeline:
///   1. Text -> pinyin (dictionary lookup with phrase matching)
///   2. Pinyin normalization (y/w stripping, v->u-umlaut)
///   3. Tone sandhi (T3+T3, yi, bu rules)
///   4. Pinyin -> IPA conversion (initial/final split, compound finals)
///   5. Erhua handling
///   6. Multi-char IPA -> PUA codepoint mapping
fn phonemize_chinese_internal(
    text: &str,
    single_dict: &HashMap<char, String>,
    phrase_dict: &HashMap<String, Vec<String>>,
) -> (Vec<String>, Vec<Option<ProsodyInfo>>) {
    let word_info = build_word_info(text);

    // Step 1: Text -> pinyin
    let mut char_pinyins = text_to_pinyin(text, single_dict, phrase_dict);

    // Step 2: Tone sandhi
    apply_tone_sandhi_to_chars(&mut char_pinyins);

    // Step 3: Generate phonemes
    let mut phonemes: Vec<String> = Vec::new();
    let mut prosody_list: Vec<Option<ProsodyInfo>> = Vec::new();

    let text_chars: Vec<char> = text.chars().collect();

    for (char_idx, cpdata) in char_pinyins.iter().enumerate() {
        let ch = if char_idx < text_chars.len() {
            text_chars[char_idx]
        } else {
            break;
        };

        if !cpdata.is_chinese {
            // Non-Chinese character passthrough
            if let Some(mapped) = map_zh_punct(ch) {
                phonemes.push(mapped.to_string());
                prosody_list.push(None);
            } else if is_zh_punctuation(ch) {
                phonemes.push(ch.to_string());
                prosody_list.push(None);
            } else if ch.is_whitespace() {
                phonemes.push(" ".to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 0,
                }));
            } else if ch.is_ascii_digit() || ch.is_alphabetic() {
                phonemes.push(ch.to_string());
                prosody_list.push(Some(ProsodyInfo {
                    a1: 0,
                    a2: 0,
                    a3: 1,
                }));
            }
            // Other characters: skip
            continue;
        }

        // Chinese character: convert pinyin to IPA
        let mut normalized = cpdata.normalized.clone();
        let tone = cpdata.tone;

        // Erhua handling: trailing 'r' that is not standalone "er"
        let has_erhua = normalized.len() > 1 && normalized != "er" && normalized.ends_with('r');
        if has_erhua {
            normalized.pop(); // remove trailing 'r'
        }

        // Convert to IPA tokens
        let mut ipa_tokens = pinyin_to_ipa(&normalized, tone);

        // Insert erhua token before tone marker
        if has_erhua && !ipa_tokens.is_empty() {
            let last_is_tone = ipa_tokens
                .last()
                .map(|t| t.starts_with("tone"))
                .unwrap_or(false);

            if last_is_tone {
                let len = ipa_tokens.len();
                ipa_tokens.insert(len - 1, "\u{025a}".to_string()); // ɚ
            } else {
                ipa_tokens.push("\u{025a}".to_string());
            }
        }

        // Prosody: a1=tone, a2=position in word, a3=word length
        let (syl_pos, word_len) = word_info.get(&char_idx).copied().unwrap_or((1, 1));
        let syl_prosody = ProsodyInfo {
            a1: tone as i32,
            a2: syl_pos,
            a3: word_len,
        };

        for token in &ipa_tokens {
            phonemes.push(token.clone());
            prosody_list.push(Some(syl_prosody));
        }
    }

    // Map multi-character tokens to PUA codepoints
    let mapped = map_sequence(phonemes);
    (mapped, prosody_list)
}

// =========================================================================
// Dictionary loading
// =========================================================================

/// Try to load a dictionary from a bincode cache file.
///
/// Returns `Some(dict)` if the `.bincode` file exists, is newer than the
/// source JSON file, and deserializes successfully. Returns `None` otherwise,
/// allowing the caller to fall back to JSON parsing.
fn try_load_bincode_cache<T: serde::de::DeserializeOwned>(json_path: &Path) -> Option<T> {
    let bincode_path = json_path.with_extension("json.bincode");
    if !bincode_path.exists() {
        return None;
    }
    let json_modified = std::fs::metadata(json_path).ok()?.modified().ok()?;
    let bin_modified = std::fs::metadata(&bincode_path).ok()?.modified().ok()?;
    if bin_modified < json_modified {
        return None;
    }
    let bytes = std::fs::read(&bincode_path).ok()?;
    bincode::deserialize(&bytes).ok()
}

/// Save a dictionary to a bincode cache file next to the JSON source.
///
/// Failures are silently ignored — the JSON fallback will always work.
fn save_bincode_cache<T: serde::Serialize>(json_path: &Path, dict: &T) {
    let bincode_path = json_path.with_extension("json.bincode");
    if let Ok(bytes) = bincode::serialize(dict) {
        let _ = std::fs::write(&bincode_path, bytes);
    }
}

/// Load pinyin single-char dictionary from JSON.
///
/// JSON format: `{ "19968": "yi1", "19969": "ding1,zheng4", ... }`
/// Keys are codepoint values as strings.
fn load_single_char_dict(path: &Path) -> Result<HashMap<char, String>, PiperError> {
    // Fast path: bincode cache
    if let Some(dict) = try_load_bincode_cache::<HashMap<char, String>>(path) {
        tracing::info!("ZH single-char dict loaded from bincode cache");
        return Ok(dict);
    }

    let content = std::fs::read_to_string(path).map_err(|_| PiperError::DictionaryLoad {
        path: path.display().to_string(),
    })?;

    let json: serde_json::Value =
        serde_json::from_str(&content).map_err(|e| PiperError::DictionaryLoad {
            path: format!("{}: {}", path.display(), e),
        })?;

    let obj = json.as_object().ok_or_else(|| PiperError::DictionaryLoad {
        path: format!("{}: expected JSON object", path.display()),
    })?;

    let mut dict = HashMap::with_capacity(obj.len());
    for (key, val) in obj {
        let codepoint: u32 = match key.parse() {
            Ok(cp) => cp,
            Err(_) => continue,
        };
        let ch = match char::from_u32(codepoint) {
            Some(c) => c,
            None => continue,
        };

        let pinyin = if let Some(s) = val.as_str() {
            s.to_string()
        } else if let Some(arr) = val.as_array() {
            // Array format: take first element
            arr.first()
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string()
        } else {
            continue;
        };

        if !pinyin.is_empty() {
            dict.insert(ch, pinyin);
        }
    }

    // Write bincode cache for next time (best-effort).
    save_bincode_cache(path, &dict);
    tracing::info!("ZH single-char dict loaded from JSON, bincode cache saved");

    Ok(dict)
}

/// Load pinyin phrase dictionary from JSON.
///
/// JSON format supports:
///   - string value: `"一个": "yi2 ge4"`
///   - array of arrays: `"一个": [["yi2"], ["ge4"]]` (pypinyin format)
///   - array of strings: `"一个": ["yi2", "ge4"]`
fn load_phrase_dict(path: &Path) -> Result<HashMap<String, Vec<String>>, PiperError> {
    // Fast path: bincode cache
    if let Some(dict) = try_load_bincode_cache::<HashMap<String, Vec<String>>>(path) {
        tracing::info!("ZH phrase dict loaded from bincode cache");
        return Ok(dict);
    }

    let content = std::fs::read_to_string(path).map_err(|_| PiperError::DictionaryLoad {
        path: path.display().to_string(),
    })?;

    let json: serde_json::Value =
        serde_json::from_str(&content).map_err(|e| PiperError::DictionaryLoad {
            path: format!("{}: {}", path.display(), e),
        })?;

    let obj = json.as_object().ok_or_else(|| PiperError::DictionaryLoad {
        path: format!("{}: expected JSON object", path.display()),
    })?;

    let mut dict = HashMap::with_capacity(obj.len());
    for (key, val) in obj {
        let pinyins = if let Some(s) = val.as_str() {
            // Space-separated pinyin string
            s.split_whitespace().map(|s| s.to_string()).collect()
        } else if let Some(arr) = val.as_array() {
            // Array of arrays or array of strings
            let mut py_list = Vec::new();
            for item in arr {
                if let Some(s) = item.as_str() {
                    py_list.push(s.to_string());
                } else if let Some(inner_arr) = item.as_array()
                    && let Some(first) = inner_arr.first().and_then(|v| v.as_str())
                {
                    py_list.push(first.to_string());
                }
            }
            py_list
        } else {
            continue;
        };

        if !pinyins.is_empty() {
            dict.insert(key.clone(), pinyins);
        }
    }

    // Write bincode cache for next time (best-effort).
    save_bincode_cache(path, &dict);
    tracing::info!("ZH phrase dict loaded from JSON, bincode cache saved");

    Ok(dict)
}

// =========================================================================
// Global Chinese dictionary cache
//
// The pinyin dictionaries (single-char ~20K entries, phrase ~100K entries)
// are loaded and parsed once, then shared across all `ChinesePhonemizer`
// instances via `&'static` references.
// =========================================================================

/// Pair of (single_char_dict, phrase_dict).
type ZhDictPair = (HashMap<char, String>, HashMap<String, Vec<String>>);

/// Cached pair of (single_char_dict, phrase_dict).
static ZH_DICT_CACHE: OnceLock<ZhDictPair> = OnceLock::new();

// =========================================================================
// ChinesePhonemizer
// =========================================================================

/// Chinese (Mandarin) phonemizer.
///
/// Loads pypinyin-format JSON dictionaries for character-to-pinyin conversion
/// and converts to IPA phonemes with PUA codepoint mapping. Dictionaries
/// are loaded once and cached globally via `OnceLock`, so creating multiple
/// instances is cheap.
pub struct ChinesePhonemizer {
    dict: ZhDictRef,
}

/// Internal enum to hold either static references to the globally cached
/// dictionaries or owned dictionaries (for tests).
enum ZhDictRef {
    /// References to the `OnceLock`-cached dictionaries.
    Static {
        single: &'static HashMap<char, String>,
        phrase: &'static HashMap<String, Vec<String>>,
    },
    /// Owned dictionaries, used by `from_dicts` for testing.
    Owned {
        single: HashMap<char, String>,
        phrase: HashMap<String, Vec<String>>,
    },
}

impl ZhDictRef {
    fn single(&self) -> &HashMap<char, String> {
        match self {
            ZhDictRef::Static { single, .. } => single,
            ZhDictRef::Owned { single, .. } => single,
        }
    }

    fn phrase(&self) -> &HashMap<String, Vec<String>> {
        match self {
            ZhDictRef::Static { phrase, .. } => phrase,
            ZhDictRef::Owned { phrase, .. } => phrase,
        }
    }
}

impl ChinesePhonemizer {
    /// Create a new `ChinesePhonemizer` by loading dictionaries from JSON files.
    ///
    /// The dictionaries are loaded and parsed only on the first call;
    /// subsequent calls reuse the cached data.
    ///
    /// # Arguments
    /// * `single_char_path` - Path to `pinyin_single.json`
    /// * `phrase_path` - Path to `pinyin_phrases.json`
    pub fn new(single_char_path: &Path, phrase_path: &Path) -> Result<Self, PiperError> {
        let (single, phrase) = ZH_DICT_CACHE.get_or_init(|| {
            let s = load_single_char_dict(single_char_path)
                .expect("pinyin single-char dictionary load failed");
            let p = load_phrase_dict(phrase_path).expect("pinyin phrase dictionary load failed");
            (s, p)
        });

        Ok(Self {
            dict: ZhDictRef::Static { single, phrase },
        })
    }

    /// Create a `ChinesePhonemizer` from pre-loaded dictionaries.
    ///
    /// Does not affect or use the global cache.
    pub fn from_dicts(
        single_dict: HashMap<char, String>,
        phrase_dict: HashMap<String, Vec<String>>,
    ) -> Self {
        Self {
            dict: ZhDictRef::Owned {
                single: single_dict,
                phrase: phrase_dict,
            },
        }
    }
}

impl Phonemizer for ChinesePhonemizer {
    fn phonemize_with_prosody(
        &self,
        text: &str,
    ) -> Result<(Vec<String>, Vec<Option<ProsodyInfo>>), PiperError> {
        Ok(phonemize_chinese_internal(
            text,
            self.dict.single(),
            self.dict.phrase(),
        ))
    }

    fn get_phoneme_id_map(&self) -> Option<&PhonemeIdMap> {
        // Chinese uses the phoneme_id_map from config.json
        None
    }

    fn post_process_ids(
        &self,
        ids: Vec<i64>,
        prosody: Vec<Option<ProsodyFeature>>,
        id_map: &PhonemeIdMap,
    ) -> (Vec<i64>, Vec<Option<ProsodyFeature>>) {
        // BOS + intersperse padding + EOS (same as English default)
        let bos = id_map
            .get("^")
            .and_then(|v| v.first().copied())
            .unwrap_or(1);
        let eos = id_map
            .get("$")
            .and_then(|v| v.first().copied())
            .unwrap_or(2);
        let pad = id_map
            .get("_")
            .and_then(|v| v.first().copied())
            .unwrap_or(0);

        let mut out_ids = Vec::with_capacity(ids.len() * 2 + 2);
        let mut out_prosody = Vec::with_capacity(ids.len() * 2 + 2);

        // BOS
        out_ids.push(bos);
        out_prosody.push(None);

        for (i, &id) in ids.iter().enumerate() {
            if i > 0 {
                // Intersperse padding between tokens
                out_ids.push(pad);
                out_prosody.push(None);
            }
            out_ids.push(id);
            out_prosody.push(prosody.get(i).cloned().unwrap_or(None));
        }

        // EOS
        out_ids.push(eos);
        out_prosody.push(None);

        (out_ids, out_prosody)
    }

    fn language_code(&self) -> &str {
        "zh"
    }
}

// =========================================================================
// Unit tests
// =========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // --- Helper: create a minimal phonemizer with inline dicts ---
    fn make_phonemizer(singles: &[(char, &str)], phrases: &[(&str, &[&str])]) -> ChinesePhonemizer {
        let single_dict: HashMap<char, String> = singles
            .iter()
            .map(|(ch, py)| (*ch, py.to_string()))
            .collect();
        let phrase_dict: HashMap<String, Vec<String>> = phrases
            .iter()
            .map(|(k, v)| (k.to_string(), v.iter().map(|s| s.to_string()).collect()))
            .collect();
        ChinesePhonemizer::from_dicts(single_dict, phrase_dict)
    }

    // ===== 1. Pinyin normalization =====

    #[test]
    fn test_normalize_pinyin_y_initial() {
        assert_eq!(normalize_pinyin("yi"), "i");
        assert_eq!(normalize_pinyin("yin"), "in");
        assert_eq!(normalize_pinyin("ying"), "ing");
        assert_eq!(normalize_pinyin("ya"), "ia");
        assert_eq!(normalize_pinyin("ye"), "ie");
        assert_eq!(normalize_pinyin("yan"), "ian");
        assert_eq!(normalize_pinyin("yu"), "\u{00fc}");
        assert_eq!(normalize_pinyin("yue"), "\u{00fc}e");
        assert_eq!(normalize_pinyin("yuan"), "\u{00fc}an");
    }

    #[test]
    fn test_normalize_pinyin_w_initial() {
        assert_eq!(normalize_pinyin("wu"), "u");
        assert_eq!(normalize_pinyin("wa"), "ua");
        assert_eq!(normalize_pinyin("wo"), "uo");
        assert_eq!(normalize_pinyin("wai"), "uai");
        assert_eq!(normalize_pinyin("wen"), "uen");
    }

    #[test]
    fn test_normalize_pinyin_v_replacement() {
        assert_eq!(normalize_pinyin("nv"), "n\u{00fc}");
        assert_eq!(normalize_pinyin("lv"), "l\u{00fc}");
    }

    // ===== 2. Split pinyin =====

    #[test]
    fn test_split_pinyin_basic() {
        let (init, fin) = split_pinyin("ma");
        assert_eq!(init, "m");
        assert_eq!(fin, "a");
    }

    #[test]
    fn test_split_pinyin_retroflex_syllabic() {
        let (init, fin) = split_pinyin("zhi");
        assert_eq!(init, "zh");
        assert_eq!(fin, "-i_retroflex");
    }

    #[test]
    fn test_split_pinyin_alveolar_syllabic() {
        let (init, fin) = split_pinyin("zi");
        assert_eq!(init, "z");
        assert_eq!(fin, "-i_alveolar");
    }

    #[test]
    fn test_split_pinyin_jqx_umlaut() {
        let (init, fin) = split_pinyin("ju");
        assert_eq!(init, "j");
        assert_eq!(fin, "\u{00fc}");

        let (init2, fin2) = split_pinyin("que");
        assert_eq!(init2, "q");
        assert_eq!(fin2, "\u{00fc}e");
    }

    #[test]
    fn test_split_pinyin_no_initial() {
        let (init, fin) = split_pinyin("a");
        assert_eq!(init, "");
        assert_eq!(fin, "a");

        let (init2, fin2) = split_pinyin("ai");
        assert_eq!(init2, "");
        assert_eq!(fin2, "ai");
    }

    // ===== 3. Tone sandhi =====

    #[test]
    fn test_tone_sandhi_t3_t3() {
        let mut st = vec![("ni".to_string(), 3_u8), ("hao".to_string(), 3)];
        apply_tone_sandhi(&mut st);
        assert_eq!(st[0].1, 2); // T3 -> T2
        assert_eq!(st[1].1, 3); // unchanged
    }

    #[test]
    fn test_tone_sandhi_yi_before_t4() {
        // 一定 yi1 ding4 -> yi2 ding4
        let mut st = vec![
            ("i".to_string(), 1_u8), // "yi" normalized to "i"
            ("ting".to_string(), 4),
        ];
        apply_tone_sandhi(&mut st);
        assert_eq!(st[0].1, 2);
    }

    #[test]
    fn test_tone_sandhi_yi_before_t1() {
        // 一般 yi1 ban1 -> yi4 ban1
        let mut st = vec![("i".to_string(), 1_u8), ("ban".to_string(), 1)];
        apply_tone_sandhi(&mut st);
        assert_eq!(st[0].1, 4);
    }

    #[test]
    fn test_tone_sandhi_bu_before_t4() {
        // 不对 bu4 dui4 -> bu2 dui4
        let mut st = vec![("bu".to_string(), 4_u8), ("tuei".to_string(), 4)];
        apply_tone_sandhi(&mut st);
        assert_eq!(st[0].1, 2);
    }

    // ===== 4. Pinyin to IPA =====

    #[test]
    fn test_pinyin_to_ipa_ma() {
        // ma1 -> ["m", "a", "tone1"]
        let tokens = pinyin_to_ipa("ma", 1);
        assert_eq!(tokens.len(), 3);
        assert_eq!(tokens[0], "m");
        assert_eq!(tokens[1], "a");
        assert_eq!(tokens[2], "tone1");
    }

    #[test]
    fn test_pinyin_to_ipa_zhi() {
        // zhi -> initial "zh" + final "-i_retroflex"
        let tokens = pinyin_to_ipa("zhi", 1);
        assert_eq!(tokens.len(), 3);
        assert_eq!(tokens[0], "t\u{0282}"); // tʂ
        assert_eq!(tokens[1], "\u{027b}\u{0329}"); // ɻ̩
        assert_eq!(tokens[2], "tone1");
    }

    #[test]
    fn test_pinyin_to_ipa_compound_final() {
        // guang -> initial "g" + final "uang"
        let tokens = pinyin_to_ipa("guang", 3);
        assert_eq!(tokens.len(), 3);
        assert_eq!(tokens[0], "k"); // g -> k in IPA
        assert_eq!(tokens[1], "ua\u{014b}"); // uaŋ
        assert_eq!(tokens[2], "tone3");
    }

    #[test]
    fn test_pinyin_to_ipa_zero_initial() {
        // a -> no initial, final "a"
        let tokens = pinyin_to_ipa("a", 1);
        assert_eq!(tokens.len(), 2);
        assert_eq!(tokens[0], "a");
        assert_eq!(tokens[1], "tone1");
    }

    // ===== 5. Phonemize with dict =====

    #[test]
    fn test_single_char_phonemize() {
        let phon = make_phonemizer(
            &[
                ('\u{4f60}', "ni3"),  // 你
                ('\u{597d}', "hao3"), // 好
            ],
            &[],
        );
        let (tokens, prosody) = phon.phonemize_with_prosody("\u{4f60}\u{597d}").unwrap();

        // 你: ni3, 好: hao3 -> T3+T3 sandhi -> ni2 hao3
        // ni2 -> ["n", "i", "tone2"]  (PUA mapped)
        // hao3 -> ["x" (h->x IPA), "aʊ" (PUA), "tone3" (PUA)]
        // Expect 6 IPA tokens total
        assert_eq!(tokens.len(), 6);
        assert_eq!(prosody.len(), 6);

        // Check tones: first char should be tone2 after sandhi
        // "tone2" maps to PUA U+E047
        assert!(
            tokens.iter().any(|t| t == "\u{E047}"),
            "Expected tone2 PUA in tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_phrase_dict_overrides_single() {
        let phon = make_phonemizer(
            &[
                ('\u{4e00}', "yi1"), // 一 (default T1)
                ('\u{4e2a}', "ge4"), // 个
            ],
            &[("\u{4e00}\u{4e2a}", &["yi2", "ge4"])], // phrase dict overrides to T2
        );
        let (tokens, _) = phon.phonemize_with_prosody("\u{4e00}\u{4e2a}").unwrap();

        // Phrase dict gives yi2 directly (T2)
        // yi2 normalized -> "i" T2
        // tokens should contain tone2 PUA for 一
        assert!(
            tokens.iter().any(|t| t == "\u{E047}"),
            "Expected tone2 PUA from phrase dict override: {:?}",
            tokens
        );
    }

    #[test]
    fn test_punctuation_passthrough() {
        let phon = make_phonemizer(&[('\u{4f60}', "ni3")], &[]);
        let (tokens, _) = phon.phonemize_with_prosody("\u{4f60}\u{3002}").unwrap();

        // Should contain the period (mapped from 。)
        assert!(
            tokens.iter().any(|t| t == "."),
            "Expected period from \u{3002} in tokens: {:?}",
            tokens
        );
    }

    #[test]
    fn test_erhua_handling() {
        // 花儿 -> normalized huar -> strip r -> hua + ɚ + tone
        let phon = make_phonemizer(
            &[
                ('\u{82b1}', "huar1"), // 花 with erhua in dict
            ],
            &[],
        );
        let (tokens, _) = phon.phonemize_with_prosody("\u{82b1}").unwrap();

        // Should contain ɚ (U+025A)
        assert!(
            tokens.iter().any(|t| t == "\u{025a}"),
            "Expected erhua \u{025a} in tokens: {:?}",
            tokens
        );
    }

    // ===== 6. PUA mapping =====

    #[test]
    fn test_pua_mapping_tones() {
        let tokens = vec![
            "tone1".to_string(),
            "tone2".to_string(),
            "tone3".to_string(),
            "tone4".to_string(),
            "tone5".to_string(),
        ];
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E046}");
        assert_eq!(mapped[1], "\u{E047}");
        assert_eq!(mapped[2], "\u{E048}");
        assert_eq!(mapped[3], "\u{E049}");
        assert_eq!(mapped[4], "\u{E04A}");
    }

    #[test]
    fn test_pua_mapping_initials() {
        let tokens = vec![
            "p\u{02b0}".to_string(),  // pʰ
            "t\u{0255}".to_string(),  // tɕ
            "t\u{0282}".to_string(),  // tʂ
            "ts\u{02b0}".to_string(), // tsʰ
        ];
        let mapped = map_sequence(tokens);
        assert_eq!(mapped[0], "\u{E020}"); // pʰ
        assert_eq!(mapped[1], "\u{E023}"); // tɕ
        assert_eq!(mapped[2], "\u{E025}"); // tʂ
        assert_eq!(mapped[3], "\u{E027}"); // tsʰ
    }

    // ===== 7. post_process_ids =====

    #[test]
    fn test_post_process_ids_bos_eos_pad() {
        let phon = make_phonemizer(&[], &[]);
        let ids = vec![10_i64, 20, 30];
        let prosody: Vec<Option<ProsodyFeature>> = vec![Some([1, 1, 2]), Some([1, 2, 2]), None];
        let mut id_map: PhonemeIdMap = HashMap::new();
        id_map.insert("^".to_string(), vec![1]);
        id_map.insert("$".to_string(), vec![2]);
        id_map.insert("_".to_string(), vec![0]);

        let (out_ids, out_prosody) = phon.post_process_ids(ids, prosody, &id_map);

        // Expected: BOS(1), 10, PAD(0), 20, PAD(0), 30, EOS(2)
        assert_eq!(out_ids, vec![1, 10, 0, 20, 0, 30, 2]);
        assert_eq!(out_prosody.len(), 7);
        assert!(out_prosody[0].is_none()); // BOS
        assert_eq!(out_prosody[1], Some([1, 1, 2])); // first token
        assert!(out_prosody[2].is_none()); // pad
        assert!(out_prosody[6].is_none()); // EOS
    }

    // ===== 8. Word boundary prosody =====

    #[test]
    fn test_build_word_info() {
        // 你好世界 -> 4 consecutive CJK chars form one word
        let info = build_word_info("\u{4f60}\u{597d}\u{4e16}\u{754c}");
        assert_eq!(info.get(&0), Some(&(1, 4))); // pos 1, word len 4
        assert_eq!(info.get(&1), Some(&(2, 4)));
        assert_eq!(info.get(&2), Some(&(3, 4)));
        assert_eq!(info.get(&3), Some(&(4, 4)));
    }

    #[test]
    fn test_build_word_info_with_punct() {
        // 你好，世界 -> two groups separated by punct
        let info = build_word_info("\u{4f60}\u{597d}\u{ff0c}\u{4e16}\u{754c}");
        assert_eq!(info.get(&0), Some(&(1, 2)));
        assert_eq!(info.get(&1), Some(&(2, 2)));
        assert_eq!(info.get(&3), Some(&(1, 2)));
        assert_eq!(info.get(&4), Some(&(2, 2)));
    }

    // ===== 9. Extract tone =====

    #[test]
    fn test_extract_tone() {
        assert_eq!(extract_tone("ma1"), ("ma", 1));
        assert_eq!(extract_tone("hao3"), ("hao", 3));
        assert_eq!(extract_tone("de5"), ("de", 5));
        assert_eq!(extract_tone("er"), ("er", 5)); // no digit -> neutral
    }

    // ===== 10. CJK detection =====

    #[test]
    fn test_is_cjk() {
        assert!(is_cjk('\u{4e00}')); // 一
        assert!(is_cjk('\u{9fff}'));
        assert!(is_cjk('\u{3400}')); // Extension A
        assert!(!is_cjk('A'));
        assert!(!is_cjk(' '));
        assert!(!is_cjk('\u{3002}')); // 。 is not CJK ideograph
    }

    // ===== 11. Integration: mixed text =====

    #[test]
    fn test_mixed_chinese_and_ascii() {
        let phon = make_phonemizer(
            &[('\u{4f60}', "ni3")], // 你
            &[],
        );
        let (tokens, prosody) = phon.phonemize_with_prosody("\u{4f60}A").unwrap();

        // 你 produces IPA tokens, 'A' passes through
        assert!(tokens.len() >= 4); // at least: n, i, tone3, A
        assert_eq!(tokens.len(), prosody.len());

        // Last token should be 'A'
        assert_eq!(tokens.last().unwrap(), "A");
    }

    // ===== 12. Language code =====

    #[test]
    fn test_language_code() {
        let phon = make_phonemizer(&[], &[]);
        assert_eq!(phon.language_code(), "zh");
    }

    // ===== 13. Empty input =====

    #[test]
    fn test_empty_input() {
        let phon = make_phonemizer(&[], &[]);
        let (tokens, prosody) = phon.phonemize_with_prosody("").unwrap();
        assert!(tokens.is_empty());
        assert!(prosody.is_empty());
    }

    // ===== 14. First alternative selection =====

    #[test]
    fn test_first_alternative() {
        assert_eq!(first_alternative("hao3,hao4"), "hao3");
        assert_eq!(first_alternative("ma1"), "ma1");
        assert_eq!(first_alternative(""), "");
    }

    // ===== 15. Bincode roundtrip =====

    #[test]
    fn test_bincode_roundtrip_single_char_dict() {
        let mut dict: HashMap<char, String> = HashMap::new();
        dict.insert('\u{4F60}', "ni3".to_string()); // 你
        dict.insert('\u{597D}', "hao3".to_string()); // 好
        let bytes = bincode::serialize(&dict).unwrap();
        let restored: HashMap<char, String> = bincode::deserialize(&bytes).unwrap();
        assert_eq!(dict, restored);
    }

    #[test]
    fn test_bincode_roundtrip_phrase_dict() {
        let mut dict: HashMap<String, Vec<String>> = HashMap::new();
        dict.insert(
            "\u{4F60}\u{597D}".to_string(),
            vec!["ni3".to_string(), "hao3".to_string()],
        );
        let bytes = bincode::serialize(&dict).unwrap();
        let restored: HashMap<String, Vec<String>> = bincode::deserialize(&bytes).unwrap();
        assert_eq!(dict, restored);
    }

    #[test]
    fn test_bincode_cache_roundtrip_single_char() {
        let dir = tempfile::tempdir().unwrap();
        let json_path = dir.path().join("pinyin_single.json");

        // Write JSON: { "20320": "ni3", "22909": "hao3" }
        std::fs::write(&json_path, r#"{"20320": "ni3", "22909": "hao3"}"#).unwrap();

        // First load: JSON parse + bincode cache creation
        let loaded1 = load_single_char_dict(&json_path).unwrap();
        assert_eq!(loaded1.len(), 2);
        assert_eq!(loaded1.get(&'\u{4F60}').unwrap(), "ni3");

        // Verify bincode cache file was created
        let bincode_path = json_path.with_extension("json.bincode");
        assert!(bincode_path.exists(), "bincode cache should be created");

        // Second load: should use bincode cache
        let loaded2 = load_single_char_dict(&json_path).unwrap();
        assert_eq!(loaded1, loaded2);
    }

    #[test]
    fn test_bincode_cache_roundtrip_phrase() {
        let dir = tempfile::tempdir().unwrap();
        let json_path = dir.path().join("pinyin_phrases.json");

        // Write JSON with space-separated pinyin string format
        std::fs::write(&json_path, r#"{"\u4f60\u597d": "ni3 hao3"}"#).unwrap();

        // First load: JSON parse + bincode cache creation
        let loaded1 = load_phrase_dict(&json_path).unwrap();
        assert_eq!(loaded1.len(), 1);
        let pinyins = loaded1.get("\u{4F60}\u{597D}").unwrap();
        assert_eq!(pinyins, &vec!["ni3".to_string(), "hao3".to_string()]);

        // Verify bincode cache file was created
        let bincode_path = json_path.with_extension("json.bincode");
        assert!(bincode_path.exists(), "bincode cache should be created");

        // Second load: should use bincode cache
        let loaded2 = load_phrase_dict(&json_path).unwrap();
        assert_eq!(loaded1, loaded2);
    }

    // ===== 16. Corrupted bincode fallback =====

    #[test]
    fn test_corrupted_bincode_falls_back_to_json_single_char() {
        let dir = tempfile::tempdir().unwrap();
        let json_path = dir.path().join("pinyin_single.json");
        let bincode_path = json_path.with_extension("json.bincode");

        // 有効な JSON を作成
        std::fs::write(&json_path, r#"{"20320": "ni3"}"#).unwrap();

        // 破損した bincode を作成 (JSON より新しいタイムスタンプ)
        std::fs::write(&bincode_path, b"CORRUPT_DATA_HERE").unwrap();

        // bincode deserialization が失敗し、None が返ること
        let result: Option<HashMap<char, String>> = try_load_bincode_cache(&json_path);
        assert!(result.is_none(), "corrupted bincode should return None");
    }
}
