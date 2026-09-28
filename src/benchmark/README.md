# Benchmark scripts (手動実行)

VITS 推論の RTF (real-time factor) を測るマイクロベンチマーク。 **CI からは実行されない。**

ランタイム横断の end-to-end 計測は `scripts/benchmark_runtime.py` +
`.github/workflows/multi-runtime-rtf.yml` が担当し、 各ランタイムの CLI を black box
として扱う。 本ディレクトリはそれより下のレイヤで、 **モデル単体の推論時間**を
`phoneme_ids` 入力から直接測る (G2P / CLI 起動を含まない)。 MB-iSTFT decoder の
A/B 比較のような内部計測はこちらを使う。

## スクリプト

| script | 対象 | 入力モデル |
|---|---|---|
| `benchmark_onnx.py` | ONNX Runtime session (`piper_train.ort_utils.create_session_options` 準拠) | `.onnx` (`piper_train.export_onnx` 出力) |
| `benchmark_torchscript.py` | TorchScript | `.ts` (`piper_train.export_torchscript` 出力) |

どちらも stdin から 1 行 1 発話の JSONL を読み、 `load_sec` / `rtf_mean` /
`rtf_stdev` / RTF 配列を JSON で stdout に出す。

## 使い方

```bash
uv pip install -r src/benchmark/requirements.txt

echo '{"phoneme_ids": [1, 2, 3], "speaker_id": 0}' \
  | uv run python src/benchmark/benchmark_onnx.py -m model.onnx -c model.onnx.json
```

`-c` を省略した場合は `<model>.json` を読む。 `speaker_id` は任意
(single-speaker モデルでは省略する)。

`benchmark_torchscript.py` は `export_torchscript.py` がトレースした 6 引数
(`sequences`, `sequence_lengths`, `sid`, `noise_scale`, `length_scale`, `noise_w`)
の署名に合わせて呼び出す。

## 依存の監視

`requirements.txt` は `.github/workflows/` のどこからも参照されないため、 放置すると
上流 advisory に追従できない。 `.github/dependabot.yml` の `pip: /src/benchmark`
エントリで月次監視している。

## 履歴

`benchmark_generator.py` は削除した。 生の `Generator` を `torch.load` で読んで測る
スクリプトだったが、 v1.12.0 で `Generator` クラス自体が廃止され (現在は
`MBiSTFTGenerator`)、 対象の `.pt` を生成する経路が存在しないため。
