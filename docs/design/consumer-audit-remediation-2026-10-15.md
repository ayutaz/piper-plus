# 第三次 consumer 監査の対応記録

対象: [第三次監査](documentation-consumer-audit-2026-10-15.md) の A01～A16。
作業ブランチ: `fix/consumer-audit-20261015`。修正・検証日: 2026-10-15。
公開版 v2.0.1 の binary/package を差し替える作業ではなく、次の source build と文書・CI の修正。

## 要件と完了根拠

| ID | 対応 | 確認した証拠 |
|---|---|---|
| A01 | 8 README のモデル管理を `uv run --no-sync` に変更。WebUI は専用 project から起動 | shell を activate せず runtime `--help` が成功。Python の text は positional 引数へ統一 |
| A02 | CPU/GPU extras を分離。root の CPU group と GPU extra を排他化 | 両 export の provider は各 1 種。クリーンな GPU venv の pip check・provider 検査・推論成功 |
| A03 | nested artifact の hash/size 照合、明示 model/artifact 選択、custom opt-in、正確な更新と失敗時の無変更 | 正常／破損／未知 artifact・更新 helper のテスト。公開 base の実 hash/size 照合成功 |
| A04 | published の実 digest と正の整数 bytes を必須化 | empty/placeholder/negative/missing/bool の各変異を拒否。実 manifest は成功 |
| A05 | Rust JSONL を実 schema（phoneme_ids 必須）へ訂正 | parser 定義と実 CLI の JSONL→WAV 実行を照合 |
| A06 | Rust の音素境界で request/prosody を分割し、各推論の間に無音を挿入 | callback テストで正確な無音・conditioning 保持、実 CLI WAV で指定無音区間を確認 |
| A07 | Rust JSONL の default を発話別 `1.wav`, `2.wav` に。record 名／明示出力も処理 | 実 CLI を出力先省略で起動し、両 WAV の非ゼロ frame を確認 |
| A08 | C# CLI を SynthesizeWithDurations と TimingWriter へ接続。stdin は発話別 file | JSON/TSV/SRT の実ファイルを CLI から生成。公開 base の 2 発話でも JSON timing を生成 |
| A09 | Go batch／JSONL を timing writer へ接続し、連番の別 file に保存 | Docker Linux で両 mode × 3 format × 2 発話の WAV/timing 成果物を検査 |
| A10 | Rust/Go の通常合成で parser の text/rate/break を各合成へ接続 | segment テストの入力・rate・無音検査。公開 base を使った両 CLI の SSML WAV も非空 |
| A11 | 公開 Rust archive は CPU build、GPU は provider feature 付き source build と明記 | Cargo feature と release build recipe、binary-selection の案内を再照合 |
| A12 | WebUI 専用 project/lock を追加、学習 interpreter の指定と依存確認を分離 | clean UI sync、pip check、Gradio Blocks 作成、指定した学習環境の依存確認が成功 |
| A13 | Swift G2P ZIP を 149,575,363 bytes / 約142.6 MiB と訂正。app 増分の未測定値は承認材料にしない | 固定 v2.0.1 Release API の asset metadata と案内を照合 |
| A14 | setup:wasm の不存在 asset の download 案内を削除し、npm 同梱物／source build を案内 | package.json の実 script と公開 asset 一覧を照合 |
| A15 | source checker を AST の実呼出検査へ変更。両 exporter に実 artifact の graph/ORT/warmup/FP16 比較を接続 | 実 tiny ONNX の正常・破損・NaN・FP16 差分・呼出接続の回帰テスト、公開 base の graph/ORT/warmup 検査 |
| A16 | Rust の source help と取得済み help を sv も含む一覧へ更新 | 現行 build の実 `--help` を再取得 |

## 検証した範囲

- Rust: `cargo test --locked -p piper-plus --features onnx --lib` は **931 passed**。CLI は **18 passed / 2 ignored**。ignored を成果物生成の証拠にせず、別の mandatory consumer harness で WAV/無音生成を実行した。
- C#: build は warning/error 0。CLI tests は **14 passed / skipped 0**。`dotnet run --project ...Cli.Tests` で実際の test summary を確認した。
- Python: artifact/manifest/ORT drift/trigger の focused tests と実 ONNX negative tests は **61 passed**。既存の文書サンプル監査テストは **11 passed**、snapshot を更新。TrainingManager の worker/引数テストは **17 passed / 3 skipped**（root に Gradio がないため UI integration の 3 件を skip）。専用 UI 環境は別途 interface・推論・worker 依存を実行確認した。
- Go: Docker Linux で `go test ./...`、実 CLI の JSONL/batch timing 出力を確認。性能測定には使っていない。
- WebUI: 専用 lock でインストールし、依存整合検査と Gradio interface 作成を確認。公開 base への日本語入力でも 25,262 samples の音声を生成。root への HF Hub 1.x の上書きは行っていない。
- GPU: `onnxruntime-gpu==1.25.1` だけの venv で provider 一覧と CPU fallback を確認。さらに手元の Windows CUDA 環境で公開 base の CUDA provider 初期化と finite/nonempty 推論を確認した（CUDA/cuDNN DLL は既存の torch/lib から preload）。全ノード GPU 実行や品質・性能を保証するものではない。

学習 UI の worker 引数も現行 CLI の `--base_lr` / `--max_epochs` / `--default_root_dir` / `--resume_from_checkpoint` に修正し、Windows の PYTHONPATH 結合を os.pathsep に変更した。speaker count は dataset config から読む。学習プロセスの mock で確認し、実学習は実施していない。

## CI

- `.github/workflows/consumer-contracts.yml`: 3 runtime の実 CLI subprocess と WAV/timing 検査、Python provider の排他と実導入、専用 UI lock の確認。
- `model-quality-gate.yml`: nested hash/update、published manifest の negative test、実 ONNX graph/ORT/warmup と negative output の回帰テスト。
- ORT / Gradio の source 移動・pin 追加に合わせて既存 gate の path trigger も更新。

ローカルで CI と同じ helper/harness を実行している。push・タグ・release は行わず、この時点の GitHub Actions のリモート run 成功を主張するものではない。

## 利用上の変更と残る制約

Python の provider extra と環境分離は [移行ガイド](../migration/provider-environments.md) を参照。
C#/Go は duration が得られないときに timing を明示要求すると失敗する。C# は streaming と timing の同時指定を拒否する。
Rust/Go の SSML 分割合成、Rust の phoneme-silence 分割合成は単一の aligned duration tensor を返さない。[timing の制限](../features/phoneme-timing.md#複数発話と分割合成)を参照。

Swift の app 組み込み後の容量、Apple 各 provider、Raspberry Pi 実機、各言語の音声品質は今回の対応で検証していない。公開 asset の GPU variant 追加や新たなモデル公開も行っていない。
Go の公開 base SSML 試験は辞書不足による letter-by-letter fallback を含むため、読みの品質を評価していない。
Rust の公開 base native Spanish 試験は外部辞書不足により H の音素解決で失敗したため、成功例には数えていない。日本語の bundled G2P で SSML→WAV を確認した。監査で範囲外とした全言語 native G2P の品質承認へ拡張したものではない。

ローカルの追加成果物と probe は ignored directory `output/consumer-audit-fixed/` に保存した。公開モデルや研究データの上書き・削除はしていない。
