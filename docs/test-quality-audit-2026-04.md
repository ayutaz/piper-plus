# テスト品質監査レポート (2026-04-09)

全30テストファイル (`src/python/tests/`) を対象に、以下のアンチパターンを調査した。

- **再実装テスト**: 本番コードのロジックをテスト内にコピペし、本番コードを呼ばずにコピー側を検証
- **壊れたテスト**: 存在しないAPIを呼び出しており、実行すると例外で落ちる
- **無意味なテスト**: 本番コードを一切呼ばず、ハードコード値やPython標準ライブラリのみを検証

---

## HIGH (本番コードが壊れてもテストが通る / テスト自体が壊れている)

### 1. `conftest.py` — `infer_forward` 3重再実装

- **場所**: L117-166, L217-258, L365-405
- **問題**: `export_onnx.py` の `infer_forward` (L278-331) を3つのfixture (`temp_onnx_model`, `temp_onnx_model_stochastic`, `temp_onnx_model_unified_emb_lang`) で個別に再実装。本番と以下の乖離がある:
  - single-speaker fixture は `_get_global_conditioning()` をスキップし `g = None` 固定
  - `_prepare_prosody_input` に `lid` を渡していない
  - 本番の `infer_forward` が変更されても3つのコピーは追従しない
- **根本原因**: 本番の `infer_forward` が `export_onnx.main()` 内のローカルクロージャで import 不可
- **推奨修正**: `export_onnx.py` に `build_infer_forward(model_g, stochastic=True) -> Callable` ファクトリ関数を抽出し、conftest から import

### 2. `test_model_config.py` — gin_channels ロジック再実装 (3テスト)

- **場所**: L67-87 (`test_gin_channels_auto_512_for_multispeaker`), L90-101 (`test_gin_channels_respects_explicit_value`), L103-115 (`test_gin_channels_not_set_for_single_speaker`)
- **問題**: `__main__.py` L430-433 の if 文をテスト内にコピペして検証。本番コードは一切呼ばれない
- **追加問題**: `lightning.py` L105 の条件 (`num_speakers > 1 or num_languages > 1`) と `__main__.py` の条件 (`num_speakers > 1`) が異なるが、テストは `num_languages > 1` パスをカバーしていない
- **推奨修正**: `VitsModel` を実際にインスタンス化して `model.hparams.gin_channels` を検証、または `__main__.py` のロジックを関数化して import

### 3. `test_freeze_dp.py` — speaker_id 正規化ロジック再実装

- **場所**: L108-167 (`test_speaker_id_tensor_handling`)
- **問題**: `lightning.py` L706-717 の speaker_id テンソル正規化 (int → LongTensor, 0-D → unsqueeze, etc.) を4パターン手動で再実装
- **推奨修正**: `lightning.py` に `_normalize_speaker_id(raw_sid) -> torch.Tensor | None` を抽出し、テストから呼び出す

### 4. `test_multispeaker_transfer.py` — 全6テストが再実装

- **場所**: L28-129 (全テスト)
- **問題**: `__main__.py` の以下のロジックを全てコピペ:
  - freeze_dp 自動有効化 (L438-443)
  - dict_args への freeze_dp 同期
  - gin_channels 自動設定 (L430-433)
- **本番コードの呼び出し**: ゼロ。全テストが本番コード削除しても通る
- **推奨修正**: `__main__.py` から `apply_quality_config()` や `apply_transfer_defaults()` を抽出して import

### 5. `test_infer_onnx_config.py` — config 解決ロジック再実装

- **場所**: L15-30 (`resolve_config_path()`)
- **問題**: `infer_onnx.py` L311-320 の config パス解決ロジックを関数としてコピペ。コメントに「Reproduce the config resolution logic from infer_onnx.main()」と明記。4テスト全てがコピーを検証
- **推奨修正**: `infer_onnx.py` に `resolve_config_path(model, config)` を抽出し、テストから import

### 6. `test_phonemizer_registry.py` — 存在しないAPI呼び出し (4テスト壊れ)

- **場所**: L79-82, L84-88 (`TestABCInterface`), L94-99 (`TestDefaultPostProcessIds`), L106-118 (`TestEnglishPostProcessIds`)
- **問題**: `Phonemizer` ABC に存在しないメソッドを呼び出し:
  - `p.get_phoneme_id_map()` — 実際は `piper_plus_g2p.encode.id_maps.get_phoneme_id_map()` (スタンドアロン関数)
  - `p.post_process_ids()` — 実際は `PiperEncoder.encode()` の一部
