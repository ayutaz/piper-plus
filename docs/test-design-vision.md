# テスト設計ビジョン — M1/M2 完了後の統合指針

M1 (本番コード抽出 6件) と M2 (テスト書き換え 7件) の全チケット「一から作り直すとしたら」セクションから抽出した、プロジェクト横断の設計原則。

---

## 1. テストアーキテクチャの理想像

**命名規則**: `test_<関数名>_<条件>_<期待>` 形式に統一する (例: `test_apply_transfer_defaults_multispeaker_sets_gin_512`)。テストファイル名はテスト対象モジュールと 1:1 対応させる。

**配置ルール**: テンソルユーティリティ (`_normalize_id` 等) は `vits/tensor_utils.py` のような汎用モジュールに集約し、`lightning.py` は学習ループに専念させる。config パス解決のような I/O 非依存ロジックは `config_utils.py` に分離し、テスト時の重い import (`onnxruntime` 等) を回避する。

**fixture 設計原則**: (a) conftest.py の fixture はメタ fixture (`make_onnx_fixture(model_factory, stochastic, multilingual)`) で 3-5 行に圧縮する。(b) WavLM resampler のように複数テストファイルで必要なインスタンスは `scope="session"` の共有 fixture + mock (`WavLMModel.from_pretrained` を patch) で初期化コストを 1 回に抑える。(c) `@pytest.mark.parametrize` によるテーブル駆動を原則とし、同一ロジックの Case 1/2/3 列挙を排除する。

---

## 2. 本番コードのテスト容易性設計

**`main()` は薄く**: `main()` は引数パース + 1 行の関数呼び出しの連鎖に留める。M1-2 の `apply_ema_weights`、M1-3 の `apply_transfer_defaults` はこの原則の実践例。理想形は「ロード → 前処理 → エクスポート → 後処理」の明示的パイプライン (`ExportContext` dataclass で状態を受け渡し)。

**ビジネスロジックは純粋関数に**: M1-3 で見えた `args` 直接変更の副作用関数ではなく、`compute_transfer_defaults(...) -> dict[str, Any]` のように入力から出力への変換として設計する。テスト側は戻り値を assert するだけで `argparse.Namespace` のセットアップが不要になる。M1-2 でも `apply_ema_weights(decoder, shadow_params)` と I/O を分離し、`load_ema_state(path)` を別関数にすれば `torch.save` なしでテスト可能になる。

**I/O は境界に**: `resolve_config_path` は Rust 版と同様にファイル不在時に例外を投げる設計にし、呼び出し側での確認漏れを防ぐ。`build_onnx_inputs()` で sid/lid/prosody の解決と inputs 辞書構築を一括して抽出すれば、`main()` の 100 行ループが関数呼び出し 1 行になる。

---

## 3. 再発防止の仕組み

**コードレビューチェックリスト** (M1/M2 で発見したアンチパターンに基づく):
- テスト内に本番ロジックのコピペがないか (`from piper_train.xxx import` しているか)
- テストが本番コードを 0 行も import していない場合は reject (M2-7 の教訓)
- fixture が `torchaudio.transforms.Resample(...)` 等を独自構築していないか (M2-2)

**CI lint**: テストファイル内の `def ` 定義が本番モジュールの同名関数と重複していないか検出する静的チェックを検討する。M1-5 で発覚した「テスト内に `resolve_config_path()` を再定義」のパターンを機械的に防止できる。

**テスト品質メトリクス**: テスト内のコピペ本番ロジック箇所数を 0 に維持する。M0 開始時点で 13 件 (M1: 6件 + M2: 7件) あった問題が M1/M2 完了で 0 件になることを CI で計測する。

---

## 4. M3 + 将来への提言

**M3 残り 3 件の優先順位**:
1. **M3-2** (map_sequence インライン化) — 1 行ラッパーの除去、最小工数で完了。最優先。
2. **M3-1** (swedish _split_ipa_to_phonemes) — Option B (docstring 修正のみ) を推奨。
3. **M3-3** (BOS/EOS ラッパー共通化) — EOS 統一は `test_phonemize.py` に波及するため慎重に。M2-5 との同一ファイル競合にも注意。

**M1/M2 で見送った改善の優先順位**:
1. **`SynthesizerTrn.infer()` メソッド追加** (M1-1): `build_infer_forward()` を不要にする根本解決。`models.py` への影響が大きいが、テスト容易性の最大改善点。
2. **`OnnxExportHelper` クラス** (M1-1): conftest の 3 fixture を 3 行に圧縮。`build_infer_forward` + ダミー入力 + input_names を統合。
3. **`build_onnx_inputs()` 抽出** (M1-6): sid/lid/prosody の解決を一括テスト可能にする。
4. **`pytest-benchmark` 導入** (M2-3): 手動 `time.perf_counter()` を置き換え。
5. **`commons.de_intersperse()` 追加** (M2-4): テスト用逆変換の公開 API 化。
6. **parametrize 全面適用** (M1-3, M1-4, M1-5, M1-6): 全テストをテーブル駆動に。

---

*作成日: 2026-04-09 / M1 6件 + M2 7件の「一から作り直すとしたら」セクションに基づく統合*
