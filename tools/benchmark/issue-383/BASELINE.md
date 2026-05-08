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

```
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

```
パイプライン: total ≈ max(G2P_first, 0) + Σ_{i=2..N} max(G2P_i, ORT_{i-1}) + ORT_last
```

cold N=10 (G2P ~56ms/文、ORT ~250ms/文) で試算:

```
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

## 次ステップ

1. Phase 1 (全文 G2P 並列) を `PiperVoice.synthesize_stream_raw` に実装
2. 同スクリプトで再計測、本レポートと並べて差分を出す
3. 効果が確認できたら他ランタイムに展開
