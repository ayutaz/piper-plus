//! ONNX 推論エンジン
//!
//! VITS モデルの ONNX Runtime 推論を行う。
//! 入力テンソルの構築・条件付きテンソル追加・出力変換を担当。
//!
//! ## 短テキスト緩和策 (Strategy A + B)
//!
//! VITS は短い phoneme 列 (< 40 tokens) で Duration Predictor が
//! 不安定になり、音声が崩壊・0秒になる問題がある。
//! `synthesize()` 内で自動的に以下の緩和策を適用する:
//!
//! - **Strategy A (Silence Padding + Post-trim)**: pause トークン (ID=0) を
//!   BOS 直後と EOS 直前に均等挿入して MIN_PHONEME_IDS まで延長し、
//!   推論後に先頭・末尾の無音をトリムする。
//! - **Strategy B (Dynamic Scales Adjustment)**: noise_scale と noise_w を
//!   phoneme 長に比例して低減し、短い入力での雑音を抑制する。

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

// ---------------------------------------------------------------------------
// 短テキスト緩和策の定数 (Strategy A + B)
// docs/spec/short-text-contract.toml と同期させること。
// ---------------------------------------------------------------------------

/// 最小 phoneme ID 数。これ未満の場合 padding を挿入する。
///
/// Issue #356: 当初 40 と仕様で固定していたが、実機計測 (tsukuyomi 6lang) で
/// 8 phoneme 以上で安定合成可能と判明。40 では Strategy A が安定入力にも
/// 発動して padding アーティファクトを残してしまう。15 に下げて
/// 「こんにちは。」級は素通りさせ、極短文だけ Strategy A を発動させる。
pub const MIN_PHONEME_IDS: usize = 15;

/// Strategy A を発動する body 長 (= phoneme_ids から BOS/EOS を除いた数) の
/// 下限。これ未満では padding が body を圧倒し、pad token 由来の音が
/// 支配的になる (例: 「あ。」, body=2)。raw VITS 出力の方が結果として自然。
pub const MIN_BODY_FOR_STRATEGY_A: usize = 3;

/// `trim_padding_by_durations` がデフォルトで残す EOS フレーム数。
/// padding context で VITS が膨張させた EOS が末尾の余分音として聞こえるため
/// (issue #356)、デフォルトでは 0 にして EOS を完全削除する。
pub const TRIM_EOS_MAX_FRAMES: usize = 0;

/// RMS トリムの閾値。この RMS 以下の窓を無音とみなす。
const TRIM_THRESHOLD_RMS: f32 = 0.01;

/// トリム後に最低限保持するサンプル数 (22050 Hz x 0.1s)。
const TRIM_MIN_SAMPLES: usize = 2205;

/// RMS 計算の窓幅 (サンプル数)。
const TRIM_WINDOW_SIZE: usize = 256;

/// Pause トークン ID (= 0)。BOS/EOS 間に挿入する無音フィラー。
const PAUSE_TOKEN_ID: i64 = 0;

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
    /// Speaker embedding vector from a speaker encoder model (voice cloning).
    /// When provided, this overrides `speaker_id` for voice conditioning.
    /// Typical dimension: 256 floats (ECAPA-TDNN output).
    pub speaker_embedding: Option<Vec<f32>>,
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
            speaker_embedding: None,
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
    /// Whether the model accepts `speaker_embedding` (float32) and
    /// `speaker_embedding_mask` (int64) inputs for voice cloning.
    pub has_speaker_embedding: bool,
}

// ---------------------------------------------------------------------------
// 短テキスト緩和策ヘルパー
// ---------------------------------------------------------------------------

/// Strategy A: phoneme_ids を MIN_PHONEME_IDS まで pause トークンで延長する。
///
/// BOS (先頭) と EOS (末尾) を保持したまま、BOS 直後と EOS 直前に
/// pause トークン (ID=0) を均等挿入する。
/// prosody_features も同期して延長する (ゼロ埋め)。
///
/// 既に MIN_PHONEME_IDS 以上の場合は変更なし。
/// body 長 (= phoneme_ids - 2) が MIN_BODY_FOR_STRATEGY_A 未満の場合は
/// padding/body 比が大きくなりすぎるため Strategy A をスキップする
/// (issue #356)。
///
/// 戻り値の 4 番目・5 番目は挿入された front / back pad トークン数。
/// padding が行われなかった場合は両方 0。durations ベース post-trim で
/// pad token のフレーム範囲を正確に切るために必要。
///
/// **Breaking change (#356):** 旧シグネチャは 3 タプルだった。
/// `pad_short_phonemes()` 直接利用者は呼び出しを更新すること。
#[allow(clippy::type_complexity)]
pub fn pad_short_phonemes(
    phoneme_ids: &[i64],
    prosody_features: Option<&Vec<[i32; 3]>>,
) -> (Vec<i64>, Option<Vec<[i32; 3]>>, bool, usize, usize) {
    let body_len = phoneme_ids.len().saturating_sub(2);
    if body_len < MIN_BODY_FOR_STRATEGY_A {
        return (phoneme_ids.to_vec(), prosody_features.cloned(), false, 0, 0);
    }
    if phoneme_ids.len() >= MIN_PHONEME_IDS {
        return (phoneme_ids.to_vec(), prosody_features.cloned(), false, 0, 0);
    }

    let deficit = MIN_PHONEME_IDS - phoneme_ids.len();
    let front_pad = deficit / 2;
    let back_pad = deficit - front_pad;

    // phoneme_ids: [BOS, ...body..., EOS]
    // → [BOS, pad*front, ...body..., pad*back, EOS]
    let mut padded = Vec::with_capacity(MIN_PHONEME_IDS);
    if !phoneme_ids.is_empty() {
        padded.push(phoneme_ids[0]); // BOS
    }
    padded.extend(std::iter::repeat_n(PAUSE_TOKEN_ID, front_pad));
    if phoneme_ids.len() > 2 {
        padded.extend_from_slice(&phoneme_ids[1..phoneme_ids.len() - 1]);
    }
    padded.extend(std::iter::repeat_n(PAUSE_TOKEN_ID, back_pad));
    if phoneme_ids.len() > 1 {
        padded.push(phoneme_ids[phoneme_ids.len() - 1]); // EOS
    }

    // prosody_features を同期延長
    let padded_prosody = prosody_features.map(|pf| {
        let mut padded_pf = Vec::with_capacity(MIN_PHONEME_IDS);
        if !pf.is_empty() {
            padded_pf.push(pf[0]);
        }
        padded_pf.extend(std::iter::repeat_n([0i32, 0, 0], front_pad));
        if pf.len() > 2 {
            padded_pf.extend_from_slice(&pf[1..pf.len() - 1]);
        }
        padded_pf.extend(std::iter::repeat_n([0i32, 0, 0], back_pad));
        if pf.len() > 1 {
            padded_pf.push(pf[pf.len() - 1]);
        }
        padded_pf
    });

    (padded, padded_prosody, true, front_pad, back_pad)
}

