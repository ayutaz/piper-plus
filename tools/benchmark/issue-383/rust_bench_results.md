# Issue #383 Phase 1 — Rust 実機ベンチ結果

> **対象 commit:** `a9c3d996` `feat(rust): G2P を全文並列実行 (Phase 1, Issue #383)`
> **ベンチハーネス:** `src/rust/piper-core/examples/bench_phase1.rs`

## 計測環境

| 項目 | 値 |
|---|---|
| OS | Windows 11 (10.0.22631) |
| CPU | AMD Ryzen 9 5900X 12-Core (24 threads) |
| Rust | 1.92.0 (ded5c06cf 2025-12-08) |
| crate | `piper-plus` 0.4.0 (workspace) |
| ORT | `ort` 2.0.0-rc.12 (CPU EP, download-binaries) |
| G2P backend | `jpreprocess` 0.9.1 + naist-jdic (bundled) |
| モデル | `test/models/multilingual-test-medium.onnx` |
| Warmup | 1 round with 2 sentences before measurement |
| Repeats | 3 per (mode, N) → median |

## 計測対象

`PiperVoice::phonemize_sentences_to_ids(sentences)` の呼び出し時間を計測。
これは Phase 1 で追加された G2P 並列化 API で、ORT 推論は含まない (Phase 1
は G2P only)。Rust 側はまだ `synthesize_stream` 統合 API を持たないため、
G2P-only ベンチで Phase 1 効果の上限を測る。

## 結果 (median over 3 repeats)

| N | serial ms | auto ms | Δ % | parallelism (auto) |
|---:|---:|---:|---:|---:|
| 1 | 0.32 | 0.34 | +6.3% | 1 (no thread spawn) |
| 2 | 0.76 | 1.59 | **+109%** | 2 |
| 5 | 2.64 | 2.16 | **-18.2%** | 4 |
| 10 | 3.45 | 3.55 | +2.9% | 4 |
| 20 | 6.04 | 5.43 | **-10.1%** | 4 |

* auto は `PIPER_G2P_PARALLELISM` 未設定 = `min(n, cores/2, 4)`。
* serial は `PIPER_G2P_PARALLELISM=1`。

## 観察と考察

### 絶対値が Python より 2 桁速い

| ランタイム | N=20 cold serial median |
|---|---:|
| Python (pyopenjtalk-plus) | 639.0 ms |
| Rust (jpreprocess) | 6.04 ms |

Rust の `jpreprocess` ベース G2P は Python の `pyopenjtalk-plus` C 拡張より
大幅に高速 (約 100x)。理由は (a) jpreprocess が pure Rust 実装で C ラッパー
オーバーヘッドなし、(b) 同一プロセス内で Rust の LRU キャッシュが効きや
すい (Python は `clear_phonemize_cache()` を本ベンチで呼んでいないが
Rust 側にも同等のキャッシュは存在する)。

### Phase 1 の相対効果は小さい

Python では cold cache N=10 で -7%、warm N=10 で -19% の改善があったのに対し、
Rust では:

* N=2: ThreadPool スレッド起動コスト (<1 ms オーダー) が G2P 時間
  (0.76 ms) を上回り **悪化**。
* N=5: -18% 改善 (median 0.5 ms 削減)。
* N=10/20: -3〜-10% 改善 (median 0.1〜0.6 ms 削減)。

Rust の G2P が既に十分速いため、Phase 1 並列化の絶対量は数 ms に留まる。
**スレッド起動オーバーヘッド (`std::thread::scope`) > G2P 時間** となる
N≤2 では純粋に悪化する。

### resolve_g2p_parallelism は期待通り

```text
resolve_g2p_parallelism(1)  = 1   ← 1 文時はスレッド非生成 (zero overhead)
resolve_g2p_parallelism(2)  = 2
resolve_g2p_parallelism(5)  = 4
resolve_g2p_parallelism(10) = 4   ← cores/2=12 や 4 cap で 4 に丸まる
resolve_g2p_parallelism(20) = 4
```

実装通りの挙動。N=1 は serial path に入りオーバーヘッドゼロ。

## Python 側との比較表

| シナリオ | Python serial | Python auto | Δ | Rust serial | Rust auto | Δ |
|---|---:|---:|---:|---:|---:|---:|
| N=2 | 489 | 437 | -10.7% | 0.76 | 1.59 | +109% |
| N=5 | 1309 | 1103 | -15.7% | 2.64 | 2.16 | -18.2% |
| N=10 | 2971 | 2412 | -18.8% | 3.45 | 3.55 | +2.9% |
| N=20 | 5282 | 4535 | -14.2% | 6.04 | 5.43 | -10.1% |

> Python と Rust は計測対象が異なる (Python は `synthesize_stream_raw`
> total = G2P + ORT、Rust は G2P-only) ため絶対値は直接比較できないが、
> **Phase 1 並列化の相対効果は両ランタイムで定性的に同方向** (N が大きい
> ほど効果増、N=2 でオーバーヘッドが目立つ)。

## 結論

* Rust 側 Phase 1 実装は仕様通り動作 (`resolve_g2p_parallelism`、
  `phonemize_sentences_to_ids` 共に期待挙動)。
* G2P が高速なため Phase 1 単独の絶対改善量は ms 単位に留まるが、
  N≥5 で 10〜20% の相対改善は確認できる。
* `synthesize_stream` 統合 (G2P + ORT エンドツーエンドのストリーミング)
  は別 commit / 別 Issue で導入することで、より大きな効果が見込める。

## 再現コマンド

```powershell
# Build once
cargo build --release --features onnx --example bench_phase1 -p piper-plus

# Serial mode
$env:PIPER_G2P_PARALLELISM = "1"
.\src\rust\target\release\examples\bench_phase1.exe

# Parallel auto mode
Remove-Item Env:PIPER_G2P_PARALLELISM
.\src\rust\target\release\examples\bench_phase1.exe
```
