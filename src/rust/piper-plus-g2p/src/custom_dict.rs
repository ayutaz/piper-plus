//! カスタム辞書モジュール
//!
//! 技術用語や固有名詞の読みを管理し、テキスト前処理を行う。
//! Python `custom_dict.py` と同一ロジックの Rust 移植。
//!
//! ## JSON 辞書フォーマット
//!
//! **v1.0** (単純形式):
//! ```json
//! { "version": "1.0", "entries": { "API": "エーピーアイ" } }
//! ```
//!
//! **v2.0** (詳細形式):
//! ```json
//! { "version": "2.0", "entries": { "API": { "pronunciation": "エーピーアイ", "priority": 5 } } }
//! ```

use std::collections::HashMap;
use std::path::Path;
use std::sync::Mutex;

use regex::Regex;
use serde::Deserialize;

use crate::error::G2pError;

/// 辞書ファイルの最大サイズ (10 MB) — Python 側の制限と一致
const MAX_DICT_SIZE: u64 = 10 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/// 辞書エントリ
#[derive(Debug, Clone)]
pub struct DictEntry {
    pub pronunciation: String,
    pub priority: i32,
}

/// JSON v2.0 のエントリ表現 (デシリアライズ用)
#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum RawEntry {
    /// v1.0 互換: 文字列のみ
    Simple(String),
    /// v2.0: pronunciation + optional priority
    Detailed(DetailedEntry),
}

#[derive(Debug, Deserialize)]
struct DetailedEntry {
    pronunciation: String,
    #[serde(default = "default_priority")]
    priority: i32,
}

fn default_priority() -> i32 {
    5
}

/// JSON 辞書ファイルのトップレベル構造
#[derive(Debug, Deserialize)]
struct DictFile {
    /// バージョン文字列 (将来の拡張用に保持)
    #[serde(default = "default_version")]
    #[allow(dead_code)]
    version: String,
    #[serde(default)]
    entries: HashMap<String, RawEntry>,
}

fn default_version() -> String {
    "1.0".to_string()
}

// ---------------------------------------------------------------------------
// CustomDictionary
// ---------------------------------------------------------------------------

/// カスタム辞書
///
/// 技術用語・固有名詞の読みを保持し、テキスト中の該当箇所を置換する。
///
/// - 大文字小文字混在の単語 (例: "GitHub") は case-sensitive マップに格納
/// - 全大文字/全小文字の単語は lowercase 正規化して case-insensitive マップに格納
/// - 日本語 (非 ASCII) 文字を含む単語は単純部分文字列マッチ
/// - ASCII のみの単語は単語境界正規表現でマッチ
pub struct CustomDictionary {
    /// Case-insensitive エントリ (キーは lowercase 正規化済み)
    entries: HashMap<String, DictEntry>,
    /// Case-sensitive エントリ (混在ケースの単語)
    case_sensitive_entries: HashMap<String, DictEntry>,
    /// コンパイル済み正規表現キャッシュ (interior mutability で &self から挿入可能)
    pattern_cache: Mutex<HashMap<String, Regex>>,
}

impl CustomDictionary {
    /// 空の辞書を作成
    pub fn new() -> Self {
        Self {
            entries: HashMap::new(),
            case_sensitive_entries: HashMap::new(),
            pattern_cache: Mutex::new(HashMap::new()),
        }
    }

    /// JSON 辞書ファイルを読み込む (v1.0 / v2.0 対応)
    pub fn load_dictionary(&mut self, path: &Path) -> Result<(), G2pError> {
        // ファイルサイズチェック (DoS 防止)
        let metadata = std::fs::metadata(path).map_err(|_| G2pError::DictionaryLoad {
            path: path.display().to_string(),
        })?;
        if metadata.len() > MAX_DICT_SIZE {
            return Err(G2pError::DictionaryLoad {
                path: format!(
                    "{}: file too large ({} bytes, max {})",
                    path.display(),
                    metadata.len(),
                    MAX_DICT_SIZE,
                ),
            });
        }

        let content = std::fs::read_to_string(path).map_err(|_| G2pError::DictionaryLoad {
            path: path.display().to_string(),
        })?;

        let dict_file: DictFile =
            serde_json::from_str(&content).map_err(|e| G2pError::DictionaryLoad {
                path: format!("{}: {}", path.display(), e),
            })?;

        for (word, raw_entry) in dict_file.entries {
            // v2.0: コメント行スキップ
            if word.starts_with("//") {
                continue;
            }

            let entry = match raw_entry {
                RawEntry::Simple(pronunciation) => DictEntry {
                    pronunciation,
                    priority: default_priority(),
                },
                RawEntry::Detailed(d) => DictEntry {
                    pronunciation: d.pronunciation,
                    priority: d.priority,
                },
            };

            self.add_entry(&word, entry);
        }

        Ok(())
    }

