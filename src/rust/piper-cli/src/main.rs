use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

use piper_plus::phonemize::custom_dict::CustomDictionary;
use piper_plus::{OnnxEngine, PiperVoice, VoiceConfig, audio, config, input::JsonlReader};

/// サポートされている言語コード
const SUPPORTED_LANGUAGES: &[&str] = &["ja", "en", "zh", "ko", "es", "fr", "pt"];

#[derive(Parser, Debug)]
#[command(name = "piper", version, about = "Piper-Plus TTS inference")]
struct Cli {
    /// ONNX モデルファイルパス (--list-devices/--list-models 以外では必須)
    #[arg(short, long)]
    model: Option<PathBuf>,

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

    /// テキスト直接入力 (JSONL stdin をバイパス)
    #[arg(short, long)]
    text: Option<String>,

    /// 音素化の言語を指定 [ja, en, zh, ko, es, fr, pt] (デフォルト: 自動検出)
    #[arg(short, long)]
    language: Option<String>,

    /// カスタム辞書パス (複数指定可)
    #[arg(long = "custom-dict")]
    custom_dicts: Vec<PathBuf>,

    /// ストリーミング合成 (センテンス単位で逐次出力)
    #[arg(long)]
    stream: bool,

    /// 音素タイミング出力 (json, tsv, srt)
    #[arg(long, value_name = "FORMAT")]
    timing: Option<String>,

    /// 利用可能なデバイスを一覧表示
    #[arg(long)]
    list_devices: bool,

    /// 利用可能なモデルを一覧表示
    #[arg(long)]
    list_models: bool,

    /// モデルをダウンロード (名前指定)
    #[arg(long, value_name = "NAME")]
    download_model: Option<String>,

    /// モデルディレクトリ (ダウンロード先)
    #[arg(long, value_name = "DIR")]
    model_dir: Option<PathBuf>,

    /// バッチ処理: テキストファイルから読み込み (1行1発話)
    #[arg(long, value_name = "FILE")]
    batch: Option<PathBuf>,
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

    // --list-devices: デバイス一覧表示 (モデル不要)
    if cli.list_devices {
        let devices = piper_plus::device::enumerate_devices();
        println!("Available devices:");
        for dev in devices {
            println!("  {}", dev);
        }
        return Ok(());
    }

    // --list-models: モデル一覧表示 (モデル不要)
    if cli.list_models {
        let models = piper_plus::model_download::builtin_registry();
        println!("Available models:");
        for model in models {
            println!(
                "  {} ({}) - {}",
                model.name, model.language, model.description
            );
        }
        return Ok(());
    }

    // --download-model: モデルダウンロード (モデル不要)
    if let Some(ref model_name) = cli.download_model {
        let registry = piper_plus::model_download::builtin_registry();
        let model_info = registry
            .iter()
            .find(|m| m.name == *model_name)
            .ok_or_else(|| {
                anyhow::anyhow!(
                    "Model '{}' not found. Use --list-models to see available models.",
                    model_name
                )
            })?;

        let dest_dir = cli
            .model_dir
            .clone()
            .unwrap_or_else(piper_plus::model_download::default_model_dir);

        eprintln!(
            "Downloading model: {} to {}",
            model_name,
            dest_dir.display()
        );

        let (model_path, config_path) = piper_plus::model_download::download_model(
            model_info,
            &dest_dir,
            Some(Box::new(|progress| {
                if let Some(pct) = progress.percentage {
                    eprint!("\r  Downloading... {:.1}%", pct);
                } else {
                    eprint!("\r  Downloading... {} KB", progress.bytes_downloaded / 1024);
                }
            })),
        )
        .context("Failed to download model")?;

        eprintln!();
        eprintln!("Model saved to: {}", model_path.display());
        eprintln!("Config saved to: {}", config_path.display());
        return Ok(());
    }

    // --text と --batch の排他チェック
    if cli.text.is_some() && cli.batch.is_some() {
        anyhow::bail!("--text and --batch are mutually exclusive");
    }

    // --model は standalone コマンド以外では必須
    let model_path = cli.model.as_ref().ok_or_else(|| {
        anyhow::anyhow!("--model is required for synthesis (only --list-devices, --list-models, and --download-model work without it)")
    })?;

    // config.json 検出
    let config_path = config::VoiceConfig::resolve_config_path(model_path, cli.config.as_deref())
        .context("config.json not found")?;

    tracing::info!("Config: {}", config_path.display());

    // 設定読み込み
    let voice_config = VoiceConfig::load(&config_path).context("Failed to load config.json")?;

    tracing::info!(
        "Model: speakers={}, languages={}, type={:?}",
        voice_config.num_speakers,
        voice_config.num_languages,
        voice_config.phoneme_type,
    );

    // 出力ディレクトリ作成
    if let Some(ref dir) = cli.output_dir {
        std::fs::create_dir_all(dir)
            .with_context(|| format!("Failed to create output dir: {}", dir.display()))?;
    }

    // stdout 出力モード判定
    let output_to_stdout = cli.output_file.as_deref() == Some("-");

