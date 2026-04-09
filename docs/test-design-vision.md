# テスト設計ビジョン — M0-M3 + レトロスペクティブ修正完了後の統合指針

M0 (壊れたテスト修正 2件)、M1 (本番コード抽出 6件)、M2 (テスト書き換え 7件)、M3 (軽微改善 3件)、およびレトロスペクティブで発見した追加修正 (8件) の全作業完了後に得られた、プロジェクト横断の設計原則。

---

## 1. テストアーキテクチャの理想像

**命名規則**: `test_<関数名>_<条件>_<期待>` 形式に統一する (例: `test_apply_transfer_defaults_multispeaker_sets_gin_512`)。テストファイル名はテスト対象モジュールと 1:1 対応させる。

**配置ルール**: テンソルユーティリティ (`normalize_id_tensor` 等) は `vits/lightning.py` のモジュールレベル公開関数として配置済み。config パス解決 (`resolve_config_path`) は `infer_onnx.py` に分離済みで、テスト時の重い import (`onnxruntime` 等) を回避可能。

**fixture 設計原則**: (a) conftest.py の fixture はメタ fixture (`make_onnx_fixture(model_factory, stochastic, multilingual)`) で 3-5 行に圧縮する。(b) WavLM resampler は `scope="session"` の `mock_wavlm_discriminator` 共有 fixture で初期化コストを 1 回に集約済み。(c) `@pytest.mark.parametrize` によるテーブル駆動を原則とし、同一ロジックの Case 1/2/3 列挙を排除する (M1-4 の `test_speaker_id_tensor_handling` 等で実現済み)。

---

## 2. 本番コードのテスト容易性設計

**`main()` は薄く**: `main()` は引数パース + 1 行の関数呼び出しの連鎖に留める。M1-2 の `apply_ema_weights`、M1-3 の `apply_transfer_defaults`、レトロスペクティブの `load_multispeaker_checkpoint` はこの原則の実践例。理想形は「ロード -> 前処理 -> エクスポート -> 後処理」の明示的パイプライン (`ExportContext` dataclass で状態を受け渡し)。

**ビジネスロジックは純粋関数に**: `apply_transfer_defaults(args, num_speakers, num_languages)` は `dict_args` パラメータを除去し `args` のみを変更する設計に改善済み。更なる理想は `compute_transfer_defaults(...) -> dict[str, Any]` のように入力から出力への変換として設計すること。`apply_ema_shadow_params(decoder, shadow_params)` は I/O を分離した純粋ロジック関数として抽出済み。

**I/O は境界に**: `resolve_config_path` は Rust 版と同様にファイル不在時の確認を呼び出し側に委譲する設計。`build_onnx_inputs()` で sid/lid/prosody の解決と inputs 辞書構築を一括して抽出すれば、`main()` の 100 行ループが関数呼び出し 1 行になる。

**モデル API の改善**: `SynthesizerTrn.infer()` が durations を含む 5-tuple を返すようになり、`build_infer_forward()` は `model.infer()` への thin wrapper に簡素化された。conftest.py の ONNX fixture は `build_infer_forward` を import して利用している。

---

## 3. 再発防止の仕組み

**コードレビューチェックリスト** (M0-M3 + レトロスペクティブで発見したアンチパターンに基づく):
- テスト内に本番ロジックのコピペがないか (`from piper_train.xxx import` しているか)
- テストが本番コードを 0 行も import していない場合は reject (M2-7 の教訓)
- fixture が `torchaudio.transforms.Resample(...)` 等を独自構築していないか (M2-2)
- 共有ヘルパーが conftest.py に集約されているか (phonemize_japanese, mock_wavlm_discriminator の教訓)

**CI lint**: テストファイル内の `def ` 定義が本番モジュールの同名関数と重複していないか検出する静的チェックを検討する。M1-5 で発覚した「テスト内に `resolve_config_path()` を再定義」のパターンを機械的に防止できる。

**テスト品質メトリクス**: テスト内のコピペ本番ロジック箇所数を 0 に維持する。M0 開始時点で 13 件 (M1: 6件 + M2: 7件) あった問題が M1/M2 完了で 0 件になった。この指標を CI で計測する。

---

## 4. 将来への提言

以下は M0-M3 + レトロスペクティブ修正完了後も未対処の改善案で、優先順位順に記載する。

**実施済み (完了確認)**:
- ~~`SynthesizerTrn.infer()` durations 追加 + `build_infer_forward` thin wrapper 化~~ -- 完了
- ~~`apply_ema_shadow_params` 抽出 (I/O 分離)~~ -- 完了
- ~~`load_multispeaker_checkpoint` 抽出~~ -- 完了
- ~~`phonemize_japanese` conftest.py 集約~~ -- 完了
- ~~`normalize_id_tensor` 公開化 + rename~~ -- 完了
- ~~`mock_wavlm_discriminator` session fixture 共有化~~ -- 完了
- ~~`parametrize` 適用 (M1-4 `test_speaker_id_tensor_handling`)~~ -- 完了
- ~~`apply_transfer_defaults` から `dict_args` パラメータ除去~~ -- 完了
- ~~`infer_onnx.py` DSP dead code 削除~~ -- 完了

**残りの改善案 (優先順位順)**:
1. **`build_onnx_inputs()` 抽出** (infer_onnx.py) -- sid/lid/prosody 解決を一括テスト可能にし、main() の 100 行ループを 1 行に
2. **BOS/EOS ユーティリティの本番化** -- `piper/phonemize/` に `wrap_with_bos_eos()` を追加し、テスト側の重複ラッパーを解消
3. **`apply_transfer_defaults` の純粋関数化** -- `compute_transfer_defaults() -> dict` に転換 (現在は args in-place 変更)
4. **`OnnxExportHelper` クラス** (M1-1) -- conftest の fixture を更に簡素化。`build_infer_forward` + ダミー入力 + input_names を統合
5. **CI lint 導入** -- テスト内コピペ検出の自動化
6. **`pytest-benchmark` 導入** -- `test_performance.py` の手動 `time.perf_counter()` を置換
7. **`commons.de_intersperse()` 追加** -- テスト用逆変換の公開 API 化

---

*作成日: 2026-04-09 / 最終更新: 2026-04-09 / M0 2件 + M1 6件 + M2 7件 + M3 3件 + レトロスペクティブ 8件の全作業完了後の統合*