/// Strategy A 精密 post-trim: モデルの `durations` 出力から padding に
/// 起因するサンプル数を計算して切り落とす。
///
/// Python (`src/python_run/piper/voice.py::_trim_padding_by_durations`)
/// と同じロジック・truncation で実装し、全ランタイムが同じ入力に対して
/// バイト一致の音声を返せるようにする (issue #356, クロスランタイム契約)。
///
/// 期待する padded layout:
///
/// ```text
/// [BOS, pad×front_pad, ...body..., pad×back_pad, EOS]
/// ```
///
/// `durations[i]` は VITS が phoneme i に割り当てたフレーム数。
/// `hop_size` を掛けてサンプル数に変換し、front 側 (BOS+front_pad) と
/// back 側 (back_pad+EOS over `eos_max_frames`) を削る。
///
/// すべての frame→sample 変換は `as i64` 経由の truncation
/// (Python の `int()` と一致) で行う。`round` を使うとランタイム間で
/// 1 サンプルのズレが生じるため避ける。
///
/// 引数が不整合 (`durations.is_empty()`, `hop_size == 0`,
/// `durations.len() < 1 + front_pad + back_pad + 1` など) のときは入力を
/// そのまま返す。
pub fn trim_padding_by_durations(
    audio: &[i16],
    durations: &[f32],
    front_pad: usize,
    back_pad: usize,
    hop_size: u32,
    eos_max_frames: usize,
) -> Vec<i16> {
    if front_pad == 0 && back_pad == 0 {
        return audio.to_vec();
    }
    if durations.is_empty() || hop_size == 0 {
        return audio.to_vec();
    }
    let expected_len = 1 + front_pad + back_pad + 1; // BOS + pads + EOS
    if durations.len() < expected_len {
        return audio.to_vec();
    }

    let hop = hop_size as f32;

    // Front: BOS + front padding samples (truncated).
    let front_sum: f32 = durations[0..1 + front_pad].iter().sum();
    let front_samples = (front_sum * hop) as i64;

    // Back: back padding samples + EOS excess (over eos_max_frames).
    let back_pad_sum: f32 = if back_pad > 0 {
        let start = durations.len() - 1 - back_pad;
        durations[start..durations.len() - 1].iter().sum()
    } else {
        0.0
    };
    let back_pad_samples = (back_pad_sum * hop) as i64;

    let eos_frames = durations[durations.len() - 1];
    let eos_excess = (eos_frames - eos_max_frames as f32).max(0.0);
    let back_samples = back_pad_samples + (eos_excess * hop) as i64;

    let total = audio.len() as i64;
    let start = front_samples.max(0);
    let mut end = total - back_samples;
    if end < start {
        end = start;
    }
    if start >= total || end <= 0 || start >= end {
        return audio.to_vec();
    }
    audio[start as usize..end as usize].to_vec()
}

