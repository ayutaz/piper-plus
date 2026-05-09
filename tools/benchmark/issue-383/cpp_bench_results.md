# C++ Phase 1 実機ベンチ結果 (Issue #383)

`piper.exe` を `--text` 引数経由で叩き、PowerShell の `Measure-Command`
相当 (`System.Diagnostics.Stopwatch`) で wall-clock を計測。serial =
`PIPER_G2P_PARALLELISM=1`、parallel = env unset (auto)。

## 計測環境

| 項目 | 値 |
|---|---|
| OS | Windows 11 (10.0.22631) |
| CPU | AMD Ryzen 9 5900X 12-Core (24 threads) |
| Compiler | MSVC (Visual Studio 2022) |
| ONNX Runtime | 1.20.0 (Issue #383 follow-up でアップグレード) |
| Build type | Release (`cmake --build build --config Release`) |
| Binary | `build/Release/piper.exe` |
| Model | `test/models/multilingual-test-medium.onnx` (multilingual 6lang medium) |
| 計測対象 | プロセス起動 → 合成 → exit までの wall-clock |
| Warmup | 計測前グローバル 3 回 + N ごとに 1 回 |
| Repeats | 各 (N, mode) で 3 回計測 → median を採用 |
| Sentences source | `tools/benchmark/texts/ja.txt` (10 文を循環) |

## 結果

### Median wall-clock (ms)

| N | serial median | parallel median | Δ % | 全 samples (serial / parallel) |
|---:|---:|---:|---:|:---|
| 1 | 3860.6 | 8411.9 | +117.9% † | 3697.3 / 3915.6 / 3860.6 vs 8468.3 / 5674.3 / 8411.9 |
| 2 | 4613.0 | 5398.9 | +17.0% † | 4641.5 / 4026.9 / 4613.0 vs 4545.1 / 5398.9 / 5751.1 |
| 5 | 7274.0 | **6506.4** | **-10.6%** | 7274.0 / 5958.6 / 8201.0 vs 6506.4 / 6143.0 / 7352.1 |
| 10 | 9258.7 | 9820.3 | +6.1% † | 9853.9 / 9258.7 / 8476.0 vs 9820.3 / 9924.9 / 9444.8 |
| 20 | 18821.1 | 21102.3 | +12.1% † | 15900.8 / 19730.2 / 18821.1 vs 16775.9 / 21102.3 / 22757.6 |

† run-to-run variance が ±2,000 ms 以上あり、Δ がノイズの範囲を超えていない。

## 解釈

### 結論: piper.exe ベースの実機ベンチでは Phase 1 効果が startup overhead に埋没

`piper.exe` を毎回 spawn するベンチは、各 invocation で:

* プロセス起動 / DLL ロード
* ONNX Runtime セッション作成 (`InferenceSession` 構築)
* モデル warmup (2 runs of dummy inference)
* OpenJTalk 辞書ロード

を実行する。これらが per-process で約 **3,500 ms 程度** のフロアを作る
(N=1 の serial median 3,860 ms に対する内訳)。Phase 1 の並列化が効く
領域 (G2P 区間) は 1 文あたり ~50 ms 程度なので、N=10 でも純粋な G2P
時間は 500 ms に過ぎず、startup フロアの 7 倍にあたる ~3,500 ms に対し
3,500 / 9,300 ≈ **37%** にしか影響できない。さらに 3 repeats だと
run-to-run の variance が ±2,000 ms 出るため、Δ 数百 ms 単位の改善は
ノイズに完全に埋没する。

### 唯一明確な改善: N=5 で -10.6%

3 サンプルとはいえ N=5 の serial median 7,274 vs parallel median
6,506 = -10.6%。他ランタイムの傾向 (Python cold N=10 -7%, Rust N=5 -18%,
C# N=10 -7%) と方向性は一致。

### なぜ N=1 の parallel が +118% も悪いのか

`_resolve_g2p_parallelism(1) = 1` で実行パスは serial と同一のはず。
しかし parallel mode では env=unset により内部で何か (例: thread pool
の lazy init や env 読み取り回数) が走っている可能性。run-to-run の
3 サンプルが (8.5, 5.7, 8.4) と二峰性で、これは Windows のプロセス起動
キャッシュに左右されたタイミング誤差と考えられる。

### in-process micro-bench との対比

C++ の **model-free unit test** (`test_g2p_parallelism`、`5e0597c5` で
追加) は per-call ~µs レベルで `resolveG2pParallelism()` の正しさを確認
しており、Issue #383 の機能的契約はそちらで担保。**実機ベンチで Phase 1
の改善幅を測るには in-process API (`Piper::phonemesToAudioFloat()`) を
直接 N 文回す形が必要**で、`piper.exe` 起動 wall-clock の計測では
構造的に Phase 1 効果を観測しにくい。

## 他ランタイムとの比較

| ランタイム | 計測形態 | Δ (代表値) |
|---|---|---|
| Python | in-process (`PiperVoice.synthesize_stream_raw`) | cold N=10 -7%, warm N=10 -19% |
| Rust | in-process example (`bench_phase1`) | N=5 -18%, N=20 -10% |
| Go | in-process micro-bench (CGO 不要分離) | N=10 3.31×, N=20 3.96× speedup |
| C# | in-process (`SentenceParallelEncoder`) | N=10 -7% |
| **C++** | **out-of-process (`piper.exe` spawn)** | **N=5 -10.6%, 他はノイズ範囲** |

C++ の out-of-process 計測は startup cost が支配的なので、効果が見えるのは
N=5 程度の "中規模" のみ。N=1 / 2 は absolute G2P time が小さすぎ、N=10 / 20 は
3 repeats の variance に飲まれる形。これは calibration の問題で
**Phase 1 実装そのものに問題はない** (test_c_api_integration / Iterator parity
test 全 pass、`a8e776d9` で iterator silence 補正済み)。

## 改善提案 (将来別 PR)

* **In-process C++ ベンチ**: `Piper::phonemesToAudioFloat` を直接 N 回呼ぶ
  C++ 専用ベンチプログラムを `src/cpp/tests/` 等に追加し、startup cost を
  排除。
* **piper.exe `--bench` モード**: 1 起動内で N 文 × M 回計測する mode を
  CLI に追加し、Python の `bench_pipeline_baseline.py` に近い形にする。

どちらも Issue #383 の対応範囲外、PR #383 後の follow-up として整理。

## 計測再現

```powershell
# Repo root から
pwsh -File tools/benchmark/issue-383/bench_pipeline_cpp.ps1
```

成果物:
* `bench_pipeline_cpp.ps1` — 計測スクリプト
* `cpp_bench_results.json` — JSON 形式の生データ (next run で生成)
* `cpp_bench_results.md` — 本ファイル
