//! ONNX 推論エンジン
//!
//! VITS モデルの ONNX Runtime 推論を行う。
//! 入力テンソルの構築・条件付きテンソル追加・出力変換を担当。

use std::borrow::Cow;
use std::path::Path;
use std::time::Instant;

use ort::session::Session;
use ort::value::Tensor;

use crate::audio::audio_float_to_int16;
use crate::config::VoiceConfig;
use crate::error::PiperError;

/// 合成パラメータ
#[derive(Debug, Clone)]
pub struct SynthesisRequest {
    pub phoneme_ids: Vec<i64>,
    pub prosody_features: Option<Vec<[i32; 3]>>,
    pub speaker_id: Option<i64>,
    pub language_id: Option<i64>,
    pub noise_scale: f32,
    pub length_scale: f32,
    pub noise_w: f32,
}

impl Default for SynthesisRequest {
    fn default() -> Self {
        Self {
            phoneme_ids: Vec::new(),
            prosody_features: None,
            speaker_id: None,
            language_id: None,
            noise_scale: 0.667,
            length_scale: 1.0,
            noise_w: 0.8,
        }
    }
}

/// 合成結果
#[derive(Debug)]
pub struct SynthesisResult {
    pub audio: Vec<i16>,
    pub sample_rate: u32,
    pub infer_seconds: f64,
    pub audio_seconds: f64,
}

impl SynthesisResult {
    /// リアルタイムファクタ (推論時間 / 音声時間)。
    /// 1.0 未満ならリアルタイムより高速。
    pub fn real_time_factor(&self) -> f64 {
        if self.audio_seconds > 0.0 {
            self.infer_seconds / self.audio_seconds
        } else {
            0.0
        }
    }
}

/// モデルの ONNX 入出力ノードから検出した能力情報
#[derive(Debug, Clone)]
pub struct ModelCapabilities {
    pub has_sid: bool,
    pub has_lid: bool,
    pub has_prosody: bool,
    pub has_duration_output: bool,
}

/// ONNX 推論エンジン
pub struct OnnxEngine {
    session: Session,
    capabilities: ModelCapabilities,
    sample_rate: u32,
}

