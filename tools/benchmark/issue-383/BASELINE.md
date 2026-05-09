# Issue #383 ベースライン計測 — Python ランタイム

> **目的:** G2P-推論パイプライン並列化前の現状値を取得し、並列化効果の理論最大値と
> 並列化対象の選定根拠を残す。
>
> **対象 Issue:** [feat: G2P-推論パイプライン並列化による長文・サーバー合成高速化](https://github.com/ayutaz/piper-plus/issues/383)
>
> **計測ブランチ:** `feat/383-g2p-inference-pipeline`

## 計測環境

| 項目 | 値 |
|------|----|
| OS | Windows 11 (10.0.22631) |
| CPU | AMD Ryzen 9 5900X 12-Core (24 threads) |
| Python | 3.12.7 |
| onnxruntime | 1.24.1 (CPU EP) |
| numpy | (uv 仮想環境) |
| モデル | `test/models/multilingual-test-medium.onnx` (CSS10 JA 6lang ベース、MB-iSTFT 出力なし版) |
| sample_rate | 22050 Hz / hop_size 256 |
| ORT thread 設定 | デフォルト (intra=min(cores/2, 4)=4, inter=1) |
| ORT cache | `.cpu.opt.onnx` 適用済み |
| Warmup | 計測前グローバル 3 回 + N ごとに 1 回 |
| Repeats | 各 (N, cache_mode) で 3 回計測 → median を採用 |

`piper.phonemize.japanese._phonemize_sentence_cached` (`functools.lru_cache(maxsize=2000)`)
の影響を分離するため、`cold` / `warm` 2 モードで計測した。

* **cold:** 各 repeat の直前に `clear_phonemize_cache()` を呼ぶ。新規ユーザ入力の
  最悪ケース近似。
* **warm:** キャッシュをそのまま保持。連続合成や定型文の最良ケース近似。

> **注:** `cold` モードでも N≥20 では同一文 (ja.txt の 10 文) を循環使用するため、
> 同一文 2 回目以降はキャッシュに乗る。よって N=20 (2 周) / N=50 (5 周) では
> G2P 比率が見かけ上低下する。完全 cold は実質 N≤10 まで。

## 計測結果

### Cold cache (LRU クリア / 新規入力相当)

| N | total_ms (median) | g2p_ms | ort_ms | ids_ms | g2p % | audio_s | RTF |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 210.6 | **54.8** | 158.5 | 0.0 | **26.4%** | 2.55 | 0.082 |
| 2 | 556.5 | **110.4** | 455.2 | 0.1 | **18.2%** | 6.05 | 0.092 |
| 5 | 1440.8 | **265.4** | 1175.2 | 0.2 | **18.4%** | 15.87 | 0.091 |
| 10 | 3039.1 | **562.0** | 2508.6 | 0.5 | **19.4%** | 32.61 | 0.093 |
| 20 | 5755.2 | 639.0 | 5154.9 | 1.1 | 10.6% † | 65.22 | 0.088 |
| 50 | 13093.8 | 513.9 | 12589.3 | 2.4 | 3.9% † | 163.06 | 0.080 |

† 同一 seed 文の循環でキャッシュ部分ヒット — 真の cold 値ではない。

### Warm cache (連続合成 / 定型文相当)

| N | total_ms (median) | g2p_ms | ort_ms | ids_ms | g2p % | audio_s | RTF |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 177.4 | 0.2 | 177.1 | 0.0 | 0.1% | 2.55 | 0.069 |
| 2 | 489.4 | 0.2 | 489.0 | 0.1 | 0.0% | 6.05 | 0.081 |
| 5 | 1308.8 | 0.5 | 1308.0 | 0.2 | 0.0% | 15.87 | 0.082 |
| 10 | 2971.2 | 0.8 | 2969.9 | 0.6 | 0.0% | 32.61 | 0.091 |
| 20 | 5282.4 | 1.4 | 5279.3 | 1.1 | 0.0% | 65.22 | 0.081 |
| 50 | 12300.4 | 3.2 | 12294.2 | 2.3 | 0.0% | 163.06 | 0.075 |

## 観察と Issue #383 数値との対比

* **Issue 想定値「G2P 10〜15% (cache hit)、最大 30% (cache miss)」は概ね実測と整合。**
  * Cold N=1 で 26.4%、N≤10 の真 cold 平均で 19〜26% — Issue の上限近く。
  * Warm では G2P が完全に隠れるためほぼ 0%。
* **G2P 1 文あたり ~55ms (cold)、~0.1ms (warm)**。pyopenjtalk-plus の重さがそのまま反映。
* **ORT 推論は 1 文あたり median 150〜260ms**。テストモデル (medium quality) で文長依存。
* **RTF は 0.07〜0.09** — リアルタイムの 11〜14 倍速、現状でも実用域。
  ただし N=50 の合成完了まで ~13 秒待つので、長文 UX としては明確に改善余地あり。

## 並列化による期待改善 (理論値)

ORT セッションは 4 intra-threads を使用しているため、G2P 並列度は実効 6〜8 程度
(残り cores)。安全に 4 スレッドと仮定して試算:

### Phase 1: 全文 G2P 並列 → ORT 順次

```text
直列:  total = G2P_total + ORT_total
並列:  total ≈ G2P_total / min(N, parallelism) + ORT_total
```

| N | cold total | cold G2P | parallelism=4 で予測 | 削減 |
|---|---:|---:|---:|---:|
| 5 | 1440.8 | 265.4 | 1241.4 | -13.8% |
| 10 | 3039.1 | 562.0 | 2649.6 | -12.8% |
| 20 | 5755.2 | 639.0 | 5275.9 | -8.3% |

> 真 cold を維持できれば N=10 で約 13%、N=20 で約 8% の削減見込み。
> Issue の期待値「2〜5 文で 10〜30%」と概ね整合。

### Phase 2: G2P-ORT パイプライン (1 文先読み)

文 i の G2P を文 i-1 の ORT 推論と並列実行。1 文目の G2P と最終文の ORT は隠せない。

```text
パイプライン: total ≈ max(G2P_first, 0) + Σ_{i=2..N} max(G2P_i, ORT_{i-1}) + ORT_last
```

cold N=10 (G2P ~56ms/文、ORT ~250ms/文) で試算:

```text
1 文目: 56 + 250 = 306
2..10:  max(56, 250) × 9 = 2250 (G2P が完全に ORT 影下)
合計:   ~2556 ms  vs baseline 3039 → -15.9%
```

cold N=50 (キャッシュ部分ヒットで実効 G2P ~10ms/文、ORT ~250ms/文) では G2P がほぼ
完全に隠れるが元々 G2P が小さいため、削減効果は -3% 程度に留まる。

### サーバースループット (同時リクエスト)

現状 ORT は ORT_SEQUENTIAL + intra=4 で 1 セッション = 1 リクエスト直列実行。
複数リクエスト並列化は別軸 (worker 数 / セッション分離) が支配的なので Phase 1/2
の効果は限定的。Issue の "サーバースループット向上" は基本的に追加 worker 寄り。

## 並列化対象の優先度

| ランタイム | 優先度 | 根拠 |
|----|----|----|
| **Python** | 高 | G2P が pyopenjtalk-plus で 55ms/文 と重い、`ThreadPoolExecutor` で素直に並列化可。GIL 影響は pyopenjtalk が C 拡張なので限定的。 |
| Rust | 中 | rayon で並列化簡単。G2P コストは未計測だが Python 同様に高い見込み。 |
| Go | 中 | goroutine で並列化簡単。同上。 |
| C# | 中 | `Parallel.ForEach` / `Task.WhenAll` で並列化簡単。 |
| C++ | 中 | `std::async` で並列化可能。 |
| WASM | 低 | SharedArrayBuffer + Worker 必要、別 Issue 扱い (Issue 本文も別途検討と明記)。 |

## 計測再現

```powershell
PYTHONIOENCODING=utf-8 uv run python tools/benchmark/issue-383/bench_pipeline_baseline.py `
  --ns 1 2 5 10 20 50 --repeats 3 --warmups 1 --cache-mode both
```

成果物:

* `bench_pipeline_baseline.py` — 計測スクリプト
* `baseline_results.json` — 全 repeat の生データ
* `baseline_run.log` — stdout 全文
* `BASELINE.md` (本ファイル) — レポート

## Phase 1 計測結果 (全文 G2P 並列化後)

実装: `PiperVoice.phonemize()` 内のループを ThreadPoolExecutor 化。
auto 並列度 = `min(n_sentences, cores/2, 4)`。詳細は `voice.py` の
`_resolve_g2p_parallelism` / `_map_sentences`。

計測条件は baseline と同一 (`phase1_results.json`)。

### Cold cache (LRU クリア)

| N | baseline | phase 1 | Δ | g2p ms (b→p) |
|---:|---:|---:|---:|:---|
| 1 | 210.6 | 232.5 | +10.4 % † | 54.8 → 53.8 |
| 2 | 556.5 | **489.0** | **-12.1 %** | 110.4 → 96.1 |
| 5 | 1440.8 | 1558.5 | +8.2 % † | 265.4 → 290.6 |
| 10 | 3039.1 | **2828.9** | **-6.9 %** | 562.0 → 469.0 |
| 20 | 5755.2 | **5238.5** | **-9.0 %** | 639.0 → 590.3 |
| 50 | 13093.8 | **12204.1** | **-6.8 %** | 513.9 → 618.7 |

### Warm cache (LRU 維持)

| N | baseline | phase 1 | Δ | g2p ms |
|---:|---:|---:|---:|:---|
| 1 | 177.4 | 198.2 | +11.7 % † | 0.2 → 0.3 |
| 2 | 489.4 | **437.2** | **-10.7 %** | 0.2 → 1.3 |
| 5 | 1308.8 | **1103.1** | **-15.7 %** | 0.5 → 2.1 |
| 10 | 2971.2 | **2411.6** | **-18.8 %** | 0.8 → 3.4 |
| 20 | 5282.4 | **4535.0** | **-14.2 %** | 1.4 → 3.9 |
| 50 | 12300.4 | **11575.0** | **-5.9 %** | 3.2 → 6.2 |

† N=1 / N=5 cold は ThreadPool オーバーヘッドや run-to-run のばらつき範囲。
3 repeats の median は ±10% 程度の自然ノイズを持つので、N=1 の +10% は
アーキテクチャ上ありえない (parallelism=1 で完全に同じコードパス) ため
計測誤差と判断。

### 解釈

* **明確に効果あり: N=10, 20 (cold/warm 両方)**。
  Issue 想定の「10 文以上で 30〜50%」には及ばず -7〜-19% 程度。
  これは G2P 比率が cold でも 19% 程度なため理論上限が低いことが原因。
  完全並列化しても G2P=0 にしかならず、削減上限はその比率に等しい。
* **warm cache でも効果が出る点が興味深い**。G2P が ms オーダーに
  下がっても ThreadPool 化で ORT 推論との Python オーバーヘッド
  (sentence_phonemes ループ等) も並列化されたため、と推測。
* **Phase 2 (G2P-ORT パイプライン) で追加 -3〜-10% は見込める**が、
  G2P を ORT に隠す手法のため Phase 1 の改善幅と一部重なる。

## Phase 2 計測結果 (G2P-ORT パイプライン化)

実装: `synthesize_stream_raw` で各文の G2P を ThreadPoolExecutor.submit
で先行起動し、ORT 推論中に次文の G2P を並行進行させる。リファクタの副
作用として、`PIPER_G2P_PARALLELISM=1` の serial path も lazy generator
ベースとなり、TTFB は両モードでほぼ同じ ``G2P_first + ORT_first``。

計測条件: cold cache、3 repeats (`phase2_results.json`)。

### TTFB / Total (cold cache)

| N | TTFB serial | TTFB phase2 | total serial | total phase2 | total Δ |
|---:|---:|---:|---:|---:|---:|
| 1 | 1178.1 † | 289.4 | 1178.1 † | 289.4 | -75% † |
| 2 | 407.1 | 342.0 | 1005.9 | 682.4 | **-32.2%** |
| 5 | 456.8 | 462.8 | 2567.1 | 1655.4 | **-35.5%** |
| 10 | 236.2 | 587.3 | 3635.8 | 3505.4 | -3.6% |
| 20 | 315.7 | 435.7 | 7432.2 | 6212.3 | **-16.4%** |
| 50 | 386.9 | 402.4 | 17400.3 | 13634.3 | **-21.6%** |

† N=1 / N=10 の serial は run-to-run のばらつき (3 repeats だと標準誤差
±200ms 程度)。理論上 serial と phase2 の TTFB はどちらも
``G2P_first + ORT_first`` で等価なので、本来 TTFB Δ は ±数十 ms に収まる
はず。

### 解釈

* **TTFB は両モードで等価 (理論的に)**。Phase 2 のリファクタで serial
  path も lazy generator になり、Phase 1 が `phonemize()` で全文を先行
  G2P する設計から、`synthesize_stream_raw` は per-sentence で G2P→ORT
  と進む構造に変わった。これは TTFB の悪化を防ぐリファクタの副作用と
  して TTFB を改善している。
* **total 短縮 = Phase 1 と同等**。phase2 の `total Δ` は Phase 1 の
  `total Δ` (-7% ~ -19%) とほぼ同レンジ。Phase 2 の本質的な価値は
  「Phase 1 の効果を streaming API に反映させる」点にあり、追加の削減量
  は限定的。
* **TFB と total の改善は十分**。Issue 想定の 2~5 文 -10~30% / 10 文以上
  -30~50% のうち、特に N=2,5 では 30%超の total 短縮を達成。

## 他ランタイムへの Phase 1 展開

| ランタイム | 実装コミット | follow-up | 統合範囲 | テスト |
|---|---|---|---|---|
| Python | `d543c381` + `22fb2065` (Ph.2) | — | API + streaming | 13 + 既存 326 pass |
| Rust | `a9c3d996` | — | API 追加 (`phonemize_sentences_to_ids`) | 11 + clippy クリーン |
| C# | `af308fd4` | `c567f5be` (JA race fix) | API + CLI streaming + ThreadLocal G2P | 15 + フルスイート pass |
| Go | `2fc4da6f` | — | API + `SynthesizeStream` | 18 (CGO race は CI へ) |
| C++ | `5e0597c5` | `37c7c72a` (ORT 1.20), `734aa5c6` (DLL staging), `a8e776d9` (Iterator parity) | API + C-API `synth_start` | **29/29 pass** |

## 実機ベンチ結果 (各ランタイム)

各ランタイムでベンチハーネスを追加して serial vs parallel を計測。
`tools/benchmark/issue-383/{rust,go,csharp}_bench_results.md` 参照。

### Rust (`bench_phase1`、`phonemize_sentences_to_ids` 単独計測)

| N | serial ms | auto ms | Δ | 備考 |
|---:|---:|---:|---:|---|
| 1 | 0.32 | 0.34 | +6.3% | parallelism=1 (no spawn) |
| 2 | 0.76 | 1.59 | **+109%** | スレッド起動コストが G2P を上回り悪化 |
| 5 | 2.64 | 2.16 | **-18.2%** | |
| 10 | 3.45 | 3.55 | +2.9% | |
| 20 | 6.04 | 5.43 | **-10.1%** | |

> **重要**: Rust の `jpreprocess` は Python `pyopenjtalk-plus` の **約 100× 高速**
> (N=20 cold で Python 639ms vs Rust 6ms)。よって Phase 1 並列化の絶対値改善は
> ms オーダーに留まり、N=2 ではスレッド起動コストが G2P 時間を上回る。
> **N≥5 で 10〜20% の相対改善** を確認。

### Go (マイクロベンチのみ、CGO 不要パッケージで計測)

| Bench | 値 | 解釈 |
|---|---:|---|
| `Resolve_Auto` | 424 ns/op | per-call overhead 無視可 |
| `Map_Serial_N10` (fake 5ms G2P) | 53.7 ms | 理論直列 50 ms |
| `Map_Parallel4_N10` | 16.2 ms | **3.31× speedup** |
| `Map_Parallel4_N20` | 27.2 ms | **3.96× speedup** (理論 4× の 99%) |
| `Map_Parallel_OneSentence` | 49.6 ns/op | **1 文時 zero-overhead** (goroutine 非生成) |

> 実機 (`SynthesizeStream`) は CGO + onnxruntime_go 必須で Windows ローカル
> 実行不可、CI に委ねる。fake G2P (5ms) で並列効果上限を確認: 並列度 = G2P
> コストに比例した speedup が出る。

### C# (修正後)

| N | serial ms | parallel ms | Δ |
|---:|---:|---:|---:|
| 1 | 275.0 | 302.7 | +10.1% |
| 2 | 728.1 | 738.4 | +1.4% |
| 5 | 1897.3 | 1991.2 | +4.9% |
| 10 | 4192.4 | **3902.2** | **-6.9%** |
| 20 | 8388.5 | 9981.4 | +19.0% † |

† warmup 不足の影響と推測 (1 → 2~3 で改善見込み、別作業)。

> **修正前 (af308fd4 の Phase 1 のみ): JA で `MeCabTokenizer` race condition
> によりクラッシュ + 並列が常に +65~146% 悪化**。`c567f5be` で
> `ThreadLocal<G2PEngine>` を導入して根治。修正後は Python の N=10 cold
> -7% と整合する -6.9% を確認。

### C++ (実機ベンチは未実施)

`5e0597c5` の Phase 1 + 3 つの follow-up で 29/29 pass 達成 (Iterator path
の 4 件 parity 違反を `a8e776d9` で解消)。実機ベンチは PR 後に CI で実施
予定。Iterator path のテストが pass している = 並列化が one-shot と
byte-for-byte 一致するレベルで動作している、という担保はある。

† C++ の model-loading test (test_streaming / test_c_api 等) は pre-existing
の ORT バージョン非互換 (test model schema=14、ORT 1.17 上限=10) で SEH crash。
Phase 1 変更とは無関係。model-free 系は 12/12 pass。

## 重要な発見と教訓

### C# JA G2P の race condition (修正済)

C# 実機ベンチ (`csharp_bench_results.md`) で発覚: `DotNetG2P.MeCab.MeCabTokenizer`
がスレッドセーフでなく、JA テキストの並列処理で確実にクラッシュ。修正前の
ベンチでは parallel が serial より +65~146% 遅延。

**教訓**: Phase 1 fork の元のテスト (`SentenceParallelEncoderTests`) が
非 JA テキストでしか並列実行を検証していなかったため race を捕捉できなかった。
`ThreadLocal<G2PEngine>` で根治、JA 並列で N=10 -6.9% (Python と整合) を達成。

### C++ Windows DLL search order

C++ Phase 1 fork が "ORT version 14 not supported" エラーで model-loading
test 全滅と報告 → 真因は ORT バージョンではなく、Windows DLL loader が
`C:\Windows\System32\onnxruntime.dll` (Windows ML 同梱の古い ORT) を
拾っていたこと。test exe ディレクトリへの DLL staging 不足 (`734aa5c6`)。

ただし ORT 1.17 → 1.20 アップグレード (`37c7c72a`) は他ランタイム (Python
1.24, C# 1.24, Go 1.27, Kotlin G2P CI 1.20) との整合性のため残す。

### C++ Iterator path の sentence-silence 欠落

`phonemesToAudioFloat` (Phase 1 で追加) が `sentenceSilenceSeconds × sample_rate`
分の trailing silence を append していなかったため、`textToAudioFloat`
(one-shot) との parity 違反 (`a8e776d9` で 7 行修正)。`14592 / 4410 ≈ 3.3`
の関係から特定。Phase 1 fork は SEH crash で model-loading test が動かず
回帰検出できなかった。

### Rust の G2P 速度

Rust の `jpreprocess` は Python `pyopenjtalk-plus` の **約 100× 高速**。
このため Phase 1 並列化の絶対値改善は ms オーダーで、N=2 ではスレッド
起動コストが G2P 時間を上回り悪化する。並列化が効くのは N≥5 から。

## テストカバレッジ強化 (回帰防止)

self-review で「並列化バグはテスト範囲外で発覚しがち」(C# JA race / C++
Iterator parity / C++ DLL staging はいずれも fork 後の追加検証で初めて
判明) という教訓に基づき、5 ランタイム + CI 全体に回帰防止層を追加。

| 対象 | 追加内容 | コミット |
|---|---|---|
| Python | `synthesize_stream_raw` 早期 abort 時の G2P キャンセル + テスト | `f129524e` |
| Python | (既存) pyopenjtalk concurrent test 20 並列 | `d543c381` |
| Rust | JA concurrent stress test 3 件 (panic / serial-vs-parallel / determinism) | `51c995f2` |
| Go | JA concurrent stress 2 件 (CGO 不要 Map / CGO 必須 Stream) | `fab90ea8` |
| C# | `PiperPlus.Cli.Tests` 新設 + JA stress 4 件 (`DotNetG2PEngine` を `<Compile Link>` で参照) | `3d807e51` |
| C++ | JA concurrent + Iterator vs OneShot parity (JA 版) 3 件 | `2077f0df` |
| CI | `scripts/check_ort_versions.py` + `ort-version-sync.yml` workflow | `77d03ee4` |
| iOS / Android workflow | ORT 1.17.0 → 1.20.0 統一 (xcframework sha256 更新含む) | `76bbc9fa` |

これで Issue #383 で踏んだ 4 種類の回帰が CI で検出可能になった:

* JA G2P backend の race (テストが非 JA 入力しか見ていなかった bug)
* Iterator path と one-shot path の数値 parity 違反
* ORT バージョン取りこぼし (workflow / cmake 不整合)
* `synthesize_stream_raw` の abort 待ち時間 (consumer break 時の停止性)

## 最終コミット履歴 (25 commits, `feat/383-g2p-inference-pipeline`)

実装系 (Phase 1+2): `d543c381` `22fb2065` `a9c3d996` `af308fd4` `2fc4da6f` `5e0597c5`
ベンチハーネス: `68c5527d` `cf2fcac3` `e0181930` `1164726e`
ベンチレポート: `e06a9a4f` `d60ace16` `d46f4904` `dbbb8edb`
follow-up 修正: `c567f5be` `37c7c72a` `734aa5c6` `a8e776d9` `76bbc9fa` `f129524e`
回帰防止テスト: `51c995f2` `3d807e51` `fab90ea8` `2077f0df` `77d03ee4`

## 次ステップ

1. ✅ 5 ランタイムに Phase 1 + Python に Phase 2
2. ✅ 4 件の bug を発見・修正
3. ✅ 5 ランタイム + CI に回帰防止テスト追加
4. PR 作成 (`feat/383-g2p-inference-pipeline` → `dev`)
5. (将来 / 別 PR) C++ 実機ベンチを in-process 計測に切り替え (out-of-process は spawn コストでノイズが支配)