/// Strategy A (post-trim): RMS ベースで先頭・末尾の無音をトリムする。
///
/// 窓幅 `TRIM_WINDOW_SIZE` の RMS が `TRIM_THRESHOLD_RMS` を超える
/// 最初・最後の位置を検出し、その範囲を返す。
/// 結果は最低 `TRIM_MIN_SAMPLES` サンプルを保持する。
pub fn trim_silence(audio: &[i16]) -> Vec<i16> {
    if audio.len() <= TRIM_MIN_SAMPLES {
        return audio.to_vec();
    }

    let rms_of_window = |start: usize| -> f32 {
        let end = (start + TRIM_WINDOW_SIZE).min(audio.len());
        let n = end - start;
        if n == 0 {
            return 0.0;
        }
        let sum_sq: f64 = audio[start..end]
            .iter()
            .map(|&s| {
                let f = s as f64 / 32768.0;
                f * f
            })
            .sum();
        (sum_sq / n as f64).sqrt() as f32
    };

    // フルウィンドウ数 + partial window の検出 (C++ と同一ロジック)
    let num_full_windows = audio.len() / TRIM_WINDOW_SIZE;
    let remainder = audio.len() % TRIM_WINDOW_SIZE;

    // total_windows: フルウィンドウ + partial (存在すれば 1)
    let total_windows = num_full_windows + if remainder > 0 { 1 } else { 0 };

    // 先頭: RMS > threshold の最初の窓を検出
    let mut first_above: Option<usize> = None;
    let mut last_above: Option<usize> = None;

    for w in 0..total_windows {
        let pos = w * TRIM_WINDOW_SIZE;
        if rms_of_window(pos) > TRIM_THRESHOLD_RMS {
            if first_above.is_none() {
                first_above = Some(w);
            }
            last_above = Some(w);
        }
    }

    let (trim_start, trim_end) = match (first_above, last_above) {
        (Some(first), Some(last)) => {
            let start = first * TRIM_WINDOW_SIZE;
            let end = ((last + 1) * TRIM_WINDOW_SIZE).min(audio.len());
            (start, end)
        }
        _ => {
            // 全て無音 -- 最低サンプル数を保持
            let safe_len = TRIM_MIN_SAMPLES.min(audio.len());
            return audio[..safe_len].to_vec();
        }
    };

    // 最低サンプル数を保証
    if trim_end <= trim_start || (trim_end - trim_start) < TRIM_MIN_SAMPLES {
        // トリムすると短すぎる場合は中央を保持
        let center = audio.len() / 2;
        let half = TRIM_MIN_SAMPLES / 2;
        let safe_start = center.saturating_sub(half);
        let safe_end = (safe_start + TRIM_MIN_SAMPLES).min(audio.len());
        return audio[safe_start..safe_end].to_vec();
    }

    audio[trim_start..trim_end].to_vec()
}

/// Strategy B: 短テキスト向けの scales 調整値を計算する。
///
/// phoneme 長が MIN_PHONEME_IDS 未満の場合、ratio に基づいて
/// noise_scale と noise_w を低減する。
/// 戻り値: (adjusted_noise_scale, adjusted_noise_w)
pub fn adjust_scales_for_short_text(
    phoneme_len: usize,
    noise_scale: f32,
    noise_w: f32,
) -> (f32, f32) {
    if phoneme_len >= MIN_PHONEME_IDS {
        return (noise_scale, noise_w);
    }
    let ratio = (phoneme_len as f32 / MIN_PHONEME_IDS as f32).clamp(0.0, 1.0);
    let adjusted_noise_scale = noise_scale * ratio.max(0.5);
    let adjusted_noise_w = noise_w * ratio.max(0.4);
    (adjusted_noise_scale, adjusted_noise_w)
}

/// ONNX 推論エンジン
pub struct OnnxEngine {
    session: Session,
    capabilities: ModelCapabilities,
    sample_rate: u32,
    /// VITS hop length (samples per acoustic frame), used by the
    /// durations-based Strategy A post-trim (#356).
    hop_size: u32,
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
        // コロンを除去: "cuda:0" → "cuda0" (C#/Python と統一)
        let device_label = device_type.to_string().replace(':', "");
        let cache_ext = format!("{}.opt.onnx", device_label);
        let optimized_path = model_path.with_extension(&cache_ext);
        let sentinel_path = {
            let mut s = optimized_path.as_os_str().to_owned();
            s.push(".ok");
            std::path::PathBuf::from(s)
        };

        // キャッシュ有効: .opt.onnx と .ok の両方が存在する場合のみ
        let cache_hit = optimized_path.exists() && sentinel_path.exists();

        // 不完全なキャッシュがあれば削除
        if !cache_hit && optimized_path.exists() && !sentinel_path.exists() {
            tracing::warn!(
                "Removing incomplete cache {:?} (missing sentinel)",
                optimized_path
            );
            let _ = std::fs::remove_file(&optimized_path);
        }

        // キャッシュヒット時のロード試行。失敗したらキャッシュを削除して通常パスにフォールスルー。
        if cache_hit {
            tracing::info!("Loading pre-optimized model from {:?}", optimized_path);
            match Self::build_session(&optimized_path, num_intra_threads, &device_type, true, None)
            {
                Ok((session, actual_device)) => {
                    tracing::info!("Using device: {}", actual_device);
                    return Self::finish_load(session, config);
                }
                Err(e) => {
                    tracing::warn!(
                        "Failed to load cached model {:?}, rebuilding: {}",
                        optimized_path,
                        e
                    );
                    let _ = std::fs::remove_file(&optimized_path);
                    let _ = std::fs::remove_file(&sentinel_path);
                }
            }
        }

        // 通常パス: 元モデルをロードし、最適化結果をキャッシュに保存
        let (session, actual_device) = Self::build_session(
            model_path,
            num_intra_threads,
            &device_type,
            false,
            Some(&optimized_path),
        )?;

        tracing::info!("Using device: {}", actual_device);

        // F1: セッション作成成功後にセンチネルファイルを書き込む
        if optimized_path.exists() {
            if let Err(e) = std::fs::write(&sentinel_path, b"ok") {
                tracing::warn!("Failed to write sentinel {:?}: {}", sentinel_path, e);
            } else {
                tracing::info!("Cache sentinel written: {:?}", sentinel_path);
            }
        }