    /// テキストに辞書を適用して単語を置換
    ///
    /// 1. Case-sensitive エントリを長い順に処理
    /// 2. Case-insensitive エントリを長い順に処理
    pub fn apply_to_text(&self, text: &str) -> String {
        let mut result = text.to_string();

        // Case-sensitive エントリ (長い順)
        let mut cs_entries: Vec<_> = self.case_sensitive_entries.iter().collect();
        cs_entries.sort_by_key(|entry| std::cmp::Reverse(entry.0.len()));

        for (word, entry) in &cs_entries {
            let pattern = self.get_word_pattern(word, true);
            result = pattern
                .replace_all(&result, entry.pronunciation.as_str())
                .to_string();
        }

        // Case-insensitive エントリ (長い順)
        let mut ci_entries: Vec<_> = self.entries.iter().collect();
        ci_entries.sort_by_key(|entry| std::cmp::Reverse(entry.0.len()));

        for (word, entry) in &ci_entries {
            let pattern = self.get_word_pattern(word, false);
            result = pattern
                .replace_all(&result, entry.pronunciation.as_str())
                .to_string();
        }

        result
    }

    /// 単語と読みを追加
    ///
    /// 既存エントリより優先度が低い場合は追加しない。
    /// パターンキャッシュはクリアされる。
    pub fn add_word(&mut self, word: &str, pronunciation: &str, priority: i32) {
        let entry = DictEntry {
            pronunciation: pronunciation.to_string(),
            priority,
        };
        self.add_entry(word, entry);
        self.pattern_cache.lock().unwrap().clear();
    }

    /// 単語の読みを取得
    ///
    /// Case-sensitive マップを先に検索し、見つからなければ case-insensitive マップを検索。
    pub fn get_pronunciation(&self, word: &str) -> Option<&str> {
        // Case-sensitive を先にチェック
        if let Some(entry) = self.case_sensitive_entries.get(word) {
            return Some(&entry.pronunciation);
        }

        // Case-insensitive (lowercase 正規化)
        let normalized = word.to_lowercase();
        self.entries
            .get(&normalized)
            .map(|e| e.pronunciation.as_str())
    }

    // -----------------------------------------------------------------------
    // Internal helpers
    // -----------------------------------------------------------------------

    /// エントリを適切なマップに追加
    fn add_entry(&mut self, word: &str, entry: DictEntry) {
        let lower = word.to_lowercase();
        let upper = word.to_uppercase();

        if word != lower && word != upper {
            // 大文字小文字混在 → case-sensitive マップ
            self.case_sensitive_entries.insert(word.to_string(), entry);
        } else {
            // 全大文字 or 全小文字 → lowercase 正規化して case-insensitive マップ
            let normalized = lower;

            if let Some(existing) = self.entries.get(&normalized)
                && entry.priority <= existing.priority
            {
                return; // 既存の方が優先度が高い (または同じ)
            }

            self.entries.insert(normalized, entry);
        }
    }

    /// 単語の正規表現パターンを取得 (キャッシュ利用)
    fn get_word_pattern(&self, word: &str, case_sensitive: bool) -> Regex {
        let cache_key = format!("{}_{}", word, case_sensitive);

        let mut cache = self.pattern_cache.lock().unwrap();
        if let Some(cached) = cache.get(&cache_key) {
            return cached.clone();
        }

        let escaped = regex::escape(word);

        // 非 ASCII 文字を含むかチェック (日本語等)
        let has_non_ascii = word.chars().any(|c| c as u32 > 127);

        let pattern_str = if has_non_ascii {
            // 日本語を含む場合: 単純部分文字列マッチ
            escaped
        } else {
            // ASCII のみ: ASCII ワード境界で区切る
            // (?-u:\b) は ASCII のみの \b — 日本語文字の隣でも正しく動作する
            format!(r"(?-u:\b){}(?-u:\b)", escaped)
        };

        let pattern = if case_sensitive {
            Regex::new(&pattern_str)
        } else {
            Regex::new(&format!("(?i){}", pattern_str))
        };

        let pat = pattern.expect("failed to compile regex pattern");
        cache.insert(cache_key, pat.clone());
        pat
    }
}

impl Default for CustomDictionary {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use std::sync::atomic::{AtomicU32, Ordering};

    static COUNTER: AtomicU32 = AtomicU32::new(0);

