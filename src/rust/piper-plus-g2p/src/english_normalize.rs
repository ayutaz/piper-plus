//! English text normalization, ported from Python's g2p_en.
//!
//! Python's English G2P (`g2p_en.G2p.__call__`) rewrites the text before its
//! dictionary lookup. This module ports those steps so the Rust phonemizer
//! sees the same words:
//!
//! 1. `normalize_numbers` spells numbers out the way inflect does
//!    (`123` -> `one hundred twenty-three`, `1984` -> `nineteen eighty-four`,
//!    `$5` -> `five dollars`, `2nd` -> `second`);
//! 2. accents are stripped (NFD, combining marks removed);
//! 3. every character other than `a-z A-Z ' . , ? ! -` and the ASCII space is
//!    removed (tabs and newlines too, so the words around them join);
//! 4. `i.e.` / `e.g.` become `that is` / `for example` (case-insensitively);
//! 5. the subset of nltk's `TweetTokenizer` that this character set can reach
//!    splits the text into words.
//!
//! Python lowercases at step 2; the port keeps the case because the OOV
//! fallback splits CamelCase words. Callers lowercase for dictionary lookup.
//! `tests/english_normalize.rs` checks both steps against
//! `tests/fixtures/g2p/english_normalize_cases.json`, generated from Python.

use std::sync::LazyLock;

use regex::{Captures, Regex};

// ---------------------------------------------------------------------------
// Number expansion (g2p_en expand.py + inflect number_to_words)
// ---------------------------------------------------------------------------

static COMMA_NUMBER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"([0-9][0-9,]+[0-9])").unwrap());
static POUNDS_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"£([0-9,]*[0-9]+)").unwrap());
static DOLLARS_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\$([0-9.,]*[0-9]+)").unwrap());
static DECIMAL_NUMBER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"([0-9]+\.[0-9]+)").unwrap());
static ORDINAL_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[0-9]+(st|nd|rd|th)").unwrap());
static NUMBER_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"[0-9]+").unwrap());

// inflect's post-processing of the joined groups.
static WHITESPACES_COMMA_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+,").unwrap());
static COMMA_WORD_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r", (\S+)\s+\z").unwrap());
static WHITESPACES_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"\s+").unwrap());

const UNIT: [&str; 10] = [
    "", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
];
const TEEN: [&str; 10] = [
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
];
const TEN: [&str; 10] = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
];
/// Group scales. inflect goes on to decillion; the port stops at quintillion
/// and reads longer digit runs digit by digit.
const MILL: [&str; 7] = [
    " ",
    " thousand",
    " million",
    " billion",
    " trillion",
    " quadrillion",
    " quintillion",
];
const DIGIT_NAMES: [&str; 10] = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
];
/// Ordinal endings, tried at the end of the last word (inflect `ordinal`).
const ORDINAL_SUFFIXES: [(&str, &str); 8] = [
    ("ty", "tieth"),
    ("one", "first"),
    ("two", "second"),
    ("three", "third"),
    ("five", "fifth"),
    ("eight", "eighth"),
    ("nine", "ninth"),
    ("twelve", "twelfth"),
];