- **結果**: 実行すると `AttributeError` で即座に失敗。CIのマーク設定 (`@pytest.mark` 未付与等) で実行されていない可能性
- **推奨修正**: 正しい本番APIを呼ぶように書き換え、またはテスト削除

---

## MEDIUM (メンテナンス負荷・乖離リスク)

### 7. `test_export_onnx.py` — EMA適用ループ再実装

- **場所**: L142-154 (`test_ema_weights_applied`)
- **問題**: `export_onnx.py` L248-265 の EMA 重み適用ループをテスト内にコピー
- **推奨修正**: `export_onnx.py` に `apply_ema_weights(model_dec, ema_state)` を抽出

### 8. `test_performance.py` — `phonemize_japanese()` 4重コピペ

- **場所**: L32-34, L84-86, L131-133, L203-205
- **問題**: 同一の `phonemize_japanese()` 関数を4テストメソッドに個別定義。毎回 `JapanesePhonemizer()` を再インスタンス化しておりベンチマーク精度にも影響
- **推奨修正**: モジュールレベルのヘルパーに統合、またはフィクスチャ化

### 9. `test_vits.py` — リサンプリング再実装

- **場所**: L114-134 (`test_wavlm_discriminator_resample`)
- **問題**: `WavLMDiscriminator._resample()` の代わりに `torchaudio.functional.resample()` を直接呼び出し。本番は `torchaudio.transforms.Resample` (sinc_interp_hann, lowpass_filter_width=64) を使用しており、異なるコードパスをテスト
- **推奨修正**: `WavLMDiscriminator` をインスタンス化して `disc._resample()` を呼ぶ

### 10. `test_wavlm_discriminator.py` — リサンプラ設定ハードコード

- **場所**: L103-110 (`resampler_sinc` fixture)
- **問題**: `torchaudio.transforms.Resample` をハードコードパラメータで作成、本番 `WavLMDiscriminator.resampler` を未使用
- **推奨修正**: `disc.resampler` を参照するか `disc._resample()` を直接呼ぶ

### 11. `test_intersperse_padding.py` — 不変条件チェック再実装

- **場所**: L45-62 (`has_intersperse_padding()`), L65-77 (`_no_intersperse_padding()`)
- **問題**: `commons.intersperse()` が保証する不変条件を手動で再実装。本番の intersperse アルゴリズムが変わると乖離
- **推奨修正**: `commons.intersperse()` の出力と比較する方式に変更

### 12. `test_prosody_extraction.py` — ローカル関数を自己テスト

- **場所**: L550-574 (`validate_dataset_prosody()`)
- **問題**: テスト内にバリデーション関数を定義し、その関数自体をテスト。本番に対応する関数なし
- **推奨修正**: バリデーションが必要なら本番コードに抽出してテスト、不要なら削除

### 13. `test_convert_fp16.py` — ONNX推論ヘルパー再実装

- **場所**: L14-42 (`_onnx_inference()`)
- **問題**: 本番 `convert_fp16.py` の `_create_dummy_inputs()` (L322-347) と `validate_model()` (L212-319) を再実装
- **推奨修正**: 本番の `_create_dummy_inputs()` を import して使用

### 14. `test_multilingual_inference.py` — sid デフォルトロジック再実装

- **場所**: L370-417 (`TestSidDefaultForSingleSpeakerMultilingual`)
- **問題**: `infer_onnx.py` L397-411 の sid デフォルト設定ロジックを3テストで再実装
- **推奨修正**: `infer_onnx.py` に `resolve_speaker_id()` を抽出

### 15. `test_integration.py` — 本番コード無関係のテスト (2件)

- **場所**: L30-55 (`test_model_config_validation`), L57-85 (`test_wav_file_generation`)
- **問題**:
  - `test_model_config_validation`: ハードコード dict のフィールド存在確認のみ、本番コード未呼び出し
  - `test_wav_file_generation`: Python `wave` モジュールのテスト、piper-plus のコード未使用
- **推奨修正**: 本番のconfig読み込み/音声生成コードを呼ぶように書き換え、または削除

---

## LOW (軽微)

### 16. `test_swedish_phonemizer.py` — 旧API関数のテスト用コピー

- **場所**: L28-46 (`_split_ipa_to_phonemes()`)
- **問題**: 旧本番関数のテスト用コピー、2箇所のみ使用

### 17. `test_token_mapper_impl.py` — 1行ヘルパー再実装