        Self::finish_load(session, config)
    }

    /// SessionBuilder を構築し、モデルファイルからセッションをコミットする。
    ///
    /// `cached` が `true` の場合は最適化をスキップし、`false` の場合は
    /// `cache_save_path` に最適化結果を保存する。
    fn build_session(
        model_path: &Path,
        num_intra_threads: usize,
        device_type: &crate::gpu::DeviceType,
        cached: bool,
        cache_save_path: Option<&std::path::Path>,
    ) -> Result<(Session, crate::gpu::DeviceType), PiperError> {
        let mut builder = Session::builder()
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?
            .with_intra_threads(num_intra_threads)
            .map_err(|e| PiperError::ModelLoad(format!("intra_threads: {e}")))?
            .with_inter_threads(1)
            .map_err(|e| PiperError::ModelLoad(format!("inter_threads: {e}")))?
            // Sequential 実行モード: C#/C++/Python と統一。VITS は分岐が少なく並列化のメリットが薄い。
            .with_parallel_execution(false)
            .map_err(|e| PiperError::ModelLoad(format!("execution_mode: {e}")))?
            // メモリパターン有効化: 推論パターンを記憶してアロケーションを最適化
            .with_memory_pattern(true)
            .map_err(|e| PiperError::ModelLoad(format!("memory_pattern: {e}")))?
            // 動的ブロックサイズ: intra-op スレッドの作業分割を細粒度化しレイテンシ分散を低減
            .with_dynamic_block_base(4)
            .map_err(|e| PiperError::ModelLoad(format!("dynamic_block_base: {e}")))?;

        if cached {
            // 最適化済みモデルを直接ロード: 再最適化をスキップ
            builder = builder
                .with_optimization_level(GraphOptimizationLevel::Disable)
                .map_err(|e| PiperError::ModelLoad(format!("optimization_level: {e}")))?;
        } else if let Some(save_path) = cache_save_path {
            // 初回: 最適化を実行し、結果を .opt.onnx に保存
            // 書き込み権限がない場合は warning のみでフォールバック
            match builder.with_optimized_model_path(save_path) {
                Ok(b) => {
                    builder = b;
                    tracing::info!("ORT will save optimized model to {:?}", save_path);
                }
                Err(e) => {
                    let msg = e.to_string();
                    builder = e.recover();
                    tracing::warn!(
                        "Could not set optimized model path {:?}: {} (continuing without cache)",
                        save_path,
                        msg
                    );
                }
            }
        }

        let (mut builder, actual_device) =
            crate::gpu::configure_session_builder(builder, device_type)
                .map_err(|e| PiperError::ModelLoad(format!("device config: {e}")))?;

        let session = builder
            .commit_from_file(model_path)
            .map_err(|e| PiperError::ModelLoad(e.to_string()))?;

        Ok((session, actual_device))
    }

    /// セッションからモデル能力を検出し、`OnnxEngine` を構築する。
    fn finish_load(session: Session, config: &VoiceConfig) -> Result<Self, PiperError> {
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
            has_speaker_embedding: has_input("speaker_embedding"),
        };

        tracing::info!(
            "Model loaded: inputs={:?}, outputs={:?}",
            input_names,
            output_names,
        );
        tracing::info!(
            "Capabilities: sid={}, lid={}, prosody={}, durations={}, speaker_embedding={}",
            capabilities.has_sid,
            capabilities.has_lid,
            capabilities.has_prosody,
            capabilities.has_duration_output,
            capabilities.has_speaker_embedding,
        );

        // hop_size: 0 (config 欠如時の serde default 直前の異常値) は
        // contract 既定の 256 にフォールバック。
        let hop_size = if config.audio.hop_size > 0 {
            config.audio.hop_size
        } else {
            256
        };

        Ok(Self {
            session,
            capabilities,
            sample_rate: config.audio.sample_rate,
            hop_size,
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
    /// 7. `speaker_embedding` (条件付き): float32 \[1, embedding_dim\] -- voice cloning
    /// 8. `speaker_embedding_mask` (条件付き): int64 \[1\] -- 1 if embedding active
    ///
    /// ONNX 出力:
    /// - `output`: float32 \[1, 1, audio_samples\]
    /// - `durations` (オプション): float32 \[1, phoneme_length\]
    pub fn synthesize(
        &mut self,
        request: &SynthesisRequest,
    ) -> Result<SynthesisResult, PiperError> {
        let original_len = request.phoneme_ids.len();
        if original_len == 0 {
            return Err(PiperError::Inference("empty phoneme_ids".to_string()));
        }

        // --- Strategy A: Silence Padding ---
        // 短い phoneme 列を pause トークンで MIN_PHONEME_IDS まで延長する。
        let (phoneme_ids, prosody_features, was_padded, front_pad, back_pad) =
            pad_short_phonemes(&request.phoneme_ids, request.prosody_features.as_ref());
        let phoneme_len = phoneme_ids.len();

        if was_padded {
            tracing::debug!(
                "Short text padding: {} -> {} phonemes",
                original_len,
                phoneme_len
            );
        }

        // --- Strategy B: Dynamic Scales Adjustment ---
        // 短い入力に対して noise_scale / noise_w を低減する。
        // original_len を使用して ratio を計算 (padding 前の実際の長さ基準)。
        let (noise_scale, noise_w) =
            adjust_scales_for_short_text(original_len, request.noise_scale, request.noise_w);

        if original_len < MIN_PHONEME_IDS {
            tracing::debug!(
                "Short text scales: noise_scale {:.3} -> {:.3}, noise_w {:.3} -> {:.3}",
                request.noise_scale,
                noise_scale,
                request.noise_w,
                noise_w,
            );
        }

        // --- 入力テンソル構築 ---
        // 条件付き入力があるため動的に ValueMap を構築する。
        // テンソルは run() 完了まで生存する必要があるため、ここで全て確保する。

        // 1. input: int64 [1, phoneme_len]
        let input_tensor =
            Tensor::from_array(([1_usize, phoneme_len], phoneme_ids.into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("input tensor: {e}")))?;

        // 2. input_lengths: int64 [1]
        let lengths_tensor =
            Tensor::from_array(([1_usize], vec![phoneme_len as i64].into_boxed_slice()))
                .map_err(|e| PiperError::Inference(format!("input_lengths tensor: {e}")))?;

        // 3. scales: float32 [3]
        let scales_tensor = Tensor::from_array((
            [3_usize],
            vec![noise_scale, request.length_scale, noise_w].into_boxed_slice(),
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
        //    Strategy A で延長済みの prosody_features を使用する。
        let prosody_tensor = if self.capabilities.has_prosody {
            let flat: Vec<i64> = if let Some(ref features) = prosody_features {
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

        // 7. speaker_embedding: float32 [1, embedding_dim] (条件付き)
        // 8. speaker_embedding_mask: int64 [1] (条件付き, 1 = embedding active)
        let speaker_emb_tensor = if self.capabilities.has_speaker_embedding {
            if let Some(ref emb) = request.speaker_embedding {
                let emb_dim = emb.len();
                Some(
                    Tensor::from_array(([1_usize, emb_dim], emb.to_vec().into_boxed_slice()))
                        .map_err(|e| {
                            PiperError::Inference(format!("speaker_embedding tensor: {e}"))
                        })?,
                )
            } else {
                None
            }
        } else {
            None
        };

        let speaker_emb_mask_tensor = if self.capabilities.has_speaker_embedding {
            let mask_val: i64 = if request.speaker_embedding.is_some() {
                1
            } else {
                0
            };
            Some(
                Tensor::from_array(([1_usize], vec![mask_val].into_boxed_slice())).map_err(
                    |e| PiperError::Inference(format!("speaker_embedding_mask tensor: {e}")),
                )?,
            )
        } else {
            None
        };

        // ValueMap を構築
        let mut inputs: Vec<(Cow<str>, ort::session::SessionInputValue<'_>)> =
            Vec::with_capacity(8);

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
        if let Some(ref t) = speaker_emb_tensor {
            inputs.push(("speaker_embedding".into(), t.into()));
        }
        if let Some(ref t) = speaker_emb_mask_tensor {
            inputs.push(("speaker_embedding_mask".into(), t.into()));
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
        let audio_i16_raw = audio_float_to_int16(audio_slice);

        // --- duration テンソル抽出 (post-trim より前) ---
        // padded sequence の durations を保持して `trim_padding_by_durations`
        // から正確に padding 範囲を切り出すために必要。
        // 呼び出し側へ返す `durations` は後で original 長に切り詰める。
        let padded_durations: Option<Vec<f32>> = if self.capabilities.has_duration_output {
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

        // --- Strategy A (post-trim): padding 由来の音声を除去 ---
        // durations が利用可能なら精密 trim、なければ RMS フォールバック。
        let audio_i16 = if was_padded {
            let trimmed = if let Some(durs) = padded_durations.as_deref() {
                trim_padding_by_durations(
                    &audio_i16_raw,
                    durs,
                    front_pad,
                    back_pad,
                    self.hop_size,
                    TRIM_EOS_MAX_FRAMES,
                )
            } else {
                trim_silence(&audio_i16_raw)
            };
            tracing::debug!(
                "Short text trim: {} -> {} samples",
                audio_i16_raw.len(),
                trimmed.len()
            );
            trimmed
        } else {
            audio_i16_raw
        };
        let audio_seconds = audio_i16.len() as f64 / self.sample_rate as f64;

        // 呼び出し側に返す durations は original 長に切り詰める
        // (timing 用途では padded extras は not user-visible)。
        let durations = padded_durations.map(|mut d| {
            if was_padded && d.len() > original_len {
                d.truncate(original_len);
            }
            d
        });

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
            has_speaker_embedding: false,
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
            speaker_embedding: None,
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
            has_speaker_embedding: true,
        };
        assert!(caps.has_sid);
        assert!(caps.has_lid);
        assert!(caps.has_prosody);
        assert!(caps.has_duration_output);
        assert!(caps.has_speaker_embedding);
    }

    #[test]
    fn test_model_capabilities_all_false() {
        let caps = ModelCapabilities {
            has_sid: false,
            has_lid: false,
            has_prosody: false,
            has_duration_output: false,
            has_speaker_embedding: false,
        };
        assert!(!caps.has_sid);
        assert!(!caps.has_lid);
        assert!(!caps.has_prosody);
        assert!(!caps.has_duration_output);
        assert!(!caps.has_speaker_embedding);
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
        // DeviceType::Cuda { device_id: 0 } displays as "cuda:0", remove ':'
        let device_label = "cuda:0".replace(':', "");
        let opt_path = build_cache_path(&model_path, &device_label);
        assert_eq!(
            opt_path.to_str().unwrap(),
            "/data/models/test.cuda0.opt.onnx"
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
    fn test_device_label_colon_removal() {
        // DeviceType display produces "cuda:0", we remove ':' (C#/Python unified)
        let label = "cuda:0".replace(':', "");
        assert_eq!(label, "cuda0");
        assert!(!label.contains(':'));
        assert!(!label.contains('.'));
    }

    // -----------------------------------------------------------------------
    // SessionBuilder 設定テスト (memory_pattern, dynamic_block_base)
    // -----------------------------------------------------------------------

    #[test]
    fn test_session_builder_with_all_options() {
        // SessionBuilder に parallel_execution(false), memory_pattern(true),
        // dynamic_block_base(4) を設定してエラーが発生しないことを検証する。
        let builder = Session::builder()
            .expect("session builder")
            .with_intra_threads(1)
            .expect("intra_threads")
            .with_inter_threads(1)
            .expect("inter_threads")
            .with_parallel_execution(false)
            .expect("parallel_execution")
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
        let label = "directml:1".replace(':', "");
        assert_eq!(label, "directml1");
        let model_path = PathBuf::from("/data/models/test.onnx");
        let opt_path = build_cache_path(&model_path, &label);
        assert_eq!(
            opt_path.to_str().unwrap(),
            "/data/models/test.directml1.opt.onnx"
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

    // -----------------------------------------------------------------------
    // Strategy A: Silence Padding テスト
    // -----------------------------------------------------------------------

    #[test]
    fn test_pad_short_phonemes_below_threshold() {
        // 10 tokens -> should be padded to MIN_PHONEME_IDS
        let ids: Vec<i64> = vec![1, 5, 6, 7, 8, 9, 10, 11, 12, 2]; // BOS=1, EOS=2
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(was_padded);
        assert_eq!(padded.len(), MIN_PHONEME_IDS);
        assert_eq!(padded[0], 1); // BOS preserved
        assert_eq!(padded[padded.len() - 1], 2); // EOS preserved
    }

    #[test]
    fn test_pad_short_phonemes_at_threshold() {
        // Exactly MIN_PHONEME_IDS -> no padding
        let ids: Vec<i64> = (0..MIN_PHONEME_IDS as i64).collect();
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(!was_padded);
        assert_eq!(padded.len(), MIN_PHONEME_IDS);
        assert_eq!(padded, ids);
    }

    #[test]
    fn test_pad_short_phonemes_above_threshold() {
        // Above MIN_PHONEME_IDS -> no padding
        let ids: Vec<i64> = (0..(MIN_PHONEME_IDS as i64 + 10)).collect();
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(!was_padded);
        assert_eq!(padded.len(), MIN_PHONEME_IDS + 10);
    }

    #[test]
    fn test_pad_short_phonemes_pause_tokens() {
        // Verify that inserted tokens are PAUSE_TOKEN_ID (0).
        // body must be >= MIN_BODY_FOR_STRATEGY_A for Strategy A to apply.
        let mut ids: Vec<i64> = vec![1]; // BOS
        ids.extend((0..MIN_BODY_FOR_STRATEGY_A as i64).map(|i| 100 + i));
        ids.push(2); // EOS
        let total = ids.len();
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(was_padded);
        // All inserted tokens should be 0
        let inserted: Vec<i64> = padded
            .iter()
            .copied()
            .filter(|&id| id == PAUSE_TOKEN_ID)
            .collect();
        assert_eq!(inserted.len(), MIN_PHONEME_IDS - total);
    }

    #[test]
    fn test_pad_short_phonemes_body_preserved() {
        // Original body tokens should be preserved in order
        let ids: Vec<i64> = vec![1, 10, 20, 30, 2]; // BOS=1, body=[10,20,30], EOS=2
        let (padded, _, _, _, _) = pad_short_phonemes(&ids, None);

        // Extract non-pause, non-BOS, non-EOS tokens
        let body: Vec<i64> = padded
            .iter()
            .copied()
            .filter(|&id| id != PAUSE_TOKEN_ID && id != 1 && id != 2)
            .collect();
        assert_eq!(body, vec![10, 20, 30]);
    }

    #[test]
    fn test_pad_short_phonemes_with_prosody() {
        // body == MIN_BODY_FOR_STRATEGY_A so Strategy A applies.
        let mut ids: Vec<i64> = vec![1];
        ids.extend((0..MIN_BODY_FOR_STRATEGY_A as i64).map(|i| 5 + i));
        ids.push(2);
        let mut prosody = vec![[0, 0, 0]];
        prosody.extend((0..MIN_BODY_FOR_STRATEGY_A as i32).map(|i| [i + 1, i + 2, i + 3]));
        prosody.push([0, 0, 0]);

        let (padded_ids, padded_prosody, was_padded, _, _) =
            pad_short_phonemes(&ids, Some(&prosody));
        assert!(was_padded);
        assert_eq!(padded_ids.len(), MIN_PHONEME_IDS);
        let pp = padded_prosody.unwrap();
        assert_eq!(pp.len(), MIN_PHONEME_IDS);
        // BOS prosody preserved
        assert_eq!(pp[0], [0, 0, 0]);
        // EOS prosody preserved
        assert_eq!(pp[pp.len() - 1], [0, 0, 0]);
    }

    #[test]
    fn test_pad_short_phonemes_prosody_none() {
        // body == MIN_BODY_FOR_STRATEGY_A.
        let mut ids: Vec<i64> = vec![1];
        ids.extend((0..MIN_BODY_FOR_STRATEGY_A as i64).map(|i| 5 + i));
        ids.push(2);
        let (padded, padded_prosody, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(was_padded);
        assert_eq!(padded.len(), MIN_PHONEME_IDS);
        assert!(padded_prosody.is_none());
    }

    #[test]
    fn test_pad_short_phonemes_skips_when_body_too_short() {
        // body=0 (just BOS+EOS): Strategy A skipped (issue #356).
        let ids: Vec<i64> = vec![1, 2];
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(!was_padded);
        assert_eq!(padded, ids);

        // body=1 (e.g. just one phoneme between BOS/EOS).
        let ids: Vec<i64> = vec![1, 10, 2];
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(!was_padded);
        assert_eq!(padded, ids);

        // body=2 ("あ。" case).
        if MIN_BODY_FOR_STRATEGY_A > 2 {
            let ids: Vec<i64> = vec![1, 10, 11, 2];
            let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
            assert!(!was_padded);
            assert_eq!(padded, ids);
        }
    }

    #[test]
    fn test_pad_short_phonemes_single_element() {
        // Edge case: single element — body would be < 0 (saturating to 0)
        // so Strategy A is skipped.
        let ids: Vec<i64> = vec![1];
        let (padded, _, was_padded, _, _) = pad_short_phonemes(&ids, None);
        assert!(!was_padded);
        assert_eq!(padded, ids);
    }

    // -----------------------------------------------------------------------
    // Strategy A: Trim Silence テスト
    // -----------------------------------------------------------------------

    #[test]
    fn test_trim_silence_removes_leading_silence() {
        // 1000 samples of silence + 5000 samples of signal
        let mut audio = vec![0i16; 1000];
        audio.extend(vec![10000i16; 5000]);
        let trimmed = trim_silence(&audio);
        assert!(trimmed.len() < audio.len());
        // Trimmed result should contain the signal
        assert!(trimmed.contains(&10000));
    }

    #[test]
    fn test_trim_silence_removes_trailing_silence() {
        // 5000 samples of signal + 1000 samples of silence
        let mut audio = vec![10000i16; 5000];
        audio.extend(vec![0i16; 1000]);
        let trimmed = trim_silence(&audio);
        assert!(trimmed.len() < audio.len());
    }

    #[test]
    fn test_trim_silence_preserves_minimum() {
        // Very short audio should be preserved
        let audio = vec![0i16; 100];
        let trimmed = trim_silence(&audio);
        assert_eq!(trimmed.len(), audio.len()); // Below TRIM_MIN_SAMPLES
    }

    #[test]
    fn test_trim_silence_all_silence() {
        // All silence but longer than TRIM_MIN_SAMPLES -> trims to minimum
        let audio = vec![0i16; 10000];
        let trimmed = trim_silence(&audio);
        assert!(trimmed.len() >= TRIM_MIN_SAMPLES);
    }

    #[test]
    fn test_trim_silence_no_silence() {
        // Constant non-zero signal -> should preserve most of it.
        // Window-based detection may round to window boundaries,
        // so allow up to TRIM_WINDOW_SIZE difference.
        let audio: Vec<i16> = (0..5000).map(|i| ((i % 1000) as i16) + 1000).collect();
        let trimmed = trim_silence(&audio);
        assert!(
            trimmed.len() >= audio.len() - TRIM_WINDOW_SIZE,
            "trimmed {} from {} (max allowed loss: {})",
            audio.len() - trimmed.len(),
            audio.len(),
            TRIM_WINDOW_SIZE,
        );
    }

    // -----------------------------------------------------------------------
    // Strategy B: Dynamic Scales Adjustment テスト
    // -----------------------------------------------------------------------

    #[test]
    fn test_adjust_scales_above_threshold() {
        let (ns, nw) = adjust_scales_for_short_text(MIN_PHONEME_IDS, 0.667, 0.8);
        assert!((ns - 0.667).abs() < 1e-6);
        assert!((nw - 0.8).abs() < 1e-6);
    }

    #[test]
    fn test_adjust_scales_below_threshold() {
        // 50% of MIN_PHONEME_IDS — exactly at the noise_scale floor (0.5).
        let len = MIN_PHONEME_IDS / 2;
        let (ns, nw) = adjust_scales_for_short_text(len, 0.667, 0.8);
        let ratio = len as f32 / MIN_PHONEME_IDS as f32;
        let ns_ratio = ratio.max(0.5);
        let nw_ratio = ratio.max(0.4);
        assert!((ns - 0.667 * ns_ratio).abs() < 1e-4);
        assert!((nw - 0.8 * nw_ratio).abs() < 1e-4);
    }

    #[test]
    fn test_adjust_scales_very_short() {
        // 1 phoneme — far below both floors so they fully clamp.
        let len = 1;
        let (ns, nw) = adjust_scales_for_short_text(len, 0.667, 0.8);
        // ratio is below both floors (0.5 / 0.4)
        assert!((ns - 0.667 * 0.5).abs() < 1e-4);
        assert!((nw - 0.8 * 0.4).abs() < 1e-4);
    }

    #[test]
    fn test_adjust_scales_zero_length() {
        let (ns, nw) = adjust_scales_for_short_text(0, 0.667, 0.8);
        // ratio = 0.0, clamped at max(0.0, 0.5) = 0.5 for ns
        assert!((ns - 0.667 * 0.5).abs() < 1e-4);
        // ratio = 0.0, clamped at max(0.0, 0.4) = 0.4 for nw
        assert!((nw - 0.8 * 0.4).abs() < 1e-4);
    }

    #[test]
    fn test_adjust_scales_boundary_ratio() {
        // Just below the threshold so neither floor engages.
        let len = MIN_PHONEME_IDS - 1;
        let ratio = len as f32 / MIN_PHONEME_IDS as f32;
        let (ns, nw) = adjust_scales_for_short_text(len, 1.0, 1.0);
        // ratio is above both floors so both expectations equal `ratio`.
        assert!((ns - ratio).abs() < 1e-4);
        assert!((nw - ratio).abs() < 1e-4);
    }

    #[test]
    fn test_min_phoneme_ids_value() {
        assert_eq!(MIN_PHONEME_IDS, 15);
    }

    #[test]
    fn test_min_body_for_strategy_a_value() {
        assert_eq!(MIN_BODY_FOR_STRATEGY_A, 3);
    }

    #[test]
    fn test_trim_eos_max_frames_value() {
        assert_eq!(TRIM_EOS_MAX_FRAMES, 0);
    }

    // -----------------------------------------------------------------------
    // Strategy A: trim_padding_by_durations (precise post-trim, issue #356)
    // -----------------------------------------------------------------------
    // Mirrors src/python_run/tests/test_short_text_mitigation.py and ensures
    // every runtime trims by the same number of samples for the same inputs.

    #[test]
    fn test_trim_padding_by_durations_no_op_when_no_padding() {
        let audio: Vec<i16> = (0..1000).map(|i| i as i16).collect();
        let durations = vec![1.0_f32; 5];
        let result = trim_padding_by_durations(&audio, &durations, 0, 0, 256, TRIM_EOS_MAX_FRAMES);
        assert_eq!(result.len(), audio.len());
    }

    #[test]
    fn test_trim_padding_by_durations_trims_front_padding_only() {
        // Layout: BOS=2, pad×3 (3+3+3), body=4, EOS=1 → 19 frames total.
        let durations: Vec<f32> = vec![2.0, 3.0, 3.0, 3.0, 4.0, 1.0];
        let hop = 100u32;
        let total = 1900usize;
        let audio = vec![0i16; total];
        let result = trim_padding_by_durations(&audio, &durations, 3, 0, hop, 6);
        // BOS + front padding samples = (2+3+3+3) * 100 = 1100
        assert_eq!(result.len(), total - 1100);
    }

    #[test]
    fn test_trim_padding_by_durations_default_strips_eos_completely() {
        let durations: Vec<f32> = vec![2.0, 5.0, 5.0, 4.0, 4.0, 5.0, 5.0, 8.0];
        let hop = 100u32;
        let total = 3800usize;
        let audio = vec![0i16; total];
        let result = trim_padding_by_durations(&audio, &durations, 2, 2, hop, TRIM_EOS_MAX_FRAMES);
        // BOS + front padding = (2+5+5)*100 = 1200
        // back padding + entire EOS = (5+5+8)*100 = 1800
        assert_eq!(result.len(), total - 1200 - 1800);
    }

    #[test]
    fn test_trim_padding_by_durations_clamps_inflated_eos() {
        let durations: Vec<f32> = vec![2.0, 3.0, 3.0, 4.0, 3.0, 3.0, 10.0];
        let hop = 100u32;
        let total = 2800usize;
        let audio = vec![0i16; total];
        let result = trim_padding_by_durations(&audio, &durations, 2, 2, hop, 6);
        // BOS + front padding = (2+3+3) * 100 = 800
        // back padding + EOS excess = (3+3 + (10-6)) * 100 = 1000
        assert_eq!(result.len(), total - 800 - 1000);
    }

    #[test]
    fn test_trim_padding_by_durations_returns_input_when_durations_empty() {
        let audio = vec![0i16; 1000];
        let durations: Vec<f32> = vec![];
        let result = trim_padding_by_durations(&audio, &durations, 3, 3, 256, TRIM_EOS_MAX_FRAMES);
        assert_eq!(result.len(), audio.len());
    }

    #[test]
    fn test_trim_padding_by_durations_returns_input_when_durations_too_short() {
        let audio = vec![0i16; 1000];
        let durations: Vec<f32> = vec![1.0, 1.0, 1.0];
        let result = trim_padding_by_durations(&audio, &durations, 5, 5, 256, TRIM_EOS_MAX_FRAMES);
        assert_eq!(result.len(), audio.len());
    }

    #[test]
    fn test_trim_padding_by_durations_returns_input_when_hop_size_zero() {
        let audio = vec![0i16; 1000];
        let durations: Vec<f32> = vec![1.0; 8];
        let result = trim_padding_by_durations(&audio, &durations, 2, 2, 0, TRIM_EOS_MAX_FRAMES);
        assert_eq!(result.len(), audio.len());
    }

    #[test]
    fn test_trim_padding_by_durations_truncation_matches_int_cast() {
        // Layout (front_pad=1, back_pad=1, body=3):
        //   [BOS=0.701, pad=0.701, body=2, body=2, body=2, pad=0.703, EOS=0.701]
        // Front trim = ((0.701+0.701)*100) as i64 = 140
        // Back trim  = (0.703*100) as i64 + (0.701*100) as i64 = 70 + 70 = 140
        // round() would diverge → cross-runtime drift.
        let durations: Vec<f32> = vec![0.701, 0.701, 2.0, 2.0, 2.0, 0.703, 0.701];
        let hop = 100u32;
        let sum: f32 = durations.iter().sum();
        let total = (sum * hop as f32) as usize;
        let audio = vec![0i16; total];
        let result = trim_padding_by_durations(&audio, &durations, 1, 1, hop, TRIM_EOS_MAX_FRAMES);
        assert_eq!(result.len(), total - 140 - 140);
    }
}
