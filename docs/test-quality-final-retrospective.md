# テスト品質監査 最終レトロスペクティブ (M0-M3 + レトロスペクティブ修正完了)

作成日: 2026-04-09

---

## 1. 達成した成果

監査で指摘された 18 件 + レトロスペクティブで追加発見した 8 件、計 26 件すべてが対処済み。

| マイルストーン | 件数 | 主な成果 |
|--------------|------|---------|
| **M0 (壊れたテスト)** | 2 | `test_phonemizer_registry.py` の 4 テストが `AttributeError` で即死する問題を修正。`get_phoneme_id_map()` / `post_process_ids()` を正しい本番 API 経由に書き換え |
| **M1 (本番関数抽出)** | 6 | 6 つの関数を `main()` 内クロージャ/インラインから独立関数に抽出。テストが本番コードを直接 import する構造に転換 |
| **M2 (テスト書き換え)** | 7 | WavLM resampler を本番インスタンス経由に統一、`_phonemize_japanese` 4 重コピペ解消、`intersperse` ラウンドトリップ検証化、自己テスト削除、FP16 テストを本番 `_create_dummy_inputs` に委譲、無意味なテスト 2 件削除 |
| **M3 (軽微改善)** | 3 | `_split_ipa_to_phonemes` docstring 修正 (Option B)、`map_sequence` 1 行ラッパー削除・インライン化、BOS/EOS ラッパーに差異の根拠を明記し統合は保留 |
| **レトロスペクティブ修正** | 8 | 下記詳細 |

### レトロスペクティブ修正の詳細

| 修正 | ファイル | 内容 |
|------|---------|------|
| `build_infer_forward` thin wrapper 化 | `export_onnx.py` | コアロジックを `SynthesizerTrn.infer()` に移動。`build_infer_forward` は scales 分解 + `onnx_export_mode` 管理のみの薄いラッパーに |
| `apply_ema_shadow_params` 抽出 | `export_onnx.py` | EMA パラメータ適用の I/O 分離。`apply_ema_weights` (ファイル読み込み + 委譲) と `apply_ema_shadow_params` (純粋ロジック) の 2 関数構成 |
| `load_multispeaker_checkpoint` 抽出 | `__main__.py` | マルチスピーカーチェックポイント読み込みロジックを `main()` から独立関数に抽出 |
| DSP dead code 削除 | `infer_onnx.py` | 使用されていない DSP 関連コードを削除 |
| `phonemize_japanese` conftest 集約 | `conftest.py` | 5 ファイルに重複していた日本語音素化ヘルパーを `conftest.py` の `phonemize_japanese()` に統合。`auto_eos` パラメータで 2 種の EOS 挙動を切替 |
| `mock_wavlm_discriminator` 共有 fixture | `conftest.py` | `scope="session"` の WavLM mock fixture を conftest に配置。`WavLMModel.from_pretrained` を patch し ~300MB ダウンロードを回避 |
| `normalize_id_tensor` 公開 + parametrize | `lightning.py`, `test_freeze_dp.py` | `_normalize_id` を `normalize_id_tensor` にリネームし公開 API に。テストは `@pytest.mark.parametrize` で int/1D-Tensor/0D-Tensor/None の 4 ケースをテーブル駆動化 |
| `test_speaker_embedding.py` 5-tuple 修正 | `test_speaker_embedding.py` | `SynthesizerTrn.infer()` が durations を含む 5-tuple を返すようになったことに合わせ、全 unpack を `o, attn, y_mask, _, _` に修正 |
| pytest markers 追加 | `test_intersperse_padding.py`, `test_wavlm_discriminator.py` | `@pytest.mark.unit` / `@pytest.mark.training` を追加 |
| placeholder テスト削除 | `test_integration.py` | 実装のない placeholder テストを削除。実質的な 4 テストのみ残存 |

**数値まとめ**:

- 本番コードのコピペ再実装テスト: **13 件 -> 0 件** (M1: 6 + M2: 7)
- 壊れたテスト: **4 テスト -> 0**
- 無意味なテスト: **2 テスト -> 削除済**
- 抽出した公開関数: `build_infer_forward`, `apply_ema_weights`, `apply_ema_shadow_params`, `apply_transfer_defaults`, `load_multispeaker_checkpoint`, `normalize_id_tensor`, `resolve_config_path`, `resolve_speaker_id` (計 8 関数)
- conftest.py の `infer_forward` 再実装行数: **約 140 行 -> thin wrapper 約 15 行** (コアロジックは `model.infer()` に移動)
- conftest.py 共有ヘルパー: `phonemize_japanese`, `phonemize_japanese_with_prosody`, `mock_wavlm_discriminator`, `build_infer_forward` import

