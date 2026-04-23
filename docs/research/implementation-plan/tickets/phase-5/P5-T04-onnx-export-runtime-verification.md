# P5-T04: ONNX エクスポート + 6 ランタイム動作確認

| 項目 | 値 |
|------|-----|
| Phase | 5 |
| マイルストーン | [#15](https://github.com/ayutaz/piper-plus/milestone/15) |
| ステータス | スクリプト準備完了 (実 runtime 起動は学習済モデル到着後の別セッション) |
| 優先度 | 高 |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P5-T02 (Stage 5a 学習完了), Phase 2 全タスク (ONNX エクスポート + 6 ランタイム style_vector 統合) |
| 後続チケット | P5-T05 |
| 関連 PR | PR-G |
| 期日 | 2026-05-08 |

## 1. タスク目的とゴール

### 1.1 目的

Stage 5a の best ckpt (P5-T02 成果物) を `export_onnx.py --style-vector-dim 256` で ONNX 化し、6 ランタイム (Python / C++ / Rust / C# / Go / WASM) で同一の `style_vector` 入力を与えた場合に同一音声が出力されることを確認する。Phase 2 で整備された `speaker_embedding` と同じ mask パターンで style_vector 入力が追加されている前提。

合わせて、HuggingFace Hub (`ayousanz/piper-plus-crema-d-emotion`) へのモデルアップロード (optional) を行い、コミュニティから利用可能にする。

### 1.2 ゴール (Definition of Done)

- [ ] `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx` が生成されている
- [ ] `onnx.load` でロード可能、`get_inputs()` に `style_vector` + `style_vector_mask` が含まれている
- [ ] `config.json` の `style_vector_dim=256`, `style_condition_mode="global"` が metadata_props に書き込まれている
- [ ] Python ランタイム (`infer_onnx.py --style-vector <path>`) で合成成功
- [ ] C++ ランタイム (`piper_plus` CLI with `--style-vector`) で合成成功
- [ ] Rust ランタイム (`piper-plus-cli --style-vector`) で合成成功
- [ ] C# ランタイム (`PiperPlus.Cli --style-vector`) で合成成功
- [ ] Go ランタイム (`piper-plus --style-vector`) で合成成功
- [ ] WASM ランタイム (`piper-plus` npm、テスト HTML で動作確認) で合成成功
- [ ] 6 ランタイムで同一 style_vector (例: `happy_centroid.npy`) + 同一テキスト + 同一 speaker_id での出力 WAV が byte-for-byte 一致 or 音響的に同等 (MD5 比較 or MEL spectrogram 目視)
- [ ] HuggingFace Hub `ayousanz/piper-plus-crema-d-emotion` にアップロード (optional、ユーザー判断)

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx` (新規、export 成果物)
- `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx.json` (config.json コピー)
- `docs/research/reports/phase-5-runtime-verification.md` (新規、6 ランタイム結果サマリ)
- HuggingFace Hub `ayousanz/piper-plus-crema-d-emotion` (optional)

### 2.2 実装手順

1. **ONNX エクスポート**:
    ```bash
    CUDA_VISIBLE_DEVICES="" uv run python -m piper_train.export_onnx \
      /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt \
      /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx
    ```
    - `--style-vector-dim` は hparams から自動取得 (Phase 2 実装により)
    - FP16 変換は既定 ON (`--no-fp16` で off)
2. **config.json コピー**:
    ```bash
    cp /data/piper/dataset-crema-d-emotion/config.json \
       /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx.json
    ```
3. **ONNX 構造確認**:
    ```python
    import onnx
    model = onnx.load("/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx")
    print([i.name for i in model.graph.input])
    # ['input', 'input_lengths', 'scales', 'sid', 'lid', 'speaker_embedding', 'speaker_embedding_mask', 'style_vector', 'style_vector_mask']
    print(dict((p.key, p.value) for p in model.metadata_props))
    # {'style_vector_dim': '256', 'style_condition_mode': 'global', ...}
    ```
4. **Python ランタイム確認**:
    ```bash
    uv run python -m piper_train.infer_onnx \
      --model /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx \
      --config /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx.json \
      --text "I wonder what this is about." \
      --language ja-en-zh-es-fr-pt \
      --speaker-id 0 \
      --style-vector /data/piper/style_bank_crema_d/happy_centroid.npy \
      --output-dir /tmp/runtime_test/python
    ```
5. **C++ ランタイム**:
    ```bash
    cmake --build build && \
    ./build/piper_plus \
      --model crema-d-finetune-v1.onnx \
      --config crema-d-finetune-v1.onnx.json \
      --text "I wonder what this is about." \
      --style-vector happy_centroid.npy \
      --output /tmp/runtime_test/cpp.wav
    ```
6. **Rust ランタイム**:
    ```bash
    cargo run --release -p piper-plus-cli -- \
      --model crema-d-finetune-v1.onnx \
      --config crema-d-finetune-v1.onnx.json \
      --text "I wonder what this is about." \
      --style-vector happy_centroid.npy \
      --output /tmp/runtime_test/rust.wav
    ```
7. **C# ランタイム**:
    ```bash
    dotnet run --project src/csharp/PiperPlus.Cli -- \
      --model crema-d-finetune-v1.onnx \
      --config crema-d-finetune-v1.onnx.json \
      --text "I wonder what this is about." \
      --style-vector happy_centroid.npy \
      --output /tmp/runtime_test/csharp.wav
    ```
8. **Go ランタイム**:
    ```bash
    cd src/go && go run ./cmd/piper-plus \
      --model crema-d-finetune-v1.onnx \
      --config crema-d-finetune-v1.onnx.json \
      --text "I wonder what this is about." \
      --style-vector happy_centroid.npy \
      --output /tmp/runtime_test/go.wav
    ```
9. **WASM ランタイム**:
    - `src/wasm/openjtalk-web/test/browser/test-style-vector.html` (新規 or 既存) でテスト
    - モデルを HuggingFace Hub にアップロード後、`piper-plus` npm パッケージ経由で動作確認
    - または Node.js test runner で style_vector 入力を ONNX に渡し WAV 出力
10. **クロスランタイム同一性検証**:
    ```bash
    md5sum /tmp/runtime_test/{python,cpp,rust,csharp,go}.wav
    # 5 ランタイムで MD5 が一致 (WASM は浮動小数精度差で異なる可能性あり、その場合は MEL spectrogram 相関で 0.95+ を確認)
    ```
11. **HuggingFace Hub アップロード (optional)**:
    ```bash
    huggingface-cli login
    huggingface-cli upload ayousanz/piper-plus-crema-d-emotion \
      /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx \
      crema-d-finetune-v1.onnx
    huggingface-cli upload ayousanz/piper-plus-crema-d-emotion \
      /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx.json \
      crema-d-finetune-v1.onnx.json
    huggingface-cli upload ayousanz/piper-plus-crema-d-emotion \
      /data/piper/style_bank_crema_d.npz \
      style_bank_crema_d.npz
    ```
12. **レポート生成**: `docs/research/reports/phase-5-runtime-verification.md` に 6 ランタイムの結果表を記載

### 2.3 検証結果レポート テンプレート

```markdown
# Phase 5 ランタイム検証レポート

## ONNX Export 情報

- 入力: /data/piper/output-emotion-fine-tune-v1/lightning_logs/version_0/checkpoints/best.ckpt
- 出力: /data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx
- サイズ: XX MB (FP16)
- 入力 テンソル: ['input', 'input_lengths', 'scales', 'sid', 'lid', 'speaker_embedding', 'speaker_embedding_mask', 'style_vector', 'style_vector_mask']
- metadata_props: style_vector_dim=256, style_condition_mode=global

## 6 ランタイム動作結果

| ランタイム | 動作 | 出力 WAV | MD5 | 音響的一致 |
|-----------|------|---------|-----|----------|
| Python    | ○    | python.wav | abc123... | baseline |
| C++       | ○    | cpp.wav    | abc123... | ○ (MD5 一致) |
| Rust      | ○    | rust.wav   | abc123... | ○ (MD5 一致) |
| C#        | ○    | csharp.wav | abc123... | ○ (MD5 一致) |
| Go        | ○    | go.wav     | abc124... | △ (浮動小数精度差、MEL spec 相関 0.98) |
| WASM      | ○    | wasm.wav   | abc125... | △ (WebGL 演算差、MEL spec 相関 0.95) |

## 使用 style_vector

- source: /data/piper/style_bank_crema_d/happy_centroid.npy
- shape: (256,)
- L2 norm: 1.0000
```

## 3. エージェントチーム構成

| 役割 | 人数 | 主な責務 |
|------|------|---------|
| Exporter | 1 | `export_onnx.py` 実行、ONNX 構造確認 (onnx.load)、config.json コピー |
| Runtime Verifier | 1 | 6 ランタイム (Python/C++/Rust/C#/Go/WASM) の CLI 実行、出力 WAV 保存、MD5 照合 |
| Hub Uploader | 1 (optional) | HuggingFace Hub へのアップロード、README 整備 |

## 4. 提供範囲 (Deliverables)

- [ ] `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx`
- [ ] `/data/piper/output-emotion-fine-tune-v1/crema-d-finetune-v1.onnx.json`
- [ ] `docs/research/reports/phase-5-runtime-verification.md` (6 ランタイム結果表)
- [ ] `/tmp/runtime_test/` or `/data/piper/evaluation/runtime_test/` (6 ランタイムの出力 WAV)
- [ ] HuggingFace Hub `ayousanz/piper-plus-crema-d-emotion` (optional)

**提供範囲外**:
- モデル評価 (P5-T03)
- 最終レポート (P5-T05)
- CI による自動ランタイム検証 (将来課題)

## 5. テスト項目

### 5.1 Unit テスト

- 該当なし (Phase 2 で 6 ランタイムの style_vector 統合テストは実装済み)
- 本チケットは実モデルでの動作確認のため integration レベル

### 5.2 E2E テスト

- ONNX 生成: `onnx.load()` で exception なく読める
- 6 ランタイム: 各 CLI が exit code 0 で完了、出力 WAV が `> 0 bytes`
- クロスランタイム一致: Python/C++/Rust/C#/Go 5 言語で MD5 一致 (WASM は 95% MEL 相関許容)
- style_vector 切替テスト: `happy_centroid.npy` と `sad_centroid.npy` を切り替えて異なる音声が出ることを確認
- style_vector=None (zeros) 互換: style_vector_mask=0 で合成した音声がベース 6lang モデルとほぼ同等 (MEL 相関 0.99+)

### 5.3 人間評価 (optional)

- 各ランタイムの出力 WAV を聴き比べ、品質差がないことを確認
- HuggingFace Hub 公開後、コミュニティからのフィードバック収集

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **Phase 2 の 6 ランタイム style_vector 統合が未完了の場合**: Phase 2 T02〜T07 のいずれかが incomplete だと本チケットが着手不能。T04 着手前に Phase 2 の完了を確認
- **FP16 変換による品質劣化**: FP16 ONNX で style_vector 条件付けが失われる可能性。`--no-fp16` でも試行し、FP32 と FP16 の差分を確認
- **クロスランタイム MD5 不一致**: 浮動小数演算順序差で MD5 が一致しないケースあり。WASM は WebGL 演算差で特に影響大。対策: MEL spectrogram 相関 0.95+ を代替基準に
- **HuggingFace Hub アップロード権限**: `ayousanz/piper-plus-crema-d-emotion` リポジトリが未作成の場合、事前に HF Hub 上で手動作成が必要
- **CREMA-D ライセンス (ODbL) の HuggingFace Hub 上での表記**: ODbL の帰属表示要件 (`attribution` + `share-alike`) を README.md に明記する必要あり
- **Phase 4 が完了している前提で Stage 5b も ONNX 化する**: Stage 5a のみで Phase 5 を進める場合は 5b ONNX は不要。P5-T03 評価結果次第で判断
- **WASM ランタイムのモデルキャッシュ**: IndexedDB 経由のキャッシュを考慮し、テスト時は初回ロード時間 (数秒〜) を許容。2 回目以降は高速

### 6.2 レビュー項目

- [ ] ONNX モデルの入力名が `style_vector` + `style_vector_mask` で Phase 2 の合意仕様と一致
- [ ] metadata_props の `style_vector_dim` / `style_condition_mode` が string で書き込まれている
- [ ] 6 ランタイム全てで CLI が `--style-vector <npy_path>` を受理 (argparse / clap / CommandLineParser 等)
- [ ] 5 ランタイム (Python/C++/Rust/C#/Go) で MD5 一致 (WASM は相関 0.95+)
- [ ] style_vector=None / zeros vs style_vector=happy_centroid で明らかに異なる音声が出る
- [ ] FP16 変換後も感情差が保たれている (MEL spec で目視確認)
- [ ] HuggingFace Hub README に ODbL 帰属表示と CREMA-D 出典が明記 (公開する場合)

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A: ONNX Optional 型 (opset 15+) で style_vector 入力を optional 化**
    - 利点: mask パターン不要、入力の有無を API で表現可能
    - 欠点: Phase 2 で mask パターン採択済み、各ランタイムの Optional サポートが未成熟
- **代替案 B: FP32 ONNX のみで公開 (FP16 変換スキップ)**
    - 利点: 音質劣化リスクゼロ、クロスランタイム MD5 一致が容易
    - 欠点: モデルサイズ 2 倍 (~150MB)、推論速度若干低下
- **代替案 C: 6 ランタイム検証を CI で自動化**
    - 利点: リリースごとの regression check、手動検証工数ゼロ
    - 欠点: CI インフラ整備工数大 (6 言語 × 3 OS = 18 combination)、本チケット期日内に無理
- **代替案 D: HuggingFace Hub の代わりに GitHub Release でモデル配布**
    - 利点: リポジトリと配布が一元化、コントリビューターに見つけやすい
    - 欠点: Git LFS の帯域制限 (1GB/月)、大容量モデルに不向き

### 7.2 現在の実装を選んだ理由

- Phase 2 で確立された mask パターン + 6 ランタイム統合のテンプレートに完全準拠、新規実装は最小限
- クロスランタイム検証を MD5 で自動化し、工数を 2〜3h に抑える
- HuggingFace Hub は既存モデル配布先 (`ayousanz/piper-plus-base`, `ayousanz/piper-plus-tsukuyomi-chan`) と統一

### 7.3 リファクタ機会 (将来)

- 6 ランタイム検証スクリプトを `scripts/verify_runtime_parity.sh` にラップし、引数 1 つ (モデル path) で全ランタイム実行
- ONNX metadata 自動検証 (`style_vector_dim` が config.json と一致) を export_onnx.py 内で assert
- WASM の浮動小数精度差を吸収する専用 MEL 相関テストを `test/js/test-runtime-parity.js` に実装
- HuggingFace Hub アップロードを GitHub Actions で自動化 (タグ付きリリース時に自動 upload)

## 8. 後続タスクへの連絡事項

- **P5-T05 へ**: `crema-d-finetune-v1.onnx` のパス、HuggingFace Hub URL、6 ランタイム検証結果を最終レポートに統合
- **CLAUDE.md 更新**: `つくよみちゃん 6lang-v2` と同じパターンで CREMA-D モデル情報を追記 (P5-T05 担当)
- **Phase 2 回帰テスト**: 本チケット実施中に 6 ランタイムの style_vector 処理で不具合が見つかった場合、Phase 2 の該当チケットに逆提案 (issue or PR)

## 9. 参考リンク

- `phase-2.md` ONNX エクスポート + 6 ランタイム統合
- CLAUDE.md 「ONNX変換」セクション
- CLAUDE.md 「HuggingFaceリソース」セクション
- CLAUDE.md 「全ランタイム Voice Cloning 統合」 (speaker_embedding の 6 ランタイム統合先例)
- HuggingFace Hub: https://huggingface.co/ayousanz
- CREMA-D ライセンス (ODbL): https://opendatacommons.org/licenses/odbl/
- Phase 2 T02〜T07 の 6 ランタイムチケット (未作成、存在すれば参照)
