use std::collections::HashMap;
use std::path::PathBuf;

use anyhow::{Context, Result};
use clap::Parser;

use piper_plus::phonemize::custom_dict::CustomDictionary;
use piper_plus::{
    OnnxEngine, PiperVoice, SynthesisParams, VoiceConfig, audio, config, input::JsonlReader,
};

/// サポートされている言語コード
const SUPPORTED_LANGUAGES: &[&str] = &["ja", "en", "zh", "ko", "es", "fr", "pt", "sv"];

#[derive(Parser, Debug)]
#[command(name = "piper", version, about = "Piper-Plus TTS inference")]
struct Cli {
    /// ONNX モデル (ファイルパス、モデル名、またはエイリアス)
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

    /// 利用可能なモデルを一覧表示 (言語フィルタ: --list-models ja)
    #[arg(long, value_name = "LANG", num_args = 0..=1, default_missing_value = "")]
    list_models: Option<String>,

    /// モデルをダウンロード (名前指定)
    #[arg(long, value_name = "NAME")]
    download_model: Option<String>,

    /// モデルディレクトリ (ダウンロード先)
    #[arg(long, value_name = "DIR")]
    model_dir: Option<PathBuf>,

    /// バッチ処理: テキストファイルから読み込み (1行1発話)
    #[arg(long, value_name = "FILE")]
    batch: Option<PathBuf>,

    /// 文間の無音時間 (秒、デフォルト: 0.2)
    #[arg(long, default_value_t = 0.2)]
    sentence_silence: f32,

    /// 特定音素の後に追加する無音 (例: "_ 0.5")
    #[arg(long, value_name = "PHONEME SECONDS")]
    phoneme_silence: Vec<String>,

    /// ログ出力を無効化
    #[arg(short, long)]
    quiet: bool,

    /// テストモード: ONNX推論をスキップし phoneme IDs のみ出力 (CI用)
    #[arg(long)]
    test_mode: bool,

    /// raw PCM int16 を stdout に出力 (WAVヘッダなし)
    #[arg(long)]
    output_raw: bool,

    /// ORT warmup を無効化 (デフォルト: 起動時にダミー推論2回で JIT キャッシュを温める)
    #[arg(long)]
    no_warmup: bool,

    /// Reference audio file for voice cloning (WAV format)
    #[arg(long, value_name = "PATH")]
    reference_audio: Option<PathBuf>,

    /// Pre-computed speaker embedding file (raw binary float32)
    #[arg(long, value_name = "PATH")]
    speaker_embedding: Option<PathBuf>,

    /// Speaker encoder ONNX model path (required for --reference-audio)
    #[arg(long, value_name = "PATH")]
    speaker_encoder_model: Option<PathBuf>,
}

/// --phoneme-silence の値をパースして HashMap に変換する。
/// 各エントリは "PHONEME SECONDS" 形式 (例: "_ 0.5")。
fn parse_phoneme_silence(values: &[String]) -> Result<HashMap<String, f32>> {
    let mut map = HashMap::new();
    for entry in values {
        let parts: Vec<&str> = entry.split_whitespace().collect();
        if parts.len() < 2 {
            anyhow::bail!(
                "Invalid --phoneme-silence format: '{}'. Expected 'PHONEME SECONDS' (e.g. '_ 0.5').",
                entry
            );
        }
        let phoneme = parts[0].to_string();
        let seconds: f32 = parts[1].parse().with_context(|| {
            format!(
                "Invalid seconds value '{}' in --phoneme-silence '{}'",
                parts[1], entry
            )
        })?;
        map.insert(phoneme, seconds);
    }
    Ok(map)
}

/// 音声データの末尾に無音サンプルを追加する。
fn append_silence(audio: &mut Vec<i16>, sample_rate: u32, silence_seconds: f32) {
    if silence_seconds > 0.0 {
        let num_samples = (sample_rate as f32 * silence_seconds) as usize;
        audio.extend(std::iter::repeat_n(0i16, num_samples));
    }
}

