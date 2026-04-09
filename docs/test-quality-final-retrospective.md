# テスト品質監査 最終レトロスペクティブ (M0-M3 完了)

作成日: 2026-04-09

---

## 1. 達成した成果

監査で指摘された 18 件すべてが対処済み。

| マイルストーン | 件数 | 主な成果 |
|--------------|------|---------|
| **M0 (壊れたテスト)** | 2 | `test_phonemizer_registry.py` の 4 テストが `AttributeError` で即死する問題を修正。`get_phoneme_id_map()` / `post_process_ids()` を正しい本番 API 経由に書き換え |
| **M1 (本番関数抽出)** | 6 | 6 つの関数を `main()` 内クロージャ/インラインから独立関数に抽出。テストが本番コードを直接 import する構造に転換 |
| **M2 (テスト書き換え)** | 7 | WavLM resampler を本番インスタンス経由に統一、`_phonemize_japanese` 4 重コピペ解消、`intersperse` ラウンドトリップ検証化、自己テスト削除、FP16 テストを本番 `_create_dummy_inputs` に委譲、無意味なテスト 2 件削除 |
| **M3 (軽微改善)** | 3 | `_split_ipa_to_phonemes` docstring 修正 (Option B)、`map_sequence` 1 行ラッパー削除・インライン化、BOS/EOS ラッパーに差異の根拠を明記し統合は保留 |

**数値まとめ**:

- 本番コードのコピペ再実装テスト: **13 件 -> 0 件** (M1: 6 + M2: 7)
- 壊れたテスト: **4 テスト -> 0**
- 無意味なテスト: **2 テスト -> 削除済**
- 抽出した公開関数: `build_infer_forward`, `apply_ema_weights`, `apply_transfer_defaults`, `normalize_id_tensor`, `resolve_config_path`, `resolve_speaker_id`
- conftest.py の `infer_forward` 再実装行数: **約 140 行 -> thin wrapper 約 15 行** (コアロジックは本番 import)

---

## 2. 残存する設計負債

### 2.1 main() の肥大化

`export_onnx.py` の `main()` と `infer_onnx.py` の `main()` は依然として 200-400 行。M1 で 6 関数を抽出したが、以下が main() 内に残る:

- `infer_onnx.py`: sid/lid/prosody_features の inputs 辞書構築ループ (約 100 行)
- `export_onnx.py`: FP16 変換、simplify、emb_lang 統一のオーケストレーション
- `__main__.py`: データセット読み込み、モデル作成、学習ループ設定の直列フロー

### 2.2 テストヘルパーの BOS/EOS 非統一

M3-3 で明らかになった `test_prosody_extraction.py` と `test_phonemize.py` の EOS 処理差異は、根拠を明記して保留とした。本番コードに `wrap_with_bos_eos()` が存在しない限り、テスト側で重複が残り続ける。

### 2.3 WavLM 初期化コスト

M2-1/M2-2 で WavLMDiscriminator をインスタンス化するテストが増えた。conftest.py の `mock_wavlm_discriminator` (session スコープ) で WavLM 本体を mock しているが、テストファイル間でのフィクスチャ共有は不完全。

### 2.4 `args` 直接変更の副作用パターン

`apply_transfer_defaults(args, dict_args, ...)` は `args` を in-place で変更する副作用関数。M1-3 チケットで指摘された通り、純粋関数 (`compute_transfer_defaults() -> dict`) への転換が望ましいが未実施。

---

## 3. M0-M3 全体を一から作り直すとしたら

### 3.1 テストスイート設計原則

- **命名**: `test_<関数名>_<条件>_<期待>` で統一。ファイル名はテスト対象モジュールと 1:1 対応
- **配置**: テンソルユーティリティは `vits/tensor_utils.py`、config 解決は `config_utils.py` に分離し、テスト時の重い import を回避
- **fixture**: `make_onnx_fixture(model_factory, stochastic, multilingual)` メタフィクスチャで conftest を 3-5 行/fixture に圧縮。WavLM resampler は `scope="session"` + mock で 1 回初期化
- **テーブル駆動**: `@pytest.mark.parametrize` を原則とし、Case 1/2/3 の列挙コピペを排除

### 3.2 本番コードのテスト容易性

- **main() は薄く**: 引数パース + 関数呼び出しの連鎖のみ。`ExportContext` dataclass で状態を受け渡すパイプライン設計
- **純粋関数化**: `compute_transfer_defaults(...) -> dict` のように入出力変換として設計。`args` 直接変更を廃止
- **I/O 分離**: `load_ema_state(path) -> dict` + `apply_ema_shadow_params(decoder, shadow_params) -> (int, int)` の 2 関数構成。`SynthesizerTrn.infer()` メソッドで `build_infer_forward` を不要にする

### 3.3 理想のモジュール構造

```
piper_train/
  config_utils.py       # resolve_config_path, validate_config
  transfer_utils.py     # compute_transfer_defaults (純粋関数)
  export_utils.py       # build_infer_forward, apply_ema_weights, OnnxExportHelper
  ort_utils.py          # create_dummy_inputs (FP16/warmup/テスト共通)
  vits/
    tensor_utils.py     # normalize_id_tensor
    models.py           # SynthesizerTrn.infer() メソッド追加
```

### 3.4 CI/CD ガードレール

- **コピペ lint**: テストファイル内の `def` が本番モジュールの同名関数と重複していないか静的チェック
- **import ガード**: テストファイルが本番コードを 0 行も import していない場合は CI fail
- **コピペ本番ロジック箇所数を 0 に維持** するメトリクスを CI に組み込む

---

## 4. 次のアクション (優先順位順)

1. **`SynthesizerTrn.infer()` メソッド追加** -- `build_infer_forward()` を不要にする根本解決。conftest fixture がさらに簡素化される
2. **`build_onnx_inputs()` 抽出** (infer_onnx.py) -- sid/lid/prosody 解決を一括テスト可能にし、main() の 100 行ループを 1 行に
3. **BOS/EOS ユーティリティの本番化** -- `piper/phonemize/` に `wrap_with_bos_eos()` を追加し、テスト側の重複ラッパーを解消
4. **`apply_transfer_defaults` の純粋関数化** -- `compute_transfer_defaults() -> dict` に転換
5. **CI lint 導入** -- テスト内コピペ検出の自動化
6. **`pytest-benchmark` 導入** -- `test_performance.py` の手動 `time.perf_counter()` を置換
