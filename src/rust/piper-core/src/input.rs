//! JSONL 入力パーサー (Python infer_onnx.py 互換)

use serde::Deserialize;

use crate::engine::SynthesisRequest;
use crate::error::PiperError;

/// JSONL の1行を表す構造体
#[derive(Debug, Deserialize)]
pub struct JsonlUtterance {
    pub phoneme_ids: Vec<i64>,

    #[serde(default)]
    pub speaker_id: Option<i64>,

    #[serde(default)]
    pub language_id: Option<i64>,

    #[serde(default)]
    pub prosody_features: Option<Vec<Option<ProsodyFeatureJson>>>,

    /// 出力ファイル名のヒント
    #[serde(default)]
    pub output_file: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ProsodyFeatureJson {
    pub a1: i32,
    pub a2: i32,
    pub a3: i32,
}

impl JsonlUtterance {
    /// JSONL 行をパース
    pub fn parse(line: &str) -> Result<Self, PiperError> {
        serde_json::from_str(line).map_err(PiperError::from)
    }

    /// SynthesisRequest に変換 (move semantics — self を消費して clone を回避)
    pub fn to_request(self, noise_scale: f32, length_scale: f32, noise_w: f32) -> SynthesisRequest {
        let prosody_features = self.prosody_features.map(|features| {
            features
                .iter()
                .map(|f| match f {
                    Some(pf) => [pf.a1, pf.a2, pf.a3],
                    None => [0, 0, 0],
                })
                .collect()
        });

        SynthesisRequest {
            phoneme_ids: self.phoneme_ids,
            prosody_features,
            speaker_id: self.speaker_id,
            language_id: self.language_id,
            noise_scale,
            length_scale,
            noise_w,
            speaker_embedding: None,
        }
    }
}

/// stdin から JSONL 行を読み込むイテレータ
pub struct JsonlReader<R: std::io::BufRead> {
    reader: R,
    line_buf: String,
}

impl<R: std::io::BufRead> JsonlReader<R> {
    pub fn new(reader: R) -> Self {
        Self {
            reader,
            line_buf: String::new(),
        }
    }
}

impl<R: std::io::BufRead> Iterator for JsonlReader<R> {
    type Item = Result<JsonlUtterance, PiperError>;

    fn next(&mut self) -> Option<Self::Item> {
        loop {
            self.line_buf.clear();
            match self.reader.read_line(&mut self.line_buf) {
                Ok(0) => return None, // EOF
                Ok(_) => {
                    let trimmed = self.line_buf.trim();
                    if trimmed.is_empty() {
                        continue; // skip empty lines without recursion
                    }
                    return Some(JsonlUtterance::parse(trimmed));
                }
                Err(e) => return Some(Err(PiperError::AudioOutput(e))),
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_minimal_jsonl() {
        let line = r#"{"phoneme_ids": [1, 2, 3]}"#;
        let utt = JsonlUtterance::parse(line).unwrap();
        assert_eq!(utt.phoneme_ids, vec![1, 2, 3]);
        assert!(utt.speaker_id.is_none());
        assert!(utt.prosody_features.is_none());
    }

    #[test]
    fn test_parse_full_jsonl() {
        let line = r#"{"phoneme_ids": [1, 2], "speaker_id": 5, "prosody_features": [{"a1": -2, "a2": 1, "a3": 5}, null]}"#;
        let utt = JsonlUtterance::parse(line).unwrap();
        assert_eq!(utt.speaker_id, Some(5));
        let pf = utt.prosody_features.as_ref().unwrap();
        assert_eq!(pf.len(), 2);
        assert_eq!(pf[0].as_ref().unwrap().a1, -2);
        assert!(pf[1].is_none());
    }

    #[test]
    fn test_to_request_defaults() {
        let line = r#"{"phoneme_ids": [1, 2, 3]}"#;
        let utt = JsonlUtterance::parse(line).unwrap();
        let req = utt.to_request(0.667, 1.0, 0.8);
        assert_eq!(req.noise_scale, 0.667);
        assert_eq!(req.length_scale, 1.0);
        assert!(req.speaker_id.is_none());
    }

    #[test]
    fn test_jsonl_reader() {
        let input = "{ \"phoneme_ids\": [1] }\n{ \"phoneme_ids\": [2, 3] }\n";
        let reader = JsonlReader::new(input.as_bytes());
        let results: Vec<_> = reader.collect();
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].as_ref().unwrap().phoneme_ids, vec![1]);
        assert_eq!(results[1].as_ref().unwrap().phoneme_ids, vec![2, 3]);
    }
}