/// Expand numbers in `text` to English words, like g2p_en's
/// `normalize_numbers`. The regex substitutions run in Python's order.
pub fn normalize_numbers(text: &str) -> String {
    let text = COMMA_NUMBER_RE.replace_all(text, |c: &Captures<'_>| c[1].replace(',', ""));
    let text = POUNDS_RE.replace_all(&text, "${1} pounds");
    let text = DOLLARS_RE.replace_all(&text, |c: &Captures<'_>| expand_dollars(&c[1]));
    let text =
        DECIMAL_NUMBER_RE.replace_all(&text, |c: &Captures<'_>| c[1].replace('.', " point "));
    let text = ORDINAL_RE.replace_all(&text, |c: &Captures<'_>| expand_ordinal(&c[0]));
    NUMBER_RE
        .replace_all(&text, |c: &Captures<'_>| expand_number(&c[0]))
        .into_owned()
}

/// The decimal digits of `s` without leading zeros ("0" when there are none).
/// Matches Python's `str(int(s))`; non-digits (a stray comma) are ignored.
fn canonical_digits(s: &str) -> String {
    let digits: String = s.chars().filter(char::is_ascii_digit).collect();
    let trimmed = digits.trim_start_matches('0');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

/// `$D.C` -> `D dollar(s), C cent(s)` (g2p_en `_expand_dollars`).
fn expand_dollars(amount: &str) -> String {
    let parts: Vec<&str> = amount.split('.').collect();
    if parts.len() > 2 {
        return format!("{amount} dollars"); // Unexpected format
    }
    let dollars = canonical_digits(parts[0]);
    let cents = canonical_digits(parts.get(1).copied().unwrap_or(""));
    let dollar_unit = if dollars == "1" { "dollar" } else { "dollars" };
    let cent_unit = if cents == "1" { "cent" } else { "cents" };
    match (dollars != "0", cents != "0") {
        (true, true) => format!("{dollars} {dollar_unit}, {cents} {cent_unit}"),
        (true, false) => format!("{dollars} {dollar_unit}"),
        (false, true) => format!("{cents} {cent_unit}"),
        (false, false) => "zero dollars".to_string(),
    }
}

/// `21st` -> `twenty-first` (inflect `number_to_words` with an ordinal suffix).
fn expand_ordinal(matched: &str) -> String {
    let digits = canonical_digits(&matched[..matched.len() - 2]);
    to_ordinal(&number_words(&digits, "and"))
}

/// Cardinal numbers, read as years between 1001 and 2999 (g2p_en
/// `_expand_number`).
fn expand_number(matched: &str) -> String {
    let digits = canonical_digits(matched);
    if digits.len() == 4 {
        let n: u32 = digits.parse().unwrap_or(0);
        if n > 1000 && n < 3000 {
            return year_words(n);
        }
    }
    number_words(&digits, "")
}

fn year_words(n: u32) -> String {
    if n == 2000 {
        "two thousand".to_string()
    } else if n > 2000 && n < 2010 {
        format!(
            "two thousand {}",
            number_words(&(n % 100).to_string(), "and")
        )
    } else if n.is_multiple_of(100) {
        format!("{} hundred", number_words(&(n / 100).to_string(), "and"))
    } else {
        // inflect group=2 with zero="oh": two digits at a time.
        let low = (n % 100) as usize;
        let low_words = if low < 10 {
            format!("oh {}", UNIT[low])
        } else {
            tens_words(low / 10, low % 10, 0).trim_end().to_string()
        };
        let high = (n / 100) as usize;
        format!(
            "{} {low_words}",
            tens_words(high / 10, high % 10, 0).trim_end()
        )
    }
}

/// inflect `tenfn`: 0-99 followed by the scale of group `mill`.
fn tens_words(tens: usize, units: usize, mill: usize) -> String {
    if tens == 1 {
        return format!("{}{}", TEEN[units], MILL[mill]);
    }
    let hyphen = if tens > 0 && units > 0 { "-" } else { "" };
    format!("{}{hyphen}{}{}", TEN[tens], UNIT[units], MILL[mill])
}

/// inflect `hundfn`: one full group of three digits.
fn hundreds_words(hundreds: usize, tens: usize, units: usize, mill: usize, and: &str) -> String {
    if hundreds > 0 {
        let andword = if tens > 0 || units > 0 {
            format!(" {and} ")
        } else {
            String::new()
        };
        format!(
            "{} hundred{andword}{}{}, ",
            UNIT[hundreds],
            tens_words(tens, units, 0),
            MILL[mill]
        )
    } else if tens > 0 || units > 0 {
        format!("{}{}, ", tens_words(tens, units, 0), MILL[mill])
    } else {
        String::new()
    }
}

/// inflect `number_to_words(digits, andword=and)` for a canonical digit
/// string. Groups are joined with ", " except that a last group of 1-99 is
/// joined with `and` (` ` when `and` is empty): `one million one`.
fn number_words(digits: &str, and: &str) -> String {
    match digits {
        "0" => return "zero".to_string(),
        "1" => return "one".to_string(),
        _ => {}
    }
    let d: Vec<usize> = digits.bytes().map(|b| usize::from(b - b'0')).collect();
    if d.len() > 3 * MILL.len() {
        // Beyond quintillion: read each digit.
        return d
            .iter()
            .map(|&x| DIGIT_NAMES[x])
            .collect::<Vec<_>>()
            .join(" ");
    }

    let groups = d.len() / 3;
    let lead = d.len() % 3;
    let mut s = String::new();
    match lead {
        2 => s.push_str(&format!("{}, ", tens_words(d[0], d[1], groups))),
        1 => s.push_str(&format!("{}{}, ", UNIT[d[0]], MILL[groups])),
        _ => {}
    }
    for g in 0..groups {
        let i = lead + 3 * g;
        s.push_str(&hundreds_words(
            d[i],
            d[i + 1],
            d[i + 2],
            groups - 1 - g,
            and,
        ));
    }

    if s.ends_with(", ") {
        s.truncate(s.len() - 2);
    }
    let s = WHITESPACES_COMMA_RE.replace_all(&s, ",");
    let s = COMMA_WORD_RE.replace(&s, |c: &Captures<'_>| format!(" {and} {}", &c[1]));
    WHITESPACES_RE.replace_all(&s, " ").trim().to_string()
}

/// inflect `_sub_ord`: the ordinal of the last word.
fn to_ordinal(words: &str) -> String {
    for (suffix, replacement) in ORDINAL_SUFFIXES {
        if let Some(stem) = words.strip_suffix(suffix) {
            return format!("{stem}{replacement}");
        }
    }
    format!("{words}th")
}

// ---------------------------------------------------------------------------
// Accent stripping and character filter
// ---------------------------------------------------------------------------

/// Base letter of each code point in U+00C0..=U+024F whose NFD form is an
/// ASCII letter followed by combining marks; `-` where there is none.
/// Generated with Python's `unicodedata`.
const LATIN_BASE_00C0: &str = concat!(
    "AAAAAA-CEEEEIIII-NOOOOO--UUUUY--aaaaaa-ceeeeiiii-nooooo--uuuuy-y",
    "AaAaAaCcCcCcCcDd--EeEeEeEeEeGgGgGgGgHh--IiIiIiIiI---JjKk-LlLlLl-",
    "---NnNnNn---OoOoOo--RrRrRrSsSsSsSsTtTt--UuUuUuUuUuUuWwYyYZzZzZz-",
    "--------------------------------Oo-------------Uu---------------",
    "-------------AaIiOoUuUuUuUuUu-AaAa----GgKkOoOo--j---Gg--NnAa----",
    "AaAaEeEeIiIiOoOoRrRrUuUuSsTt--Hh------AaEeOoOoOoOoYy------------",
    "----------------",
);

/// The same for U+1E00..=U+1EFF (Latin Extended Additional).
const LATIN_BASE_1E00: &str = concat!(
    "AaBbBbBbCcDdDdDdDdDdEeEeEeEeEeFfGgHhHhHhHhHhIiIiKkKkKkLlLlLlLlMm",
    "MmMmNnNnNnNnOoOoOoOoPpPpRrRrRrRrSsSsSsSsSsTtTtTtTtUuUuUuUuUuVvVv",
    "WwWwWwWwWwXxXxYyZzZzZzhtwy------AaAaAaAaAaAaAaAaAaAaAaAaEeEeEeEe",
    "EeEeEeEeIiIiOoOoOoOoOoOoOoOoOoOoOoOoUuUuUuUuUuUuUuYyYyYyYy------",
);

/// The ASCII letter left after NFD and removing combining marks, for a
/// non-ASCII character. Combining marks themselves and every other
/// character give `None`: the character filter would remove them anyway.
fn fold_accent(ch: char) -> Option<char> {
    let from_table = |table: &str, offset: u32| match table.as_bytes().get(offset as usize) {
        Some(&b) if b != b'-' => Some(char::from(b)),
        _ => None,
    };
    let cp = u32::from(ch);
    match cp {
        0x00C0..=0x024F => from_table(LATIN_BASE_00C0, cp - 0x00C0),
        0x1E00..=0x1EFF => from_table(LATIN_BASE_1E00, cp - 0x1E00),
        0x212A => Some('K'), // KELVIN SIGN
        0x212B => Some('A'), // ANGSTROM SIGN
        _ => None,
    }
}

/// Steps 2-3: strip accents and keep `a-z A-Z ' . , ? ! -` and ASCII space.
/// The result is ASCII.
fn strip_accents_and_filter(text: &str) -> String {
    text.chars()
        .filter_map(|ch| {
            if ch.is_ascii() {
                Some(ch)
            } else {
                fold_accent(ch)
            }
        })
        .filter(|&ch| {
            ch.is_ascii_alphabetic() || matches!(ch, ' ' | '\'' | '.' | ',' | '?' | '!' | '-')
        })
        .collect()
}

/// Python's `str.replace` (left to right, non-overlapping), ignoring ASCII
/// case. `text` and `pattern` are ASCII.
fn replace_ignore_ascii_case(text: &str, pattern: &str, replacement: &str) -> String {
    let bytes = text.as_bytes();
    let pat = pattern.as_bytes();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes.len() - i >= pat.len() && bytes[i..i + pat.len()].eq_ignore_ascii_case(pat) {
            out.push_str(replacement);
            i += pat.len();
        } else {
            out.push(char::from(bytes[i]));
            i += 1;
        }
    }
    out
}

// ---------------------------------------------------------------------------
// TweetTokenizer subset
// ---------------------------------------------------------------------------

/// nltk `HANG_RE`: 4+ copies of a non-letter, non-digit character become 3.
fn shorten_hang(text: &str) -> String {
    let bytes = text.as_bytes();
    let mut out = String::with_capacity(text.len());
    let mut i = 0;
    while i < bytes.len() {
        let c = bytes[i];
        let mut j = i + 1;
        while j < bytes.len() && bytes[j] == c {
            j += 1;
        }
        let run = if c.is_ascii_alphanumeric() {
            j - i
        } else {
            (j - i).min(3)
        };
        for _ in 0..run {
            out.push(char::from(c));
        }
        i = j;
    }
    out
}

fn letter_run_end(b: &[u8], start: usize) -> usize {
    let mut j = start;
    while j < b.len() && b[j].is_ascii_alphabetic() {
        j += 1;
    }
    j
}

/// Naked domain: `[a-z]+([.-][a-z]+){0,126}\.[a-z]{2,13}` not followed by a
/// letter. Like the backtracking regex, it takes the most labels for which
/// the next separator is '.' and the label after it has 2-13 letters.
fn match_domain(b: &[u8], start: usize) -> Option<usize> {
    let mut pos = letter_run_end(b, start);
    if pos == start {
        return None;
    }
    // (separator, label end) for each label after the first run.
    let mut labels: Vec<(u8, usize, usize)> = Vec::new();
    while pos + 1 < b.len() && matches!(b[pos], b'.' | b'-') && b[pos + 1].is_ascii_alphabetic() {
        let end = letter_run_end(b, pos + 1);
        labels.push((b[pos], pos + 1, end));
        pos = end;
    }
    labels
        .iter()
        .enumerate()
        .rev()
        .filter(|(k, _)| *k <= 126)
        .find(|&(_, &(sep, s, e))| sep == b'.' && (2..=13).contains(&(e - s)))
        .map(|(_, &(_, _, e))| e)
}

/// Word with apostrophes or dashes: `[a-z]([a-z]|['-])+[a-z]`.
fn match_hyphenated_word(b: &[u8], start: usize) -> Option<usize> {
    if !b[start].is_ascii_alphabetic() {
        return None;
    }
    let mut end = start + 1;
    while end < b.len() && (b[end].is_ascii_alphabetic() || matches!(b[end], b'\'' | b'-')) {
        end += 1;
    }
    (start + 2..end)
        .rev()
        .find(|&i| b[i].is_ascii_alphabetic())
        .map(|i| i + 1)
}

/// Ellipsis: `\.( *\.)+`.
fn match_ellipsis(b: &[u8], start: usize) -> Option<usize> {
    if b[start] != b'.' {
        return None;
    }
    let mut end = None;
    let mut j = start + 1;
    loop {
        let mut k = j;
        while k < b.len() && b[k] == b' ' {
            k += 1;
        }
        if k < b.len() && b[k] == b'.' {
            end = Some(k + 1);
            j = k + 1;
        } else {
            return end;
        }
    }
}

/// The part of nltk's `TweetTokenizer` that the filtered character set
/// (`a-z A-Z ' . , ? ! -` and space) can reach. At each position the first
/// matching alternative wins, in nltk's order; spaces only separate words.
fn tweet_tokenize(text: &str) -> Vec<String> {
    let text = shorten_hang(text);
    let b = text.as_bytes();
    let mut words = Vec::new();
    let mut i = 0;
    while i < b.len() {
        if b[i] == b' ' {
            i += 1;
            continue;
        }
        let end = match_domain(b, i)
            .or_else(|| match_hyphenated_word(b, i))
            .or_else(|| Some(letter_run_end(b, i)).filter(|&e| e > i))
            .or_else(|| match_ellipsis(b, i))
            .unwrap_or(i + 1);
        words.push(text[i..end].to_string());
        i = end;
    }
    words
}

/// All of g2p_en's preprocessing: number expansion, accent stripping, the
/// character filter, the i.e./e.g. replacement and tokenization. The words
/// keep their case; Python's are these words lowercased.
pub fn normalize_and_tokenize(text: &str) -> Vec<String> {
    let text = strip_accents_and_filter(&normalize_numbers(text));
    let text = replace_ignore_ascii_case(&text, "i.e.", "that is");
    let text = replace_ignore_ascii_case(&text, "e.g.", "for example");
    tweet_tokenize(&text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_number_beyond_quintillion_read_digit_by_digit() {
        assert_eq!(
            normalize_numbers("1234567890123456789012"),
            "one two three four five six seven eight nine zero one two three four five six \
             seven eight nine zero one two"
        );
        assert_eq!(
            normalize_numbers("999999999999999999999"),
            "nine hundred ninety-nine quintillion, nine hundred ninety-nine quadrillion, \
             nine hundred ninety-nine trillion, nine hundred ninety-nine billion, \
             nine hundred ninety-nine million, nine hundred ninety-nine thousand, \
             nine hundred ninety-nine"
        );
    }

    #[test]
    fn test_accents_stripped_and_other_characters_removed() {
        assert_eq!(strip_accents_and_filter("Crème Brûlée"), "Creme Brulee");
        assert_eq!(strip_accents_and_filter("\u{212A}elvin"), "Kelvin");
        assert_eq!(strip_accents_and_filter("a\tb\nc;d:e\"f"), "abcdef");
        assert_eq!(strip_accents_and_filter("日本 ß æ"), "  ");
    }

    #[test]
    fn test_ie_eg_replaced_ignoring_case() {
        assert_eq!(
            replace_ignore_ascii_case("I.e. x i.E.", "i.e.", "that is"),
            "that is x that is"
        );
    }

    #[test]
    fn test_shorten_hang() {
        assert_eq!(shorten_hang("!!!!"), "!!!");
        assert_eq!(shorten_hang("a----b"), "a---b");
        assert_eq!(shorten_hang("aaaa..."), "aaaa...");
    }

    #[test]
    fn test_tokenize_keeps_case() {
        assert_eq!(
            normalize_and_tokenize("ChatGPT, e.g. Mr. Smith"),
            vec!["ChatGPT", ",", "for", "example", "Mr", ".", "Smith"]
        );
    }

    #[test]
    fn test_domain_with_hyphen_after_tld() {
        assert_eq!(tweet_tokenize("foo.bar-baz"), vec!["foo.bar", "-", "baz"]);
    }
}
