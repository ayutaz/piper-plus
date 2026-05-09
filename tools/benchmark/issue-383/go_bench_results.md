# Issue #383 Phase 1 — Go 実機ベンチ

> 対応: `feat(go): G2P を全文並列実行 (Phase 1, Issue #383)` (`2fc4da6f`)

## 計測環境

| 項目 | 値 |
|------|----|
| OS | Windows 11 (10.0.22631) |
| CPU | AMD Ryzen 9 5900X 12-Core (24 threads) |
| Go | 1.26.1 windows/amd64 |
| ORT | onnxruntime_go v1.27.0 (CGO 必須) |

## 計測手段

Go のフルランタイムベンチには CGO + gcc が必要 (`onnxruntime_go` の依存)。
本機の Windows 環境にはローカル C ツールチェインがないため、`Voice.SynthesizeStream`
の実機計測は CI の Linux ランナーへ委譲する。代替として:

1. **マイクロベンチ** (`piperplus/internal/parallelism` パッケージ単体、CGO 非依存)
   - resolver / 順序保持 Map のオーバーヘッドを直接測定
   - 5 ms の fake G2P (sleep) で N 文の並列 speedup を測定 → Phase 1 が
     ORT を含まないコア部分でどれだけ wall-clock を縮めるかの上限値
2. **実機ベンチハーネス** (`src/go/cmd/bench-pipeline/main.go`、CGO 必須)
   - `Voice.SynthesizeStream` を `serial` (`PIPER_G2P_PARALLELISM=1`) /
     `auto` で計測 → Linux/CI 実行用にコードのみ追加

## マイクロベンチ結果

`go test ./piperplus/internal/parallelism/ -bench=. -benchmem -run=^$ -benchtime=2s`

| ベンチ | ns/op | B/op | allocs/op |
|---|---:|---:|---:|
| `Resolve_Auto` | **424** | 256 | 2 |
| `Resolve_ForceSerial` | 597 | 257 | 3 |
| `Map_Serial_N10` | 53,671,561 (≈ 53.7 ms) | 339 | 11 |
| `Map_Parallel4_N10` | **16,220,223 (≈ 16.2 ms)** | 3,007 | 47 |
| `Map_Serial_N20` | 107,763,214 (≈ 107.8 ms) | 772 | 21 |
| `Map_Parallel4_N20` | **27,198,035 (≈ 27.2 ms)** | 5,833 | 87 |
| `Map_Parallel_OneSentence` | **49.58** | 16 | 1 |

### 解釈

- **Resolver は 1 µs 未満**。SynthesizeStream の per-call overhead は無視できる。
- **N=10、4 並列で 3.31× speedup** (53.7 → 16.2 ms)。理論上限 4× に対して 83 %。
- **N=20、4 並列で 3.96× speedup** (107.8 → 27.2 ms)。理論上限 4× に対して 99 %。
  N が増えるほどスケジューラの隙間が減って効率が上がる。
- **N=1 の zero-overhead 主張を定量化** — Parallel パスでも workers=4 を要求しても
  goroutine を生成せず 49.58 ns/op に収まる。Python と同じ「1 文時はスレッドを作らない」
  契約を Go 側でも守れている。
- アロケーション増加 (Map Serial 11 vs Parallel4 47) はチャネル + worker クロージャ
  起因。1 sentence あたり ~4 alloc 増は許容範囲。

これらは fake G2P (5 ms sleep) を仮定した上限値。実 G2P は Mutex 越しの
MeCab 呼び出しなので、実機の speedup は Python の cold-cache 値
(N=10 で約 -7 %、N=20 で約 -9 %) に近づくはず。

## 実機ベンチハーネス (`src/go/cmd/bench-pipeline`)

CGO が利用できる環境では以下で実行:

```bash
go run ./src/go/cmd/bench-pipeline \
  --model test/models/multilingual-test-medium.onnx \
  --text-file tools/benchmark/texts/ja.txt \
  --ns 1,2,5,10,20 --repeats 3 --warmups 1 \
  --out tools/benchmark/issue-383/go_bench_results_runtime.md
```

| N | serial_ms | auto_ms | Δ |
|---:|---:|---:|---:|
| 1 | TBD (CI) | TBD (CI) | TBD |
| 2 | TBD (CI) | TBD (CI) | TBD |
| 5 | TBD (CI) | TBD (CI) | TBD |
| 10 | TBD (CI) | TBD (CI) | TBD |
| 20 | TBD (CI) | TBD (CI) | TBD |

ベンチ本体 (`main.go`) は `gofmt` / `go vet` (CGO=0 では `onnxruntime_go` が
build 制約で除外されるため部分的に失敗するのは想定通り) でローカル構文確認済み。

## Python 比較

| 指標 | Python (cold N=10) | Go (Map_Parallel4_N10、fake 5ms) |
|---|---|---|
| Speedup | 1.07× (-7 %) | 3.31× (-70 %) |

差の主因:

1. Python の実 G2P は `pyopenjtalk-plus` で 1 文 ~55 ms、ORT 推論は 1 文
   ~250 ms。並列化は G2P のみで、ORT 順次部分が支配的。
2. Go の microbench は ORT 部分を含まない純粋 G2P 並列の上限値。
3. Go の実機 (Linux/CI) では Python と同様、ORT 順次が支配的になり Δ は
   Python と同オーダーに収束する見込み。

実機計測値は CI 経由で別途追記する。