    // --language バリデーション
    if let Some(ref lang) = cli.language
        && !SUPPORTED_LANGUAGES.contains(&lang.as_str())
    {
        anyhow::bail!(
            "Unsupported language: '{}'. Supported languages: {}",
            lang,
            SUPPORTED_LANGUAGES.join(", "),
        );
    }

    if let Some(ref batch_path) = cli.batch {
        // --batch モード: テキストファイルから1行ずつ読み込み合成
        let mut voice = PiperVoice::load(model_path, cli.config.as_deref(), &cli.device)
            .context("Failed to initialize PiperVoice")?;

        // Load custom dictionaries
        let custom_dict = if !cli.custom_dicts.is_empty() {
            let mut dict = CustomDictionary::new();
            for path in &cli.custom_dicts {
                match dict.load_dictionary(path) {
                    Ok(()) => tracing::info!("Loaded custom dictionary: {}", path.display()),
                    Err(e) => {
                        tracing::error!(
                            "Failed to load custom dictionary {}: {}",
                            path.display(),
                            e
                        )
                    }
                }
            }
            Some(dict)
        } else {
            None
        };

        let content = std::fs::read_to_string(batch_path)
            .with_context(|| format!("Failed to read batch file: {}", batch_path.display()))?;

        let lines: Vec<&str> = content.lines().filter(|l| !l.trim().is_empty()).collect();
        if lines.is_empty() {
            anyhow::bail!("Batch file is empty: {}", batch_path.display());
        }

        let output_dir = cli
            .output_dir
            .as_ref()
            .ok_or_else(|| anyhow::anyhow!("--output-dir is required for --batch mode"))?;

        tracing::info!(
            "Batch mode: {} lines from {}",
            lines.len(),
            batch_path.display()
        );

        for (i, line) in lines.iter().enumerate() {
            let idx = i + 1;
            let text_to_synth = if let Some(ref dict) = custom_dict {
                let modified = dict.apply_to_text(line);
                if modified != *line {
                    tracing::debug!("Custom dict: \"{}\" -> \"{}\"", line, modified);
                }
                modified
            } else {
                line.to_string()
            };
            let result = voice
                .synthesize_text(
                    &text_to_synth,
                    cli.speaker,
                    cli.language.as_deref(),
                    cli.noise_scale,
                    cli.length_scale,
                    cli.noise_w,
                )
                .with_context(|| format!("Synthesis failed for line {}", idx))?;

            let filename = format!("{:04}.wav", idx);
            let path = output_dir.join(&filename);
            audio::write_wav(&path, result.sample_rate, &result.audio)
                .with_context(|| format!("Failed to write {}", path.display()))?;

            tracing::info!(
                "Batch [{}/{}]: {:.3}s audio, {:.3}s infer, RTF={:.3} -> {}",
                idx,
                lines.len(),
                result.audio_seconds,
                result.infer_seconds,
                result.real_time_factor(),
                path.display(),
            );
        }

        tracing::info!("Batch complete: {} files written", lines.len());
    } else if let Some(text) = &cli.text {
        // --text モード: PiperVoice でテキストから直接音声合成
        let mut voice = PiperVoice::load(model_path, cli.config.as_deref(), &cli.device)
            .context("Failed to initialize PiperVoice")?;

        // Load custom dictionaries
        let custom_dict = if !cli.custom_dicts.is_empty() {
            let mut dict = CustomDictionary::new();
            for path in &cli.custom_dicts {
                match dict.load_dictionary(path) {
                    Ok(()) => tracing::info!("Loaded custom dictionary: {}", path.display()),
                    Err(e) => {
                        tracing::error!(
                            "Failed to load custom dictionary {}: {}",
                            path.display(),
                            e
                        )
                    }
                }
            }
            Some(dict)
        } else {
            None
        };

        // 言語ログ出力
        if let Some(ref lang) = cli.language {
            // 多言語モデルの場合: 指定言語が language_id_map に存在するか確認
            if voice_config.is_multilingual() {
                if let Some(&lid) = voice_config.language_id_map.get(lang.as_str()) {
                    tracing::info!("Language override: {} (lid={})", lang, lid);
                } else {
                    let available: Vec<&str> = voice_config
                        .language_id_map
                        .keys()
                        .map(|s| s.as_str())
                        .collect();
                    anyhow::bail!(
                        "Language '{}' is not available in this model. Available: {}",
                        lang,
                        available.join(", "),
                    );
                }
            } else {
                tracing::info!(
                    "Language specified: {} (model is monolingual, language detection handled by phonemizer)",
                    lang
                );
            }
        } else {
            tracing::info!("Language: auto-detect (from phonemizer)");
        }

        if cli.stream {
            // --stream --text: センテンス単位で分割して逐次合成
            let sentences = piper_plus::streaming::split_sentences(text);
            if sentences.is_empty() {
                anyhow::bail!("No sentences found in input text");
            }

            tracing::info!("Streaming mode: {} sentence(s)", sentences.len());

            let output_dir = cli
                .output_dir
                .as_ref()
                .ok_or_else(|| anyhow::anyhow!("--output-dir is required for --stream mode"))?;

            for (i, sentence) in sentences.iter().enumerate() {
                let idx = i + 1;
                let text_to_synth = if let Some(ref dict) = custom_dict {
                    let modified = dict.apply_to_text(sentence);
                    if modified != *sentence {
                        tracing::debug!("Custom dict: \"{}\" -> \"{}\"", sentence, modified);
                    }
                    modified
                } else {
                    sentence.to_string()
                };
                let result = voice
                    .synthesize_text(
                        &text_to_synth,
                        cli.speaker,
                        cli.language.as_deref(),
                        cli.noise_scale,
                        cli.length_scale,
                        cli.noise_w,
                    )
                    .with_context(|| format!("Synthesis failed for sentence {}", idx))?;

                let filename = format!("chunk_{:04}.wav", idx);
                let path = output_dir.join(&filename);
                audio::write_wav(&path, result.sample_rate, &result.audio)
                    .with_context(|| format!("Failed to write {}", path.display()))?;

                tracing::info!(
                    "Stream chunk [{}/{}]: \"{}\", {:.3}s audio -> {}",
                    idx,
                    sentences.len(),
                    sentence,
                    result.audio_seconds,
                    path.display(),
                );
            }

            tracing::info!("Streaming complete: {} chunks written", sentences.len());
        } else {
            // 通常の --text モード (一括合成)
            let text_to_synth = if let Some(ref dict) = custom_dict {
                let modified = dict.apply_to_text(text);
                if modified != *text {
                    tracing::debug!("Custom dict: \"{}\" -> \"{}\"", text, modified);
                }
                modified
            } else {
                text.to_string()
            };
            let result = voice
                .synthesize_text(
                    &text_to_synth,
                    cli.speaker,
                    cli.language.as_deref(),
                    cli.noise_scale,
                    cli.length_scale,
                    cli.noise_w,
                )
                .context("Failed to synthesize text")?;

            tracing::info!(
                "Synthesized: {:.3}s audio, {:.3}s infer, RTF={:.3}",
                result.audio_seconds,
                result.infer_seconds,
                result.real_time_factor(),
            );

            // --timing: 音素タイミング出力
            if let Some(ref format) = cli.timing {
                if let Some(ref durations) = result.durations {
                    // phoneme_ids からトークン名を推定 (簡易版: ID をそのまま使用)
                    let tokens: Vec<String> =
                        (0..durations.len()).map(|i| format!("ph_{}", i)).collect();
                    match piper_plus::timing::durations_to_timing(
                        durations,
                        &tokens,
                        result.sample_rate,
                        piper_plus::timing::DEFAULT_HOP_LENGTH,
                    ) {
                        Ok(timing) => {
                            let output = match format.as_str() {
                                "json" => timing.to_json().unwrap_or_default(),
                                "tsv" => timing.to_tsv(),
                                "srt" => timing.to_srt(),
                                _ => {
                                    anyhow::bail!(
                                        "Unknown timing format: '{}'. Use json, tsv, or srt.",
                                        format
                                    );
                                }
                            };
                            eprintln!("{}", output);
                        }
                        Err(e) => tracing::warn!("Timing extraction failed: {}", e),
                    }
                } else {
                    tracing::warn!("Model does not output duration tensor; --timing ignored.");
                }
            }

            // 出力
            if output_to_stdout {
                audio::write_wav_to_stdout(result.sample_rate, &result.audio)
                    .context("Failed to write WAV to stdout")?;
            } else if let Some(ref dir) = cli.output_dir {
                let path = dir.join("output.wav");
                audio::write_wav(&path, result.sample_rate, &result.audio)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            } else if let Some(ref file) = cli.output_file {
                let path = PathBuf::from(file);
                audio::write_wav(&path, result.sample_rate, &result.audio)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            } else {
                // デフォルト: output.wav に出力
                let path = PathBuf::from("output.wav");
                audio::write_wav(&path, result.sample_rate, &result.audio)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            }
        }
    } else {
        // JSONL stdin パイプライン (既存)
        let mut engine = OnnxEngine::load(model_path, &voice_config, &cli.device)
            .context("Failed to load ONNX model")?;

        let stdin = std::io::stdin();
        let reader = JsonlReader::new(stdin.lock());
        let mut utt_count = 0u64;

        for result in reader {
            let utterance = result.context("Failed to parse JSONL line")?;
            utt_count += 1;

            // output_file を先に取り出す (to_request が self を消費するため)
            let output_file = utterance.output_file.clone();

            // SynthesisRequest 構築 (move semantics — clone を回避)
            let mut request = utterance.to_request(cli.noise_scale, cli.length_scale, cli.noise_w);

            // CLI の speaker_id でオーバーライド
            if let Some(sid) = cli.speaker {
                request.speaker_id = Some(sid);
            }

            // 推論実行
            let synthesis = engine
                .synthesize(&request)
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
                let filename = output_file.unwrap_or_else(|| format!("{}.wav", utt_count));
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
            tracing::warn!("No input received from stdin. Pipe JSONL data or use --text.");
        } else {
            tracing::info!("Processed {} utterances", utt_count);
        }
    }

    Ok(())
}
