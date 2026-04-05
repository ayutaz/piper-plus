//! ONNX 推論エンジン
//!
//! VITS モデルの ONNX Runtime 推論を行う。
//! 入力テンソルの構築・条件付きテンソル追加・出力変換を担当。

use std::borrow::Cow;
use std::path::Path;
use std::time::Instant;

use ort::session::Session;
use ort::session::builder::GraphOptimizationLevel;
use ort::value::Tensor;

use crate::audio::audio_float_to_int16;
use crate::config::VoiceConfig;
use crate::error::PiperError;

/// VITS 小モデルの intra-op スレッド上限。
/// 4 以上では待機コストが推論時間を上回る。
const MAX_INTRA_THREADS: usize = 4;

/// デフォルトの warmup 実行回数。
/// ORT JIT キャッシュは 1-2 回で安定するが、安全マージンとして 2 回。
pub const DEFAULT_WARMUP_RUNS: usize = 2;

/// warmup 用のダミー phoneme 入力長。
/// 本番入力 (50-200) と同程度の形状で ORT メモリアロケーションを温める。
const WARMUP_PHONEME_LENGTH: usize = 100;

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
    /// Phoneme durations from the model (if available).
    /// Shape: [phoneme_length], each value = number of frames.
    pub durations: Option<Vec<f32>>,
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
    /// `device` は `"cpu"`, `"auto"`, `"cuda"`, `"cuda:0"`, `"coreml"`, `"directml"`, `"tensorrt"` のいずれか。
    /// `"auto"` 指定時は CUDA を試行し、失敗すれば CPU にフォールバックする。
    pub fn load(model_path: &Path, config: &VoiceConfig, device: &str) -> Result<Self, PiperError> {
        // デバイス文字列をパースして GPU プロバイダを設定
        // "auto" は parse_device_string 内でフォールバックするが、
        // 明示的なデバイス指定 (e.g. "cuda:0") が不正な場合はエラーを返す。
        let device_type = crate::gpu::parse_device_string(device)
            .map_err(|e| PiperError::ModelLoad(format!("invalid device '{}': {}", device, e)))?;

        // COLD-M1: VITS は小モデルのためスレッド数上限を設ける。
        // 過剰なスレッド生成はオーバーヘッドになる。
        // 論理コア数 / 2 で HT 分を除外し物理コア近似 (Python/C# と同一ロジック)。
        let num_intra_threads = std::thread::available_parallelism()
            .map(|n| (n.get() / 2).max(1))
            .unwrap_or(1)
            .min(MAX_INTRA_THREADS);

        // COLD-M5 + F1/D5: 最適化済みモデルキャッシュ
        // キャッシュパスにデバイス名を含める (D5: CPU/CUDA 混用防止)。
        // センチネルファイル (.ok) で書き込み完了を保証 (F1: 中断耐性)。
        let device_label = device_type.to_string().replace(':', ".");
        let cache_ext = format!("{}.opt.onnx", device_label);
        let optimized_path = model_path.with_extension(&cache_ext);
        let sentinel_path = {
            let mut s = optimized_path.as_os_str().to_owned();
            s.push(".ok");
            std::path::PathBuf::from(s)
        };

        // キャッシュ有効: .opt.onnx と .ok の両方が存在する場合のみ
        let use_cached = optimized_path.exists() && sentinel_path.exists();

        let (load_path, use_cached) = if use_cached {
            tracing::info!("Loading pre-optimized model from {:?}", optimized_path);
            (optimized_path.clone(), true)
        } else {
            // 不完全なキャッシュがあれば削除
            if optimized_path.exists() && !sentinel_path.exists() {
                tracing::warn!(
                    "Removing incomplete cache {:?} (missing sentinel)",
                    optimized_path
                );
                let _ = std::fs::remove_file(&optimized_path);
            }
            (model_path.to_path_buf(), false)
        };

        let mut builder = Session::builder()
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
            .with_intra_threads(num_intra_threads)
            .map_err(|e| PiperError::ModelLoad(format!("intra_threads: {e}")))?
            .with_inter_threads(1)
            .map_err(|e| PiperError::ModelLoad(format!("inter_threads: {e}")))?
            // メモリパターン有効化: 推論パターンを記憶してアロケーションを最適化
            .with_memory_pattern(true)
            .map_err(|e| PiperError::ModelLoad(format!("memory_pattern: {e}")))?
            // 動的ブロックサイズ: intra-op スレッドの作業分割を細粒度化しレイテンシ分散を低減
            .with_dynamic_block_base(4)
            .map_err(|e| PiperError::ModelLoad(format!("dynamic_block_base: {e}")))?;

        if use_cached {
            // 最適化済みモデルを直接ロード: 再最適化をスキップ
            builder = builder
                .with_optimization_level(GraphOptimizationLevel::Disable)
                .map_err(|e| PiperError::ModelLoad(format!("optimization_level: {e}")))?;
        } else {
            // 初回: 最適化を実行し、結果を .opt.onnx に保存
            // 書き込み権限がない場合は warning のみでフォールバック
            match builder.with_optimized_model_path(&optimized_path) {
                Ok(b) => {
                    builder = b;
                    tracing::info!("ORT will save optimized model to {:?}", optimized_path);
                }
                Err(e) => {
                    let msg = e.to_string();
                    builder = e.recover();
                    tracing::warn!(
                        "Could not set optimized model path {:?}: {} (continuing without cache)",
                        optimized_path,
                        msg
                    );
                }
            }
        }

        let (mut builder, actual_device) =
            crate::gpu::configure_session_builder(builder, &device_type)
                .map_err(|e| PiperError::ModelLoad(format!("device config: {e}")))?;

        tracing::info!("Using device: {}", actual_device);

        let session = builder
            .commit_from_file(&load_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

        // F1: セッション作成成功後にセンチネルファイルを書き込む
        if !use_cached && optimized_path.exists() {
            if let Err(e) = std::fs::write(&sentinel_path, b"ok") {
                tracing::warn!("Failed to write sentinel {:?}: {}", sentinel_path, e);
            } else {
                tracing::info!("Cache sentinel written: {:?}", sentinel_path);
            }
        }

        // モデルの入出力ノード名から能力を自動検出
        let input_names: Vec<String> = session
            .inputs()
            .iter()
            .map(|i| i.name().to_string())
            .collect();
        let output_names: Vec<String> = session
            .outputs()
            .iter()
            .map(|o| o.name().to_string())
            .collect();

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
    pub fn synthesize(
        &mut self,
        request: &SynthesisRequest,
    ) -> Result<SynthesisResult, PiperError> {
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
            request.phoneme_ids.to_vec().into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("input tensor: {e}")))?;

        // 2. input_lengths: int64 [1]
        let lengths_tensor =
            Tensor::from_array(([1_usize], vec![phoneme_len as i64].into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("input_lengths tensor: {e}")))?;

        // 3. scales: float32 [3]
        let scales_tensor = Tensor::from_array((
            [3_usize],
            vec![request.noise_scale, request.length_scale, request.noise_w].into_boxed_slice(),
        ))
        .map_err(|e| PiperError::Inference(format!("scales tensor: {e}")))?;

        // 4. sid: int64 [1] (条件付き)
        let sid_val = request.speaker_id.unwrap_or(0);
        let sid_tensor = if self.capabilities.has_sid {
            Some(
                Tensor::from_array(([1_usize], vec![sid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("sid tensor: {e}")))?,
            )
        } else {
            None
        };

        // 5. lid: int64 [1] (条件付き)
        let lid_val = request.language_id.unwrap_or(0);
        let lid_tensor = if self.capabilities.has_lid {
            Some(
                Tensor::from_array(([1_usize], vec![lid_val].into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("lid tensor: {e}")))?,
            )
        } else {
            None
        };

        // 6. prosody_features: int64 [1, phoneme_len, 3] (条件付き)
        let prosody_tensor = if self.capabilities.has_prosody {
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
            Some(
                Tensor::from_array(([1_usize, pf_len, 3], flat.into_boxed_slice()))
                    .map_err(|e| PiperError::Inference(format!("prosody tensor: {e}")))?,
            )
        } else {
            None
        };

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

        // float32 -> int16 ピーク正規化
        let audio_i16 = audio_float_to_int16(audio_slice);
        let audio_seconds = audio_i16.len() as f64 / self.sample_rate as f64;

        // --- duration テンソル抽出 (オプション) ---
        let durations = if self.capabilities.has_duration_output {
            match outputs.get("durations") {
                Some(d) => match d.try_extract_tensor::<f32>() {
                    Ok((_shape, data)) => {
                        let vec = data.to_vec();
                        tracing::debug!("Duration tensor extracted: {} values", vec.len());
                        Some(vec)
                    }
                    Err(e) => {
                        tracing::warn!(
                            "Duration tensor extraction failed (shape/type mismatch): {}. \
                             Expected f32 tensor with shape [1, phoneme_length].",
                            e
                        );
                        None
                    }
                },
                None => {
                    tracing::warn!(
                        "Model declares 'durations' output but tensor was not found in results"
                    );
                    None
                }
            }
        } else {
            None
        };

        Ok(SynthesisResult {
            audio: audio_i16,
            sample_rate: self.sample_rate,
            infer_seconds,
            audio_seconds,
            durations,
        })
    }

    /// ORT グラフ最適化キャッシュを温める。
    /// 本番入力と同程度の形状でダミー推論を `runs` 回実行する。
    pub fn warmup(&mut self, runs: usize) -> Result<(), PiperError> {
        let mut dummy_ids = vec![8i64; WARMUP_PHONEME_LENGTH]; // dummy phonemes
        dummy_ids[0] = 1; // BOS
        dummy_ids[WARMUP_PHONEME_LENGTH - 1] = 2; // EOS
        let dummy_request = SynthesisRequest {
            phoneme_ids: dummy_ids,
            ..SynthesisRequest::default()
        };
        for i in 0..runs {
            let start = std::time::Instant::now();
            let _ = self.synthesize(&dummy_request)?;
            tracing::debug!("warmup run {}/{}: {:?}", i + 1, runs, start.elapsed());
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;

    // -----------------------------------------------------------------------
    // COLD-M1: スレッド設定テスト
    // -----------------------------------------------------------------------

    #[test]
    fn test_intra_threads_capped_at_max() {
        let available = std::thread::available_parallelism()
            .map(|n| n.get())
            .unwrap_or(2);
        let num_intra_threads = available.min(MAX_INTRA_THREADS);
        assert!(num_intra_threads >= 1);
        assert!(num_intra_threads <= MAX_INTRA_THREADS);
    }

    #[test]
    fn test_thread_count_low_cpu() {
        assert_eq!(2_usize.min(MAX_INTRA_THREADS), 2);
    }

    #[test]
    fn test_thread_count_high_cpu() {
        assert_eq!(32_usize.min(MAX_INTRA_THREADS), MAX_INTRA_THREADS);
    }

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
            durations: None,
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
            durations: None,
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

    // -----------------------------------------------------------------------
    // Additional TDD tests
    // -----------------------------------------------------------------------

    #[test]
    fn test_synthesis_result_with_durations() {
        let result = SynthesisResult {
            audio: vec![0i16; 22050],
            sample_rate: 22050,
            infer_seconds: 0.3,
            audio_seconds: 1.0,
            durations: Some(vec![1.0, 2.0, 3.0]),
        };
        let durations = result.durations.as_ref().unwrap();
        assert_eq!(durations.len(), 3);
        assert!((durations[0] - 1.0).abs() < 1e-6);
        assert!((durations[1] - 2.0).abs() < 1e-6);
        assert!((durations[2] - 3.0).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_result_rtf_infinity() {
        // infer_seconds > 0 but audio_seconds = 0 => RTF should be 0.0 (guard)
        let result = SynthesisResult {
            audio: Vec::new(),
            sample_rate: 22050,
            infer_seconds: 1.5,
            audio_seconds: 0.0,
            durations: None,
        };
        assert!((result.real_time_factor() - 0.0).abs() < 1e-6);
    }

    #[test]
    fn test_synthesis_request_custom_values() {
        let req = SynthesisRequest {
            phoneme_ids: vec![1, 2, 3, 4, 5],
            prosody_features: Some(vec![
                [1, 2, 3],
                [4, 5, 6],
                [7, 8, 9],
                [10, 11, 12],
                [13, 14, 15],
            ]),
            speaker_id: Some(42),
            language_id: Some(3),
            noise_scale: 0.333,
            length_scale: 1.5,
            noise_w: 0.5,
        };
        assert_eq!(req.phoneme_ids.len(), 5);
        assert_eq!(req.speaker_id, Some(42));
        assert_eq!(req.language_id, Some(3));
        assert!((req.noise_scale - 0.333).abs() < 1e-6);
        assert!((req.length_scale - 1.5).abs() < 1e-6);
        assert!((req.noise_w - 0.5).abs() < 1e-6);
        let pf = req.prosody_features.as_ref().unwrap();
        assert_eq!(pf.len(), 5);
        assert_eq!(pf[0], [1, 2, 3]);
    }

    #[test]
    fn test_model_capabilities_all_true() {
        let caps = ModelCapabilities {
            has_sid: true,
            has_lid: true,
            has_prosody: true,
            has_duration_output: true,
        };
        assert!(caps.has_sid);
        assert!(caps.has_lid);
        assert!(caps.has_prosody);
        assert!(caps.has_duration_output);
    }

    #[test]
    fn test_model_capabilities_all_false() {
        let caps = ModelCapabilities {
            has_sid: false,
            has_lid: false,
            has_prosody: false,
            has_duration_output: false,
        };
        assert!(!caps.has_sid);
        assert!(!caps.has_lid);
        assert!(!caps.has_prosody);
        assert!(!caps.has_duration_output);
    }

    // -----------------------------------------------------------------------
    // COLD-M2: Warmup テスト
    // -----------------------------------------------------------------------

    #[test]
    fn test_warmup_request_is_valid() {
        let mut dummy_ids = vec![8i64; WARMUP_PHONEME_LENGTH]; // dummy phonemes
        dummy_ids[0] = 1; // BOS
        dummy_ids[WARMUP_PHONEME_LENGTH - 1] = 2; // EOS
        let req = SynthesisRequest {
            phoneme_ids: dummy_ids,
            ..SynthesisRequest::default()
        };
        assert!(!req.phoneme_ids.is_empty());
        assert_eq!(req.phoneme_ids.len(), WARMUP_PHONEME_LENGTH);
        assert_eq!(req.phoneme_ids[0], 1); // BOS
        assert_eq!(req.phoneme_ids[WARMUP_PHONEME_LENGTH - 1], 2); // EOS
        assert_eq!(req.phoneme_ids[1], 8); // dummy phoneme
    }

    // -----------------------------------------------------------------------
    // COLD-M5 + F1/D5: 最適化済みモデルキャッシュ テスト
    // -----------------------------------------------------------------------

    /// Helper: build device-labelled cache path (mirrors engine.rs load logic).
    fn build_cache_path(model_path: &Path, device_label: &str) -> PathBuf {
        let cache_ext = format!("{}.opt.onnx", device_label);
        model_path.with_extension(&cache_ext)
    }

    /// Helper: build sentinel path from cache path.
    fn build_sentinel_path(optimized_path: &Path) -> PathBuf {
        let mut s = optimized_path.as_os_str().to_owned();
        s.push(".ok");
        PathBuf::from(s)
    }

    #[test]
    fn test_optimized_model_path_construction_cpu() {
        let model_path = PathBuf::from("/data/models/test.onnx");
        let opt_path = build_cache_path(&model_path, "cpu");
        assert_eq!(opt_path.to_str().unwrap(), "/data/models/test.cpu.opt.onnx");
    }

    #[test]
    fn test_optimized_model_path_construction_cuda() {
        let model_path = PathBuf::from("/data/models/test.onnx");
        // DeviceType::Cuda { device_id: 0 } displays as "cuda:0", replace ':' -> '.'
        let device_label = "cuda:0".replace(':', ".");
        let opt_path = build_cache_path(&model_path, &device_label);
        assert_eq!(
            opt_path.to_str().unwrap(),
            "/data/models/test.cuda.0.opt.onnx"
        );
    }

    #[test]
    fn test_optimized_model_path_from_nested_dir() {
        let model_path = PathBuf::from("/home/user/models/tsukuyomi/model.onnx");
        let opt_path = build_cache_path(&model_path, "cpu");
        assert_eq!(
            opt_path.to_str().unwrap(),
            "/home/user/models/tsukuyomi/model.cpu.opt.onnx"
        );
    }

    #[test]
    fn test_optimized_model_path_preserves_parent() {
        let model_path = PathBuf::from("/data/models/test.onnx");
        let opt_path = build_cache_path(&model_path, "cpu");
        assert_eq!(opt_path.parent(), model_path.parent());
    }

    #[test]
    fn test_sentinel_path_construction() {
        let model_path = PathBuf::from("/data/models/test.onnx");
        let opt_path = build_cache_path(&model_path, "cpu");
        let sentinel = build_sentinel_path(&opt_path);
        assert_eq!(
            sentinel.to_str().unwrap(),
            "/data/models/test.cpu.opt.onnx.ok"
        );
    }

    #[test]
    fn test_use_cached_requires_both_files() {
        // Simulate: cache used only when BOTH opt and sentinel exist
        let opt_exists = true;
        let sentinel_exists = true;
        let use_cached = opt_exists && sentinel_exists;
        assert!(use_cached);
    }

    #[test]
    fn test_no_cache_when_sentinel_missing() {
        // Simulate: opt exists but sentinel missing => incomplete write
        let opt_exists = true;
        let sentinel_exists = false;
        let use_cached = opt_exists && sentinel_exists;
        assert!(!use_cached);
    }

    #[test]
    fn test_no_cache_when_opt_missing() {
        // Simulate: neither file exists => no cache
        let opt_exists = false;
        let sentinel_exists = false;
        let use_cached = opt_exists && sentinel_exists;
        assert!(!use_cached);
    }

    #[test]
    fn test_device_label_colon_replacement() {
        // DeviceType display produces "cuda:0", we replace ':' -> '.'
        let label = "cuda:0".replace(':', ".");
        assert_eq!(label, "cuda.0");
        assert!(!label.contains(':'));
    }

    // -----------------------------------------------------------------------
    // SessionBuilder 設定テスト (memory_pattern, dynamic_block_base)
    // -----------------------------------------------------------------------

    #[test]
    fn test_session_builder_with_memory_pattern_and_dynamic_block() {
        // SessionBuilder に memory_pattern(true) と dynamic_block_base(4) を設定して
        // エラーが発生しないことを検証する。
        let builder = Session::builder()
            .expect("session builder")
            .with_intra_threads(1)
            .expect("intra_threads")
            .with_inter_threads(1)
            .expect("inter_threads")
            .with_memory_pattern(true)
            .expect("memory_pattern")
            .with_dynamic_block_base(4)
            .expect("dynamic_block_base");
        // builder が正常に構築されることを確認 (型の存在で検証)
        let _ = builder;
    }

    #[test]
    fn test_device_label_cpu_no_colon() {
        let label = "cpu".replace(':', ".");
        assert_eq!(label, "cpu");
    }

    #[test]
    fn test_device_label_directml() {
        let label = "directml:1".replace(':', ".");
        assert_eq!(label, "directml.1");
        let model_path = PathBuf::from("/data/models/test.onnx");
        let opt_path = build_cache_path(&model_path, &label);
        assert_eq!(
            opt_path.to_str().unwrap(),
            "/data/models/test.directml.1.opt.onnx"
        );
    }

    #[test]
    fn test_sentinel_file_io_roundtrip() {
        // Write and read back sentinel content
        let dir = std::env::temp_dir().join("piper_test_sentinel");
        let _ = std::fs::create_dir_all(&dir);
        let sentinel = dir.join("test.cpu.opt.onnx.ok");
        std::fs::write(&sentinel, b"ok").unwrap();
        assert!(sentinel.exists());
        let content = std::fs::read(&sentinel).unwrap();
        assert_eq!(content, b"ok");
        let _ = std::fs::remove_file(&sentinel);
        let _ = std::fs::remove_dir(&dir);
    }
}
