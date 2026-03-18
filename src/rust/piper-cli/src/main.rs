use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

use piper_core::{
    OnnxEngine, VoiceConfig,
    audio, config,
    input::JsonlReader,
};

#[derive(Parser, Debug)]
#[command(name = "piper", version, about = "Piper-Plus TTS inference")]
struct Cli {
    /// ONNX モデルファイルパス
    #[arg(short, long)]
    model: PathBuf,

    /// config.json パス (省略時は自動検出)
    #[arg(short, long)]
    config: Option<PathBuf>,

    /// WAV 出力ディレクトリ
    #[arg(short = 'd', long)]
    output_dir: Option<PathBuf>,

    /// WAV 出力ファイル (- で stdout)
    #[arg(short = 'f', long)]
    output_file: Option<String>,

    /// 話者 ID (デフォルト: 0)
    #[arg(short, long)]
    speaker: Option<i64>,

    /// 生成ノイズスケール
    #[arg(long, default_value_t = 0.667)]
    noise_scale: f32,

    /// 音素長さスケール
    #[arg(long, default_value_t = 1.0)]
    length_scale: f32,

    /// 音素幅ノイズ
    #[arg(long, default_value_t = 0.8)]
    noise_w: f32,

    /// 実行デバイス
    #[arg(long, default_value = "auto")]
    device: String,

    /// デバッグログ出力
    #[arg(long)]
    debug: bool,
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    // ログ初期化
    let env_filter = if cli.debug { "debug" } else { "info" };
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new(env_filter)),
        )
        .with_writer(std::io::stderr)
        .init();

    // config.json 検出
    let config_path = config::VoiceConfig::resolve_config_path(
        &cli.model,
        cli.config.as_deref(),
    ).context("config.json not found")?;

    tracing::info!("Config: {}", config_path.display());

    // 設定読み込み
    let voice_config = VoiceConfig::load(&config_path)
        .context("Failed to load config.json")?;

    tracing::info!(
        "Model: speakers={}, languages={}, type={:?}",
        voice_config.num_speakers,
        voice_config.num_languages,
        voice_config.phoneme_type,
    );

    // ONNX エンジン初期化
    let mut engine = OnnxEngine::load(&cli.model, &voice_config, &cli.device)
        .context("Failed to load ONNX model")?;

    // 出力ディレクトリ作成
    if let Some(ref dir) = cli.output_dir {
        std::fs::create_dir_all(dir)
            .with_context(|| format!("Failed to create output dir: {}", dir.display()))?;
    }

    // stdout 出力モード判定
    let output_to_stdout = cli.output_file.as_deref() == Some("-");

    // JSONL 入力処理
    let stdin = std::io::stdin();
    let reader = JsonlReader::new(stdin.lock());
    let mut utt_count = 0u64;

    for result in reader {
        let utterance = result.context("Failed to parse JSONL line")?;
        utt_count += 1;

        // SynthesisRequest 構築
        let mut request = utterance.to_request(
            cli.noise_scale,
            cli.length_scale,
            cli.noise_w,
        );

        // CLI の speaker_id でオーバーライド
        if let Some(sid) = cli.speaker {
            request.speaker_id = Some(sid);
        }

        // 推論実行
        let synthesis = engine.synthesize(&request)
            .with_context(|| format!("Inference failed for utterance {}", utt_count))?;

        tracing::info!(
            "Utterance {}: {:.3}s audio, {:.3}s infer, RTF={:.3}",
            utt_count,
            synthesis.audio_seconds,
            synthesis.infer_seconds,
            synthesis.real_time_factor(),
        );

        // 出力
        if output_to_stdout {
            audio::write_wav_to_stdout(synthesis.sample_rate, &synthesis.audio)
                .context("Failed to write WAV to stdout")?;
        } else if let Some(ref dir) = cli.output_dir {
            let filename = utterance
                .output_file
                .unwrap_or_else(|| format!("{}.wav", utt_count));
            let output_path = dir.join(&filename);
            audio::write_wav(&output_path, synthesis.sample_rate, &synthesis.audio)
                .with_context(|| format!("Failed to write {}", output_path.display()))?;
            tracing::info!("Wrote: {}", output_path.display());
        } else if let Some(ref file) = cli.output_file {
            let output_path = PathBuf::from(file);
            audio::write_wav(&output_path, synthesis.sample_rate, &synthesis.audio)
                .with_context(|| format!("Failed to write {}", output_path.display()))?;
            tracing::info!("Wrote: {}", output_path.display());
        }
    }

    if utt_count == 0 {
        tracing::warn!("No input received from stdin. Pipe JSONL data or use --text (Phase 2).");
    } else {
        tracing::info!("Processed {} utterances", utt_count);
    }

    Ok(())
}