/// CLI引数から SynthesisParams を構築する。
fn build_synthesis_params(cli: &Cli, speaker_emb: Option<Vec<f32>>) -> SynthesisParams {
    SynthesisParams {
        speaker_id: cli.speaker,
        language_override: cli.language.clone(),
        noise_scale: cli.noise_scale,
        length_scale: cli.length_scale,
        noise_w: cli.noise_w,
        speaker_embedding: speaker_emb,
    }
}

/// Load speaker embedding from a binary file (raw float32 values, little-endian).
fn load_speaker_embedding(path: &std::path::Path) -> Result<Vec<f32>> {
    let data = std::fs::read(path)
        .with_context(|| format!("Failed to read speaker embedding: {}", path.display()))?;
    if data.len() % 4 != 0 {
        anyhow::bail!(
            "Speaker embedding file size ({} bytes) is not a multiple of 4 (float32)",
            data.len()
        );
    }
    let floats: Vec<f32> = data
        .chunks_exact(4)
        .map(|chunk| f32::from_le_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]))
        .collect();
    tracing::info!(
        "Loaded speaker embedding: {} dimensions from {}",
        floats.len(),
        path.display()
    );
    Ok(floats)
}

fn main() -> Result<()> {
    let cli = Cli::parse();

    // Apply environment variable defaults
    let model_arg = cli
        .model
        .clone()
        .or_else(|| std::env::var("PIPER_DEFAULT_MODEL").ok().map(PathBuf::from));

    let config_arg = cli.config.clone().or_else(|| {
        std::env::var("PIPER_DEFAULT_CONFIG")
            .ok()
            .map(PathBuf::from)
    });

    let model_dir_arg = cli
        .model_dir
        .clone()
        .or_else(|| std::env::var("PIPER_MODEL_DIR").ok().map(PathBuf::from));

    // ログ初期化
    let env_filter = if cli.quiet {
        "off"
    } else if cli.debug {
        "debug"
    } else {
        "info"
    };
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
    if let Some(ref lang_filter) = cli.list_models {
        let models = piper_plus::model_download::builtin_registry();
        println!("Available models:");
        for model in models {
            if !lang_filter.is_empty() && !model.language.contains(lang_filter.as_str()) {
                continue;
            }
            println!(
                "  {} ({}) - {}",
                model.name, model.language, model.description
            );
        }
        return Ok(());
    }

    // --download-model: モデルダウンロード (モデル不要)
    if let Some(ref model_name) = cli.download_model {
        let model_info = piper_plus::model_download::find_model(model_name).ok_or_else(|| {
            anyhow::anyhow!(
                "Model '{}' not found. Use --list-models to see available models.",
                model_name
            )
        })?;

        let dest_dir = model_dir_arg
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

    // --model は standalone コマンド以外では必須 (env: PIPER_DEFAULT_MODEL)
    // ファイルパス、モデル名、エイリアスのいずれかで指定可能
    let model_path = {
        let model_str = model_arg.as_ref().ok_or_else(|| {
            anyhow::anyhow!("--model is required for synthesis (or set PIPER_DEFAULT_MODEL env var). Only --list-devices, --list-models, and --download-model work without it.")
        })?;
        piper_plus::model_download::resolve_model_path(
            &model_str.to_string_lossy(),
            model_dir_arg.as_deref(),
        )
        .context("Failed to resolve model")?
    };

    // config.json 検出 (env: PIPER_DEFAULT_CONFIG)
    let config_path = config::VoiceConfig::resolve_config_path(&model_path, config_arg.as_deref())
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

    // --phoneme-silence パース
    let _phoneme_silence_map = parse_phoneme_silence(&cli.phoneme_silence)?;
    // TODO: phoneme_silence_map を音素境界で適用する (現在はパース・保持のみ)
    if !_phoneme_silence_map.is_empty() {
        tracing::info!(
            "Phoneme silence: {:?} (parsed but not yet applied to audio)",
            _phoneme_silence_map
        );
    }

    if cli.sentence_silence != 0.2 {
        tracing::info!("Sentence silence: {:.3}s", cli.sentence_silence);
    }

    // --- Voice cloning: resolve speaker embedding ---
    if cli.reference_audio.is_some() && cli.speaker_embedding.is_some() {
        anyhow::bail!("--reference-audio and --speaker-embedding are mutually exclusive");
    }
    if cli.reference_audio.is_some() && cli.speaker_encoder_model.is_none() {
        anyhow::bail!("--speaker-encoder-model is required when using --reference-audio");
    }

    let speaker_emb: Option<Vec<f32>> = if let Some(ref emb_path) = cli.speaker_embedding {
        Some(load_speaker_embedding(emb_path)?)
    } else if let Some(ref ref_audio) = cli.reference_audio {
        let enc_model = cli.speaker_encoder_model.as_ref().unwrap();
        tracing::info!("Loading speaker encoder: {}", enc_model.display());
        let mut encoder = piper_plus::speaker_encoder::SpeakerEncoder::new(enc_model)
            .context("Failed to load speaker encoder model")?;
        let emb = encoder
            .encode_file(ref_audio)
            .context("Failed to encode reference audio")?;
        tracing::info!(
            "Extracted speaker embedding: {} dimensions from {}",
            emb.len(),
            ref_audio.display()
        );
        Some(emb)
    } else {
        None
    };

    if let Some(ref batch_path) = cli.batch {
        // --batch モード: テキストファイルから1行ずつ読み込み合成
        let mut voice = PiperVoice::load(&model_path, config_arg.as_deref(), &cli.device)
            .context("Failed to initialize PiperVoice")?;

        // ORT warmup: JIT 最適化キャッシュを温める (失敗は非致命的)
        if !cli.no_warmup {
            tracing::info!("Warming up ORT session...");
            if let Err(e) = voice.warmup(piper_plus::DEFAULT_WARMUP_RUNS) {
                tracing::warn!("Warmup failed (non-fatal): {}", e);
            }
        }

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

        let params = build_synthesis_params(&cli, speaker_emb.clone());
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
                .synthesize_with_params(&text_to_synth, &params)
                .with_context(|| format!("Synthesis failed for line {}", idx))?;

            // --sentence-silence: 文末に無音を追加
            let sample_rate = result.sample_rate;
            let audio_seconds = result.audio_seconds;
            let infer_seconds = result.infer_seconds;
            let rtf = result.real_time_factor();
            let mut audio_data = result.audio;
            append_silence(&mut audio_data, sample_rate, cli.sentence_silence);

            let filename = format!("{:04}.wav", idx);
            let path = output_dir.join(&filename);
            audio::write_wav(&path, sample_rate, &audio_data)
                .with_context(|| format!("Failed to write {}", path.display()))?;

            tracing::info!(
                "Batch [{}/{}]: {:.3}s audio, {:.3}s infer, RTF={:.3} -> {}",
                idx,
                lines.len(),
                audio_seconds,
                infer_seconds,
                rtf,
                path.display(),
            );
        }

        tracing::info!("Batch complete: {} files written", lines.len());
    } else if let Some(text) = &cli.text {
        // --text モード: PiperVoice でテキストから直接音声合成
        let mut voice = PiperVoice::load(&model_path, config_arg.as_deref(), &cli.device)
            .context("Failed to initialize PiperVoice")?;

        // ORT warmup: JIT 最適化キャッシュを温める (失敗は非致命的)
        if !cli.no_warmup && !cli.test_mode {
            tracing::info!("Warming up ORT session...");
            if let Err(e) = voice.warmup(piper_plus::DEFAULT_WARMUP_RUNS) {
                tracing::warn!("Warmup failed (non-fatal): {}", e);
            }
        }

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

            let params = build_synthesis_params(&cli, speaker_emb.clone());
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
                    .synthesize_with_params(&text_to_synth, &params)
                    .with_context(|| format!("Synthesis failed for sentence {}", idx))?;

                // --sentence-silence: 文末に無音を追加
                let sample_rate = result.sample_rate;
                let audio_seconds = result.audio_seconds;
                let mut audio_data = result.audio;
                append_silence(&mut audio_data, sample_rate, cli.sentence_silence);

                let filename = format!("chunk_{:04}.wav", idx);
                let path = output_dir.join(&filename);
                audio::write_wav(&path, sample_rate, &audio_data)
                    .with_context(|| format!("Failed to write {}", path.display()))?;

                tracing::info!(
                    "Stream chunk [{}/{}]: \"{}\", {:.3}s audio -> {}",
                    idx,
                    sentences.len(),
                    sentence,
                    audio_seconds,
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

            // --test-mode: phoneme IDs のみ出力して終了 (ONNX 推論スキップ)
            if cli.test_mode {
                let ids = voice
                    .phonemize_to_ids(&text_to_synth)
                    .context("Failed to phonemize text")?;
                let json =
                    serde_json::to_string(&ids).context("Failed to serialize phoneme IDs")?;
                println!("{}", json);
                return Ok(());
            }

            let params = build_synthesis_params(&cli, speaker_emb.clone());
            let result = voice
                .synthesize_with_params(&text_to_synth, &params)
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

            // --sentence-silence: 文末に無音を追加
            let sample_rate = result.sample_rate;
            let mut audio_data = result.audio;
            append_silence(&mut audio_data, sample_rate, cli.sentence_silence);

            // 出力
            if cli.output_raw {
                audio::write_raw_to_stdout(&audio_data)
                    .context("Failed to write raw PCM to stdout")?;
            } else if output_to_stdout {
                audio::write_wav_to_stdout(sample_rate, &audio_data)
                    .context("Failed to write WAV to stdout")?;
            } else if let Some(ref dir) = cli.output_dir {
                let path = dir.join("output.wav");
                audio::write_wav(&path, sample_rate, &audio_data)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            } else if let Some(ref file) = cli.output_file {
                let path = PathBuf::from(file);
                audio::write_wav(&path, sample_rate, &audio_data)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            } else {
                // デフォルト: output.wav に出力
                let path = PathBuf::from("output.wav");
                audio::write_wav(&path, sample_rate, &audio_data)
                    .with_context(|| format!("Failed to write {}", path.display()))?;
                tracing::info!("Wrote: {}", path.display());
            }
        }
    } else {
        // JSONL stdin パイプライン (既存)
        let mut engine = OnnxEngine::load(&model_path, &voice_config, &cli.device)
            .context("Failed to load ONNX model")?;

        // ORT warmup: JIT 最適化キャッシュを温める (失敗は非致命的)
        if !cli.no_warmup {
            tracing::info!("Warming up ORT session...");
            if let Err(e) = engine.warmup(piper_plus::DEFAULT_WARMUP_RUNS) {
                tracing::warn!("Warmup failed (non-fatal): {}", e);
            }
        }

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

            // --sentence-silence: 文末に無音を追加
            let sample_rate = synthesis.sample_rate;
            let mut audio_data = synthesis.audio;
            append_silence(&mut audio_data, sample_rate, cli.sentence_silence);

            // 出力
            if output_to_stdout {
                audio::write_wav_to_stdout(sample_rate, &audio_data)
                    .context("Failed to write WAV to stdout")?;
            } else if let Some(ref dir) = cli.output_dir {
                let filename = output_file.unwrap_or_else(|| format!("{}.wav", utt_count));
                let output_path = dir.join(&filename);
                audio::write_wav(&output_path, sample_rate, &audio_data)
                    .with_context(|| format!("Failed to write {}", output_path.display()))?;
                tracing::info!("Wrote: {}", output_path.display());
            } else if let Some(ref file) = cli.output_file {
                let output_path = PathBuf::from(file);
                audio::write_wav(&output_path, sample_rate, &audio_data)
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
