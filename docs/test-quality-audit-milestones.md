# テスト品質監査 — マイルストーン

参照: `docs/test-quality-audit-2026-04.md`
ブランチ: `fix/test-quality-audit`
チケット: `docs/tickets/`

---

## M0: 壊れたテストの修正 (ブロッカー)

他の全作業の前提。AttributeError で即座に失敗するテストを修正する。

| # | チケット | ファイル | 作業内容 | 並行可 |
|---|---------|---------|---------|:------:|
| M0-1 | [M0-1](tickets/M0-1.md) | `test_phonemizer_registry.py` | 存在しない `p.get_phoneme_id_map()` → `get_phoneme_id_map()` スタンドアロン関数に書き換え (L79-88) | - |
| M0-2 | [M0-2](tickets/M0-2.md) | `test_phonemizer_registry.py` | 存在しない `p.post_process_ids()` → `PiperEncoder.encode()` に書き換え (L91-118) | - |

---

## M1: 本番コードから関数を抽出 + テスト書き換え

`main()` 内クロージャや if 分岐を独立関数に抽出し、テストから import する。各タスクは独立して並行作業可能。

| # | チケット | 抽出元 | 抽出する関数 | 影響テスト | 並行可 |
|---|---------|--------|-------------|-----------|:------:|
| M1-1 | [M1-1](tickets/M1-1.md) | `export_onnx.py` (L278-331) | `build_infer_forward(model_g, stochastic)` | `conftest.py` 3 fixture (L117, L217, L365) | Yes |
| M1-2 | [M1-2](tickets/M1-2.md) | `export_onnx.py` (L248-265) | `apply_ema_weights(model_dec, ema_state)` | `test_export_onnx.py` (L142-154) | Yes |
| M1-3 | [M1-3](tickets/M1-3.md) | `__main__.py` (L430-443) | `apply_transfer_defaults(args, dict_args, num_speakers, num_languages)` | `test_multispeaker_transfer.py` 全6テスト, `test_model_config.py` gin_channels 3テスト | Yes |
| M1-4 | [M1-4](tickets/M1-4.md) | `lightning.py` (L706-717) | `_normalize_id(raw_id)` | `test_freeze_dp.py` (L108-167) | Yes |
| M1-5 | [M1-5](tickets/M1-5.md) | `infer_onnx.py` (L311-320) | `resolve_config_path(model, config)` | `test_infer_onnx_config.py` 全4テスト | Yes |
| M1-6 | [M1-6](tickets/M1-6.md) | `infer_onnx.py` (L397-411) | `resolve_speaker_id(speaker_id, has_sid)` | `test_multilingual_inference.py` (L370-417) | Yes |

---

## M2: テスト書き換え (本番コード変更不要)

テスト側のみの修正。各タスクは独立して並行作業可能。

| # | チケット | ファイル | 作業内容 | 並行可 |
|---|---------|---------|---------|:------:|
| M2-1 | [M2-1](tickets/M2-1.md) | `test_vits.py` (L114-134) | `torchaudio.functional.resample()` → `WavLMDiscriminator` インスタンスの `_resample()` を呼ぶ | Yes |
| M2-2 | [M2-2](tickets/M2-2.md) | `test_wavlm_discriminator.py` (L103-110) | `resampler_sinc` fixture → `WavLMDiscriminator.resampler` を参照 | Yes |
| M2-3 | [M2-3](tickets/M2-3.md) | `test_performance.py` (L32, L84, L131, L203) | `phonemize_japanese()` 4重コピペ → モジュールレベルのヘルパーに統合 | Yes |
| M2-4 | [M2-4](tickets/M2-4.md) | `test_intersperse_padding.py` (L45-77) | `has_intersperse_padding()` 再実装 → `commons.intersperse()` の出力と比較 | Yes |
| M2-5 | [M2-5](tickets/M2-5.md) | `test_prosody_extraction.py` (L550-574) | `validate_dataset_prosody()` 自己テスト → 本番に抽出するか削除 | Yes |
| M2-6 | [M2-6](tickets/M2-6.md) | `test_convert_fp16.py` (L14-42) | `_onnx_inference()` → 本番 `_create_dummy_inputs()` を import | Yes |
| M2-7 | [M2-7](tickets/M2-7.md) | `test_integration.py` (L30-85) | 無意味なテスト2件 (`test_model_config_validation`, `test_wav_file_generation`) → 本番コードを呼ぶか削除 | Yes |

---

## M3: 軽微な改善 (対応任意)

| # | チケット | ファイル | 作業内容 | 並行可 |
|---|---------|---------|---------|:------:|
| M3-1 | [M3-1](tickets/M3-1.md) | `test_swedish_phonemizer.py` (L28-46) | `_split_ipa_to_phonemes()` 旧API関数のテスト用コピー整理 | Yes |
| M3-2 | [M3-2](tickets/M3-2.md) | `test_token_mapper_impl.py` (L16-18) | `map_sequence()` 1行ラッパー → インライン化 | Yes |
| M3-3 | [M3-3](tickets/M3-3.md) | `test_prosody_extraction.py` (L18-38) | BOS/EOS ラッパー → 共通ユーティリティ抽出を検討 | Yes |

---

## エージェント割り当てガイド

### 推奨並行構成 (6エージェント)

```
Agent 1: M0-1 + M0-2 (ブロッカー、最初に完了させる)
Agent 2: M1-1 (conftest.py 最大の変更)
Agent 3: M1-3 (test_multispeaker_transfer + test_model_config、影響最大)
Agent 4: M1-2 + M1-4 (小規模抽出2件)
Agent 5: M1-5 + M1-6 (infer_onnx.py 2件)
Agent 6: M2-1 〜 M2-7 (テスト側のみ、本番コード変更なし)
```

### 依存関係

```
M0 → M1, M2, M3  (M0 が全てのブロッカー)
M1-1 → なし      (conftest.py は他テストの fixture だが、既存テストは壊れない)
M1-3 → なし      (gin_channels テストは独立)
M2-* → なし      (全て独立、本番コード変更なし)
```

### 完了条件
- 全既存テスト (`pytest tests/ -m "unit"`) がパス
- 修正したテストが本番コードを直接 import/呼び出ししている
- テスト内にコピペされた本番ロジックが残っていない