    /// テスト用に一時 JSON ファイルを作成するヘルパー
    fn write_temp_json(content: &str) -> std::path::PathBuf {
        let id = COUNTER.fetch_add(1, Ordering::SeqCst);
        let path = std::env::temp_dir().join(format!(
            "piper_test_dict_{}_{}.json",
            std::process::id(),
            id
        ));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(content.as_bytes()).unwrap();
        f.flush().unwrap();
        path
    }

    // ----- v1.0 / v2.0 ロード -----

    #[test]
    fn test_load_v1_dictionary() {
        let json = r#"{
            "version": "1.0",
            "entries": {
                "API": "エーピーアイ",
                "CPU": "シーピーユー"
            }
        }"#;
        let f = write_temp_json(json);

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&f).unwrap();

        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
        assert_eq!(dict.get_pronunciation("cpu"), Some("シーピーユー"));
    }

    #[test]
    fn test_load_v2_dictionary() {
        let json = r#"{
            "version": "2.0",
            "entries": {
                "API": {"pronunciation": "エーピーアイ", "priority": 8},
                "GPU": {"pronunciation": "ジーピーユー"}
            }
        }"#;
        let f = write_temp_json(json);

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&f).unwrap();

        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
        assert_eq!(dict.get_pronunciation("gpu"), Some("ジーピーユー"));
    }

    #[test]
    fn test_v2_comment_lines_skipped() {
        let json = r#"{
            "version": "2.0",
            "entries": {
                "// this is a comment": {"pronunciation": "ignored", "priority": 1},
                "API": {"pronunciation": "エーピーアイ", "priority": 5}
            }
        }"#;
        let f = write_temp_json(json);

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&f).unwrap();

        // コメント行は登録されない
        assert_eq!(dict.get_pronunciation("// this is a comment"), None);
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
    }

    #[test]
    fn test_load_nonexistent_file() {
        let mut dict = CustomDictionary::new();
        let result = dict.load_dictionary(Path::new("/no/such/file.json"));
        assert!(result.is_err());
    }

    #[test]
    fn test_load_file_too_large() {
        // MAX_DICT_SIZE (10 MB) を超えるファイルは拒否される
        let id = COUNTER.fetch_add(1, Ordering::SeqCst);
        let path = std::env::temp_dir().join(format!(
            "piper_test_dict_large_{}_{}.json",
            std::process::id(),
            id,
        ));
        // 10 MB + 1 byte のダミーファイルを作成
        let size = (super::MAX_DICT_SIZE + 1) as usize;
        let data = vec![b' '; size];
        std::fs::write(&path, &data).unwrap();

        let mut dict = CustomDictionary::new();
        let result = dict.load_dictionary(&path);
        assert!(result.is_err());

        let err_msg = format!("{}", result.unwrap_err());
        assert!(
            err_msg.contains("file too large"),
            "error should mention 'file too large': {}",
            err_msg
        );

        // テスト後クリーンアップ
        let _ = std::fs::remove_file(&path);
    }

    // ----- Case sensitivity -----

    #[test]
    fn test_case_sensitivity() {
        let mut dict = CustomDictionary::new();

        // 混在ケース → case-sensitive マップ
        dict.add_word("GitHub", "ギットハブ", 5);
        // 全大文字 → case-insensitive マップ (lowercase 正規化)
        dict.add_word("API", "エーピーアイ", 5);

        // case-sensitive: 完全一致のみ
        assert_eq!(dict.get_pronunciation("GitHub"), Some("ギットハブ"));
        // "github" (全小文字) は case-sensitive マップにないので None
        // ただし case-insensitive マップにも登録されていないので None
        assert_eq!(dict.get_pronunciation("github"), None);

        // case-insensitive: どのケースでも取得可能
        assert_eq!(dict.get_pronunciation("API"), Some("エーピーアイ"));
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ"));
        assert_eq!(dict.get_pronunciation("Api"), Some("エーピーアイ"));
    }

    // ----- Priority -----

    #[test]
    fn test_priority_ordering() {
        let mut dict = CustomDictionary::new();

        dict.add_word("API", "エーピーアイ低", 3);
        dict.add_word("API", "エーピーアイ高", 7);
        // 優先度 7 > 3 なので上書きされる
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ高"));

        // 同じ優先度では上書きされない
        dict.add_word("API", "エーピーアイ同", 7);
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ高"));

        // 低い優先度では上書きされない
        dict.add_word("API", "エーピーアイ低2", 2);
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ高"));
    }

    // ----- Japanese word matching -----

    #[test]
    fn test_japanese_word_matching() {
        let mut dict = CustomDictionary::new();
        dict.add_word("東京都", "トウキョウト", 5);

        let result = dict.apply_to_text("私は東京都に住んでいます");
        assert_eq!(result, "私はトウキョウトに住んでいます");
    }

    #[test]
    fn test_japanese_substring_no_boundary() {
        let mut dict = CustomDictionary::new();
        dict.add_word("京都", "キョウト", 5);
        dict.add_word("東京都", "トウキョウト", 5);

        // 長い方が先にマッチ → 「東京都」が置換される
        let result = dict.apply_to_text("東京都と京都");
        assert_eq!(result, "トウキョウトとキョウト");
    }

    // ----- English word boundary matching -----

    #[test]
    fn test_english_word_boundary() {
        let mut dict = CustomDictionary::new();
        dict.add_word("API", "エーピーアイ", 5);

        // 単語境界あり → マッチ
        assert_eq!(dict.apply_to_text("Use API here"), "Use エーピーアイ here");

        // 英数字に隣接 → マッチしない
        assert_eq!(dict.apply_to_text("UseAPIhere"), "UseAPIhere");

        // 記号に隣接 → マッチ
        assert_eq!(dict.apply_to_text("(API)"), "(エーピーアイ)");
    }

    #[test]
    fn test_english_case_insensitive_matching() {
        let mut dict = CustomDictionary::new();
        dict.add_word("CPU", "シーピーユー", 5);

        // case-insensitive: 大文字小文字問わずマッチ
        assert_eq!(dict.apply_to_text("my cpu"), "my シーピーユー");
        assert_eq!(dict.apply_to_text("my CPU"), "my シーピーユー");
    }

    // ----- apply_to_text with mixed text -----

    #[test]
    fn test_apply_mixed_ja_en_text() {
        let mut dict = CustomDictionary::new();
        dict.add_word("GitHub", "ギットハブ", 5);
        dict.add_word("API", "エーピーアイ", 5);
        dict.add_word("東京", "トウキョウ", 5);

        let input = "東京のGitHubでAPI開発";
        let result = dict.apply_to_text(input);
        assert_eq!(result, "トウキョウのギットハブでエーピーアイ開発");
    }

    #[test]
    fn test_apply_case_sensitive_before_insensitive() {
        let mut dict = CustomDictionary::new();
        // "iOS" は混在ケース → case-sensitive
        dict.add_word("iOS", "アイオーエス", 5);
        // "android" は全小文字 → case-insensitive
        dict.add_word("android", "アンドロイド", 5);

        let result = dict.apply_to_text("iOS and Android");
        assert_eq!(result, "アイオーエス and アンドロイド");

        // "ios" (全小文字) は case-sensitive マップの "iOS" にマッチしない
        // case-insensitive マップにも無いのでそのまま
        let result2 = dict.apply_to_text("ios test");
        assert_eq!(result2, "ios test");
    }

    // ----- Longest match first -----

    #[test]
    fn test_longest_match_first() {
        let mut dict = CustomDictionary::new();
        dict.add_word("DB", "ディービー", 5);
        dict.add_word("DBMS", "ディービーエムエス", 5);

        // "DBMS" が先にマッチし、残った部分に "DB" はマッチしない
        let result = dict.apply_to_text("DBMS and DB");
        assert_eq!(result, "ディービーエムエス and ディービー");
    }

    // ----- Default constructor -----

    #[test]
    fn test_default_empty() {
        let dict = CustomDictionary::default();
        assert_eq!(dict.get_pronunciation("anything"), None);
    }

    // ----- Multiple dictionaries -----

    #[test]
    fn test_load_multiple_dictionaries() {
        let json1 = r#"{
            "version": "2.0",
            "entries": {
                "API": {"pronunciation": "エーピーアイ", "priority": 3}
            }
        }"#;
        let json2 = r#"{
            "version": "2.0",
            "entries": {
                "API": {"pronunciation": "エーピーアイ改", "priority": 8},
                "GPU": {"pronunciation": "ジーピーユー", "priority": 5}
            }
        }"#;
        let f1 = write_temp_json(json1);
        let f2 = write_temp_json(json2);

        let mut dict = CustomDictionary::new();
        dict.load_dictionary(&f1).unwrap();
        dict.load_dictionary(&f2).unwrap();

        // 2番目のファイルの方が優先度が高い → 上書き
        assert_eq!(dict.get_pronunciation("api"), Some("エーピーアイ改"));
        assert_eq!(dict.get_pronunciation("gpu"), Some("ジーピーユー"));
    }
}