impl OnnxEngine {
    /// ONNX モデルを読み込んでエンジンを初期化する。
    ///
    /// `device` は `"cpu"`, `"gpu"`, `"auto"` のいずれか。
    /// `"gpu"` / `"auto"` 指定時は CUDA を試行し、失敗すれば CPU にフォールバックする。
    pub fn load(model_path: &Path, config: &VoiceConfig, device: &str) -> Result<Self, PiperError> {
        let mut builder = Session::builder()
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

        // GPU support is not yet implemented; always use CPU.
        if device == "gpu" {
            tracing::warn!("GPU requested but not yet supported, using CPU");
        }

        let session = builder
            .commit_from_file(model_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

        // モデルの入出力ノード名から能力を自動検出
        let input_names: Vec<String> = session.inputs().iter().map(|i| i.name().to_string()).collect();
        let output_names: Vec<String> = session.outputs().iter().map(|o| o.name().to_string()).collect();

        let has_input = |name: &str| input_names.iter().any(|n| n == name);
        let has_output = |name: &str| output_names.iter().any(|n| n == name);

        let capabilities = ModelCapabilities {
            has_sid: has_input("sid"),
            has_lid: has_input("lid"),
            has_prosody: has_input("prosody_features"),
            has_duration_output: has_output("durations"),
        };

        tracing::info!(
            "Model loaded: inputs={:?}, outputs={:?}",
            input_names,
            output_names,
        );
        tracing::info!(
            "Capabilities: sid={}, lid={}, prosody={}, durations={}",
            capabilities.has_sid,
            capabilities.has_lid,
            capabilities.has_prosody,
            capabilities.has_duration_output,
        );

        Ok(Self {
            session,
            capabilities,
            sample_rate: config.audio.sample_rate,
        })
    }

    /// モデルの能力情報を返す
    pub fn capabilities(&self) -> &ModelCapabilities {
        &self.capabilities
    }

    /// サンプルレートを返す
    pub fn sample_rate(&self) -> u32 {
        self.sample_rate
    }

    /// ONNX 推論を実行して音声を生成する。
    ///
    /// ONNX 入力テンソル順序:
    /// 1. `input` (phoneme_ids): int64 \[1, phoneme_length\]
    /// 2. `input_lengths`: int64 \[1\]
    /// 3. `scales`: float32 \[3\] = \[noise_scale, length_scale, noise_w\]
    /// 4. `sid` (条件付き): int64 \[1\] -- has_sid が true のとき
    /// 5. `lid` (条件付き): int64 \[1\] -- has_lid が true のとき
    /// 6. `prosody_features` (条件付き): int64 \[1, phoneme_length, 3\]
    ///
    /// ONNX 出力:
    /// - `output`: float32 \[1, 1, audio_samples\]
    /// - `durations` (オプション): float32 \[1, phoneme_length\]
    pub fn synthesize(&mut self, request: &SynthesisRequest) -> Result<SynthesisResult, PiperError> {
        let phoneme_len = request.phoneme_ids.len();
        if phoneme_len == 0 {
            return Err(PiperError::Inference("empty phoneme_ids".to_string()));
        }

        // --- 入力テンソル構築 ---
        // 条件付き入力があるため動的に ValueMap を構築する。
        // テンソルは run() 完了まで生存する必要があるため、ここで全て確保する。

        // 1. input: int64 [1, phoneme_len]
        let input_tensor = Tensor::from_array((
            [1_usize, phoneme_len],
            request.phoneme_ids.clone().into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("input tensor: {e}")))?;

        // 2. input_lengths: int64 [1]
        let lengths_tensor = Tensor::from_array((
            [1_usize],
            vec![phoneme_len as i64].into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("input_lengths tensor: {e}")))?;

        // 3. scales: float32 [3]
        let scales_tensor = Tensor::from_array((
            [3_usize],
            vec![request.noise_scale, request.length_scale, request.noise_w].into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("scales tensor: {e}")))?;

        // 4. sid: int64 [1] (条件付き)
        let sid_tensor;
        let sid_val = request.speaker_id.unwrap_or(0);
        if self.capabilities.has_sid {
            sid_tensor = Some(
                Tensor::from_array(([1_usize], vec![sid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("sid tensor: {e}")))?,
            );
        } else {
            sid_tensor = None;
        }

        // 5. lid: int64 [1] (条件付き)
        let lid_tensor;
        let lid_val = request.language_id.unwrap_or(0);
        if self.capabilities.has_lid {
            lid_tensor = Some(
                Tensor::from_array(([1_usize], vec![lid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("lid tensor: {e}")))?,
            );
        } else {
            lid_tensor = None;
        }

        // 6. prosody_features: int64 [1, phoneme_len, 3] (条件付き)
        let prosody_tensor;
        if self.capabilities.has_prosody {
            let flat: Vec<i64> = if let Some(ref features) = request.prosody_features {
                features
                    .iter()
                    .flat_map(|f| [f[0] as i64, f[1] as i64, f[2] as i64])
                    .collect()
            } else {
                // prosody ノードは存在するがリクエストに特徴量がない場合はゼロ埋め
                vec![0i64; phoneme_len * 3]
            };
            let pf_len = flat.len() / 3;
            prosody_tensor = Some(
                Tensor::from_array((
                    [1_usize, pf_len, 3],
                    flat.into_boxed_slice(),
                ))
                .map_err(|e| PiperError::Inference(format!("prosody tensor: {e}")))?,
            );
        } else {
            prosody_tensor = None;
        }

        // ValueMap を構築
        let mut inputs: Vec<(Cow<str>, ort::session::SessionInputValue<'_>)> =
            Vec::with_capacity(6);

        inputs.push(("input".into(), (&input_tensor).into()));
        inputs.push(("input_lengths".into(), (&lengths_tensor).into()));
        inputs.push(("scales".into(), (&scales_tensor).into()));

        if let Some(ref t) = sid_tensor {
            inputs.push(("sid".into(), t.into()));
        }
        if let Some(ref t) = lid_tensor {
            inputs.push(("lid".into(), t.into()));
        }
        if let Some(ref t) = prosody_tensor {
            inputs.push(("prosody_features".into(), t.into()));
        }

        // --- 推論実行 ---
        let start = Instant::now();

        let outputs = self
            .session
            .run(inputs)
            .map_err(|e| PiperError::Inference(e.to_string()))?;

        let infer_seconds = start.elapsed().as_secs_f64();

        // --- 出力テンソル処理 ---
        // output: float32 [1, 1, audio_samples]
        let (_shape, audio_slice) = outputs["output"]
            .try_extract_tensor::<f32>()
            .map_err(|e| PiperError::Inference(format!("extract output: {e}")))?;

        let audio_f32: Vec<f32> = audio_slice.to_vec();

        // float32 -> int16 ピーク正規化
        let audio_i16 = audio_float_to_int16(&audio_f32);
        let audio_seconds = audio_i16.len() as f64 / self.sample_rate as f64;

        Ok(SynthesisResult {
            audio: audio_i16,
            sample_rate: self.sample_rate,
            infer_seconds,
            audio_seconds,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_synthesis_request_default() {
        let req = SynthesisRequest::default();
        assert!(req.phoneme_ids.is_empty());
        assert!(req.prosody_features.is_none());
        assert!(req.speaker_id.is_none());
        assert!(req.language_id.is_none());
        assert!((req.noise_scale - 0.667).abs() < 1e-6);
        assert!((req.length_scale - 1.0).abs() < 1e-6);
        assert!((req.noise_w - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_result_rtf() {
        let result = SynthesisResult {
            audio: vec![0i16; 22050],
            sample_rate: 22050,
            infer_seconds: 0.5,
            audio_seconds: 1.0,
        };
        assert!((result.real_time_factor() - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_result_rtf_zero_audio() {
        let result = SynthesisResult {
            audio: Vec::new(),
            sample_rate: 22050,
            infer_seconds: 0.1,
            audio_seconds: 0.0,
        };
        assert!((result.real_time_factor()).abs() < 1e-6);
    }

    #[test]
    fn test_model_capabilities_debug() {
        let caps = ModelCapabilities {
            has_sid: true,
            has_lid: false,
            has_prosody: true,
            has_duration_output: false,
        };
        let debug = format!("{:?}", caps);
        assert!(debug.contains("has_sid: true"));
        assert!(debug.contains("has_lid: false"));
        assert!(debug.contains("has_prosody: true"));
        assert!(debug.contains("has_duration_output: false"));
    }
}
