//! Concurrent stress test for the Japanese G2P backend (Issue #383 follow-up).
//!
//! C# fork (`af308fd4`) で並列パイプライン化したあと、実機ベンチ
//! (`csharp_bench_results.md`) で `DotNetG2P.MeCab.MeCabTokenizer` の
//! race condition (`NullReferenceException` in `Lattice.ViterbiDecoder.Decode`)
//! が露見し、`c567f5be` で `ThreadLocal<G2PEngine>` を導入して根治した。
//!
//! 同種の race を Rust の `jpreprocess` backend で **未然に** 検出するための
//! レグレッションテスト。Phase 1 の `phonemize_sentences_to_ids` は
//! `map_sentences_parallel` 経由で複数スレッドから JA G2P を叩くため、
//! `JapanesePhonemizer` の `Phonemizer: Send + Sync` 契約が実体としても
//! 維持されていることをここで担保する。
//!
//! 既存のユニットテスト (`a9c3d996` で追加) は `_resolve_g2p_parallelism` /
//! `map_sentences_parallel` の機械的契約しか検証していない。本テストは
//! 実際の JA backend を multi-thread で叩いて panic / race を炙り出す。

#[cfg(feature = "naist-jdic")]
use piper_plus_g2p::Phonemizer;
#[cfg(feature = "naist-jdic")]
use piper_plus_g2p::japanese::JapanesePhonemizer;
#[cfg(feature = "naist-jdic")]
use std::sync::Arc;
#[cfg(feature = "naist-jdic")]
use std::thread;

#[cfg(feature = "naist-jdic")]
const JA_SENTENCES: &[&str] = &[
    "こんにちは。",
    "東京駅から新幹線で大阪まで約2時間30分かかります。",
    "昨日の会議では、新しいプロジェクトの方針について話し合いました。",
    "桜の花が満開になると、多くの人々が公園でお花見を楽しみます。",
    "明日の午後3時に渋谷のカフェで待ち合わせしましょう。",
    "日本語の音声合成技術は、近年大きく進歩しています。",
    "すみません、この近くに郵便局はありますか?",
    "彼女は毎朝6時に起きて、30分間ジョギングをしています。",
    "人工知能の発展により、私たちの生活は大きく変わろうとしています。",
    "この料理のレシピを教えていただけますか?",
];

#[cfg(feature = "naist-jdic")]
fn try_create_phonemizer() -> Option<Arc<JapanesePhonemizer>> {
    match JapanesePhonemizer::new_bundled() {
        Ok(p) => Some(Arc::new(p)),
        Err(e) => {
            eprintln!(
                "Skipping: JapanesePhonemizer::new_bundled() failed: {} \
                 (test environment likely missing the bundled NAIST-JDIC dictionary)",
                e
            );
            None
        }
    }
}

/// 8 並列スレッド × 50 iter × 10 文 = 4000 phonemize call で race / panic を検出。
///
/// 期待: 全 thread が panic なく完走、各呼び出しが Ok を返す。
/// 失敗例: jpreprocess の内部状態が共有され、`Lattice` 系の panic / data race
/// が出る場合は ここで露見する。
#[cfg(feature = "naist-jdic")]
#[test]
fn ja_concurrent_stress_no_panic() {
    let Some(phonemizer) = try_create_phonemizer() else {
        return;
    };

    const THREAD_COUNT: usize = 8;
    const ITER_PER_THREAD: usize = 50;

    let mut handles = Vec::with_capacity(THREAD_COUNT);
    for thread_idx in 0..THREAD_COUNT {
        let phonemizer = Arc::clone(&phonemizer);
        handles.push(thread::spawn(move || {
            for iter in 0..ITER_PER_THREAD {
                for (sent_idx, sentence) in JA_SENTENCES.iter().enumerate() {
                    let result = phonemizer.phonemize_with_prosody(sentence);
                    assert!(
                        result.is_ok(),
                        "phonemize failed at thread {} iter {} sentence {}: {:?}",
                        thread_idx,
                        iter,
                        sent_idx,
                        result.err()
                    );
                }
            }
        }));
    }

    for (i, h) in handles.into_iter().enumerate() {
        h.join().unwrap_or_else(|_| panic!("worker thread {} panicked", i));
    }
}

/// 直列実行と並列実行で同じトークン列が出ることを検証 (順序保持を含む)。
///
/// `MultilingualPhonemizer` 同様、`JapanesePhonemizer` も deterministic である
/// べき。並列実行で順序や内容がずれたら data race を疑う。
#[cfg(feature = "naist-jdic")]
#[test]
fn ja_serial_vs_parallel_token_consistency() {
    let Some(phonemizer) = try_create_phonemizer() else {
        return;
    };

    // 直列基準
    let serial: Vec<Vec<String>> = JA_SENTENCES
        .iter()
        .map(|s| {
            phonemizer
                .phonemize_with_prosody(s)
                .expect("serial phonemize failed")
                .0
        })
        .collect();

    // 並列: 各文を別 thread で同時に処理
    let parallel: Vec<Vec<String>> = {
        let mut handles = Vec::with_capacity(JA_SENTENCES.len());
        for sentence in JA_SENTENCES {
            let phonemizer = Arc::clone(&phonemizer);
            let sentence = sentence.to_string();
            handles.push(thread::spawn(move || {
                phonemizer
                    .phonemize_with_prosody(&sentence)
                    .expect("parallel phonemize failed")
                    .0
            }));
        }
        handles
            .into_iter()
            .map(|h| h.join().expect("thread panicked"))
            .collect()
    };

    for (i, (s, p)) in serial.iter().zip(parallel.iter()).enumerate() {
        assert_eq!(
            s, p,
            "tokens differ at sentence {} (text: {:?}):\n  serial   = {:?}\n  parallel = {:?}",
            i, JA_SENTENCES[i], s, p
        );
    }
}

/// 同一文を 4 thread から同時に呼んでも結果が deterministic であることを確認。
///
/// `JapanesePhonemizer` を共有した状態で同一入力を並列処理し、すべての出力
/// が一致することで、内部に `&mut` 経由の hidden state が無いことを担保。
#[cfg(feature = "naist-jdic")]
#[test]
fn ja_same_input_concurrent_deterministic() {
    let Some(phonemizer) = try_create_phonemizer() else {
        return;
    };

    let target = "東京駅から新幹線で大阪まで約2時間30分かかります。";

    // 期待値 (1 thread での結果)
    let expected = phonemizer
        .phonemize_with_prosody(target)
        .expect("baseline phonemize failed")
        .0;

    let mut handles = Vec::with_capacity(4);
    for _ in 0..4 {
        let phonemizer = Arc::clone(&phonemizer);
        let target = target.to_string();
        handles.push(thread::spawn(move || {
            // 各 thread で複数回呼んで race 窓を広げる
            (0..25)
                .map(|_| {
                    phonemizer
                        .phonemize_with_prosody(&target)
                        .expect("phonemize failed")
                        .0
                })
                .collect::<Vec<_>>()
        }));
    }

    for h in handles {
        let runs = h.join().expect("thread panicked");
        for run in runs {
            assert_eq!(
                run, expected,
                "non-deterministic concurrent output for fixed input"
            );
        }
    }
}