---

## 2. 残存する設計負債

### 2.1 main() の肥大化

`export_onnx.py` の `main()` と `infer_onnx.py` の `main()` は依然として 200-400 行。M1 で 6 関数 + レトロスペクティブで 2 関数を抽出したが、以下が main() 内に残る:

- `infer_onnx.py`: sid/lid/prosody_features の inputs 辞書構築ループ (約 100 行)
- `export_onnx.py`: FP16 変換、simplify、emb_lang 統一のオーケストレーション
- `__main__.py`: データセット読み込み、モデル作成、学習ループ設定の直列フロー

### 2.2 テストヘルパーの BOS/EOS 非統一

M3-3 で明らかになった `test_prosody_extraction.py` と `test_phonemize.py` の EOS 処理差異は、根拠を明記して保留とした。本番コードに `wrap_with_bos_eos()` が存在しない限り、テスト側で重複が残り続ける。conftest.py の `auto_eos` パラメータで 2 種の挙動を集約済みだが、根本解決には本番側の API 追加が必要。

### 2.3 `apply_transfer_defaults` の args in-place 変更

`apply_transfer_defaults(args, num_speakers, num_languages)` は `args` を in-place で変更する副作用関数。`dict_args` パラメータは除去済みだが、純粋関数 (`compute_transfer_defaults() -> dict`) への転換は未実施。

---

## 3. M0-M3 全体を一から作り直すとしたら

### 3.1 テストスイート設計原則

- **命名**: `test_<関数名>_<条件>_<期待>` で統一。ファイル名はテスト対象モジュールと 1:1 対応
- **配置**: `normalize_id_tensor` は `lightning.py` のモジュールレベル公開関数として配置済み。config 解決は `infer_onnx.py` に分離済み
- **fixture**: `mock_wavlm_discriminator` (session scope) + `phonemize_japanese` 共有ヘルパーで conftest.py を集約済み。ONNX fixture は `build_infer_forward` を import して構築
- **テーブル駆動**: `@pytest.mark.parametrize` を原則とし、Case 1/2/3 の列挙コピペを排除 (`test_speaker_id_tensor_handling` で実践済み)

### 3.2 本番コードのテスト容易性

- **main() は薄く**: 引数パース + 関数呼び出しの連鎖のみ。`ExportContext` dataclass で状態を受け渡すパイプライン設計
- **純粋関数化**: `compute_transfer_defaults(...) -> dict` のように入出力変換として設計。`args` 直接変更を廃止
- **I/O 分離**: `apply_ema_weights(decoder, path)` + `apply_ema_shadow_params(decoder, shadow_params)` の 2 関数構成で実現済み
- **モデル API**: `SynthesizerTrn.infer()` が durations 含む 5-tuple を返し、`build_infer_forward` は thin wrapper に簡素化済み

### 3.3 実現済みモジュール構造

```
piper_train/
  __main__.py             # apply_transfer_defaults, load_multispeaker_checkpoint 抽出済み
  export_onnx.py          # build_infer_forward (thin wrapper), apply_ema_weights,
                          #   apply_ema_shadow_params, should_unify_emb_lang,
                          #   unify_emb_lang_weights 抽出済み
  infer_onnx.py           # resolve_config_path, resolve_speaker_id 抽出済み。DSP dead code 削除済み
  ort_utils.py            # create_dummy_inputs (FP16/warmup/テスト共通)
  vits/
    lightning.py          # normalize_id_tensor (公開 API)
    models.py             # SynthesizerTrn.infer() -- durations 含む 5-tuple を返す
```

### 3.4 CI/CD ガードレール

- **コピペ lint**: テストファイル内の `def` が本番モジュールの同名関数と重複していないか静的チェック
- **import ガード**: テストファイルが本番コードを 0 行も import していない場合は CI fail
- **コピペ本番ロジック箇所数を 0 に維持** するメトリクスを CI に組み込む

---

## 4. 次のアクション (優先順位順)

1. **`build_onnx_inputs()` 抽出** (infer_onnx.py) -- sid/lid/prosody 解決を一括テスト可能にし、main() の 100 行ループを 1 行に
2. **BOS/EOS ユーティリティの本番化** -- `piper/phonemize/` に `wrap_with_bos_eos()` を追加し、テスト側の重複ラッパーを解消
3. **`apply_transfer_defaults` の純粋関数化** -- `compute_transfer_defaults() -> dict` に転換
4. **CI lint 導入** -- テスト内コピペ検出の自動化
5. **`pytest-benchmark` 導入** -- `test_performance.py` の手動 `time.perf_counter()` を置換
