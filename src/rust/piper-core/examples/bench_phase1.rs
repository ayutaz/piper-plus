//! Issue #383 Phase 1 ベンチ — Rust ランタイムで G2P の serial vs parallel を計測。
//!
//! Voice::phonemize_sentences_to_ids() は piper-core の Phase 1 公開 API。
//! このベンチはその関数を N 文の sentence slice で呼び、`PIPER_G2P_PARALLELISM`
//! の値に従って serial / auto-parallel いずれかを実行する。
//!
//! 1 プロセス = 1 mode (env はプロセスグローバル) なので、PowerShell ラッパー
//! `bench_phase1.ps1` から 2 回別プロセスで起動して serial と parallel を比較する。
//!
//! Phase 1 が並列化するのは G2P のみ (ORT 推論は `&mut self.engine` で
//! 順次のまま) のため、本ベンチは G2P-only 計測。エンドツーエンドの
//! synthesize_stream 統合は別 commit / 別 Issue で扱う。

use std::env;
use std::error::Error;
use std::path::PathBuf;
use std::time::Instant;

use piper_plus::{PiperVoice, voice::resolve_g2p_parallelism};

const SEED_SENTENCES: &[&str] = &[
    "こんにちは、今日はとても良い天気ですね。",
    "東京駅から新幹線で大阪まで約2時間30分かかります。",
    "昨日の会議では、新しいプロジェクトの方針について話し合いました。",
    "この料理のレシピを教えていただけますか？",
    "桜の花が満開になると、多くの人々が公園でお花見を楽しみます。",
    "明日の午後3時に渋谷のカフェで待ち合わせしましょう。",
    "日本語の音声合成技術は、近年大きく進歩しています。",
    "すみません、この近くに郵便局はありますか？",
    "彼女は毎朝6時に起きて、30分間ジョギングをしています。",
    "人工知能の発展により、私たちの生活は大きく変わろうとしています。",
];

fn build_sentences(n: usize) -> Vec<String> {
    (0..n)
        .map(|i| SEED_SENTENCES[i % SEED_SENTENCES.len()].to_string())
        .collect()
}

fn percentile_ms(samples: &mut [f64], p: f64) -> f64 {
    samples.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = samples.len();
    let idx = ((n as f64) * p).clamp(0.0, (n - 1) as f64) as usize;
    samples[idx]
}

fn main() -> Result<(), Box<dyn Error>> {
    // CLI: bench_phase1 [model.onnx] [config.json] [n_list_csv]
    let args: Vec<String> = env::args().collect();
    let model_path = args
        .get(1)
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("test/models/multilingual-test-medium.onnx"));
    let config_path = args
        .get(2)
        .filter(|s| !s.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("test/models/multilingual-test-medium.onnx.json"));
    let ns: Vec<usize> = args
        .get(3)
        .map(|csv| {
            csv.split(',')
                .filter_map(|s| s.trim().parse().ok())
                .collect()
        })
        .unwrap_or_else(|| vec![1usize, 2, 5, 10, 20]);

    let env_value = env::var("PIPER_G2P_PARALLELISM").unwrap_or_default();
    let mode_label = if env_value == "1" { "serial" } else { "auto" };

    eprintln!("=== Issue #383 Phase 1 Rust bench ===");
    eprintln!("mode  : {}", mode_label);
    eprintln!("env   : PIPER_G2P_PARALLELISM={:?}", env_value);
    eprintln!("model : {}", model_path.display());
    eprintln!("ns    : {:?}", ns);
    eprintln!();

    let load_start = Instant::now();
    let voice = PiperVoice::load(&model_path, Some(&config_path), "cpu")?;
    eprintln!("voice loaded in {:.1} ms", load_start.elapsed().as_secs_f64() * 1000.0);

    // Print resolved parallelism for sanity check
    for &n in &ns {
        let p = resolve_g2p_parallelism(n);
        eprintln!("  resolve_g2p_parallelism({}) = {}", n, p);
    }
    eprintln!();

    // Warmup once with the smallest size to let LRU caches settle.
    let warmup_sentences = build_sentences(2);
    for _ in 0..1 {
        let _ = voice.phonemize_sentences_to_ids(&warmup_sentences);
    }

    println!("# mode\tn\trep0_ms\trep1_ms\trep2_ms\tmedian_ms\tmean_ms");
    for &n in &ns {
        let sentences = build_sentences(n);
        let mut samples_ms: Vec<f64> = Vec::with_capacity(3);
        for _ in 0..3 {
            let t0 = Instant::now();
            let results = voice.phonemize_sentences_to_ids(&sentences);
            // Force completion / surface errors
            for r in &results {
                if let Err(e) = r {
                    return Err(format!("G2P failed: {:?}", e).into());
                }
            }
            let elapsed_ms = t0.elapsed().as_secs_f64() * 1000.0;
            samples_ms.push(elapsed_ms);
        }
        let mean = samples_ms.iter().sum::<f64>() / samples_ms.len() as f64;
        let mut sorted = samples_ms.clone();
        let median = percentile_ms(&mut sorted, 0.5);
        println!(
            "{}\t{}\t{:.2}\t{:.2}\t{:.2}\t{:.2}\t{:.2}",
            mode_label, n, samples_ms[0], samples_ms[1], samples_ms[2], median, mean
        );
    }

    Ok(())
}