- **場所**: L16-18 (`map_sequence()`)
- **問題**: `[map_token(t) for t in tokens]` の1行ラッパー。本番 `map_token()` に完全委譲

### 18. `test_prosody_extraction.py` — BOS/EOSグルーコード

- **場所**: L18-38 (`phonemize_japanese()`, `phonemize_japanese_with_prosody()`)
- **問題**: BOS/EOS追加の薄いラッパー。本番に対応する共通関数がない（missing shared utility 問題）

---

## CLEAN (問題なし — 19ファイル)

| ファイル | 備考 |
|---------|------|
| `test_infer_onnx.py` | 本番 `text_to_phoneme_ids_and_prosody` を直接呼び出し |
| `test_pytorch_onnx_parity.py` | `model.infer()` で PyTorch 推論、ORT で ONNX 推論 |
| `test_ddp_strategy.py` | 本番 `configure_ddp_strategy` を直接呼び出し |
| `test_validation_metrics.py` | 本番 `VitsModel.validation_step()` を直接呼び出し |
| `test_speaker_balanced_sampler.py` | 本番 `SpeakerBalancedBatchSampler` を直接テスト |
| `test_dataset_getitem.py` | 本番 `PiperDataset.__getitem__` を直接テスト |
| `test_add_prosody_features.py` | 本番 `process_utterance` を直接テスト — 模範的 |
| `test_ort_utils.py` | 全本番関数を直接テスト |
| `test_monotonic_align.py` | 本番 `maximum_path()` を直接テスト |
| `test_phonemize.py` | 本番 `JapanesePhonemizer` を直接テスト |
| `test_english_phonemizer.py` | 全本番関数を直接テスト — 模範的 |
| `test_swedish_m1_1_m1_2.py` | 全本番関数を直接テスト |
| `test_custom_dict.py` | 本番 `CustomDictionary` を直接テスト |
| `test_model_manager.py` | 本番関数を直接テスト、外部I/Oのみモック |
| `test_freeze_dp.py` (他テスト) | `VitsModel` + `configure_optimizers()` を直接テスト |
| `test_wavlm_discriminator.py` (他テスト) | 本番 `WavLMDiscriminator.forward()` を直接テスト |
| `test_multilingual_inference.py` (他テスト) | 本番 `text_to_phoneme_ids_and_prosody()` を直接テスト |
| `test_integration.py` (他テスト) | 本番 `JapanesePhonemizer` + `map_token` を使用 |
| `test_quality_tiny.py` | AST検査 + `model.infer()` 公開API — 修正済み |

---

## 推奨修正の優先順位

### P0: 壊れたテストの修正
- `test_phonemizer_registry.py` の4テスト — AttributeError で即座に失敗

### P1: 本番コードのリファクタリング + テスト書き換え
以下の本番関数を抽出し、テストから import できるようにする:

| 抽出元 | 抽出する関数 | 影響テスト数 |
|--------|-------------|------------|
| `export_onnx.py` (`main()` 内クロージャ) | `build_infer_forward(model_g, stochastic)` | conftest.py (3 fixture) |
| `export_onnx.py` (`main()` 内) | `apply_ema_weights(model_dec, ema_state)` | test_export_onnx.py (1) |
| `__main__.py` | `apply_transfer_defaults(args, dict_args)` | test_multispeaker_transfer.py (6), test_model_config.py (3) |
| `lightning.py` | `_normalize_speaker_id(raw_sid)` | test_freeze_dp.py (1) |
| `infer_onnx.py` (`main()` 内) | `resolve_config_path(model, config)` | test_infer_onnx_config.py (4) |
| `infer_onnx.py` (`main()` 内) | `resolve_speaker_id(speaker_id, has_sid)` | test_multilingual_inference.py (3) |

### P2: テストの書き換え (本番コード変更不要)
- `test_vits.py`, `test_wavlm_discriminator.py`: `WavLMDiscriminator` インスタンスから直接呼び出し
- `test_performance.py`: `phonemize_japanese()` をモジュールレベルに統合
- `test_intersperse_padding.py`: `commons.intersperse()` の出力と比較
- `test_integration.py`: 無意味なテスト2件を削除または書き換え
- `test_convert_fp16.py`: 本番 `_create_dummy_inputs()` を import

### P3: 軽微 (対応任意)
- `test_swedish_phonemizer.py`, `test_token_mapper_impl.py`, `test_prosody_extraction.py` の LOW 問題
