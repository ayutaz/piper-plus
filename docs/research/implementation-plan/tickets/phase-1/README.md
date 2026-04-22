# Phase 1: Style Vector Conditioning 学習側統合

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| 期日 | 2026-04-28 |
| Claude Code 工数目安 | 4〜8h |
| 人間エンジニア参考工数 | 約 1 週間 (21.5h) |
| 依存 | Phase 0 完了 (PE-A PoC、embedding 次元確定) |
| 後続 | Phase 2 (ONNX+ランタイム)、Phase 3 (Style bank)、Phase 4 (PE-A loss) |
| 関連 PR | PR-B |

---

## 概要

Phase 1 では、Fork `yusuke-ai/piper-plus` のコミット `314b3355` を最終形として、Style Vector Conditioning 機能の**学習側コード**を本家に取り込む。PE-A emotion loss 関連コードは **Phase 4 で別途取り込み**とし、本 Phase の責任範囲は以下に限定する:

- `src/python/piper_train/vits/models.py` の TextEncoder / SynthesizerTrn 拡張
- `src/python/piper_train/vits/dataset.py` の Utterance / Batch への style_vector 追加
- `src/python/piper_train/vits/lightning.py` の batch.style_vectors 伝播
- `src/python/piper_train/vits/commons.py` の slice_segments 一般化
- `src/python/piper_train/__main__.py` の CLI オプション 4 個追加 (style 系 3 個 + load_weights_from_checkpoint)
- `src/python/piper_train/infer.py` の style_vector 推論統合
- 11 件の Unit テスト (`tests/test_style_vector_conditioning.py` 8 件 + `tests/test_load_weights_from_checkpoint.py` 3 件)
- CLAUDE.md への新セクション追加 + CI リグレッション確認

**最重要要件**: `--style-vector-dim 0` (default) で既存モデルと bit-for-bit 一致すること (後方互換性)。

---

## チケット一覧

| チケット | タイトル | 優先度 | 工数 | ステータス | 依存 |
|---------|---------|-------|------|---------|------|
| [P1-T01](P1-T01-models-style-vector.md) | models.py に style_vector 層を追加 | 高 | 30分〜1h | 未着手 | P0-T03 |
| [P1-T02](P1-T02-dataset-style-vector.md) | dataset.py に style_vector フィールドを追加 | 高 | 30分〜1h | 未着手 | なし |
| [P1-T03](P1-T03-lightning-commons.md) | lightning.py に style_vector 伝播 + commons.py の slice_segments 一般化 | 高 | 20分 | 未着手 | T01, T02 |
| [P1-T04](P1-T04-main-cli-load-weights.md) | __main__.py に CLI オプション + --load_weights_from_checkpoint (shape-aware) | 高 | 30分〜1h | 未着手 | T01, T02, T03 |
| [P1-T05](P1-T05-infer-style-vector.md) | infer.py に style_vector 推論統合 | 中 | 15〜30分 | 未着手 | T01, T04 |
| [P1-T06](P1-T06-unit-tests.md) | Unit テスト作成 (style_vector 8件 + load_weights 3件) | 高 | 1h | 未着手 | T01〜T05 |
| [P1-T07](P1-T07-docs-ci-regression.md) | CLAUDE.md 更新 + CI リグレッション確認 | 中 | 10分 + CI 待ち | 未着手 | T01〜T06 |

**合計工数**: 3.5〜5.5h (実装) + 1〜3h (CI 待ち) = 4〜8h

---

## 依存関係図

```
[P0-T03 embedding 次元確定]
          │
          ▼
      ┌───┴───┐
      │       │
  ┌──T01──┐  T02              (並行実装可)
  │ models │  dataset
  └───┬───┘  │
      │      │
      └──┬───┘
         ▼
       T03 (lightning + commons)
         │
         ▼
       T04 (main CLI + load_weights)
         │
         ▼
       T05 (infer)
         │
         ▼
       T06 (unit tests)
         │
         ▼
       T07 (docs + CI regression)
         │
         ▼
   [Phase 2 着手]
```

### 順序依存の詳細

- **T01 (models)** と **T02 (dataset)** は互いに独立しているため並行実装可。両方マージ後に T03 着手
- **T03 (lightning+commons)** は T01 の SynthesizerTrn.forward シグネチャ変更、T02 の Batch.style_vectors 追加の両方に依存
- **T04 (main)** は T01-T03 の完了後、CLI → VitsModel hparams → SynthesizerTrn の全体パスが通った時点で実装
- **T05 (infer)** は T01/T04 完了後。PyTorch 側推論のみ (ONNX は Phase 2)
- **T06 (tests)** は T01-T05 の全実装を verify するため最後
- **T07 (docs+CI)** は最終確認、全実装完了後

---

## 一から考えたら

Fork `314b3355` をベースとした実装を前提としているが、ゼロから設計する場合に検討すべき代替案:

### 1. style_vector 注入位置の再検討

**現状 (fork 準拠)**: `style_condition_mode ∈ {"global", "text"}` の 2 択で、どちらか片方のみ動作。

**代替案**:
- **両方同時 (hybrid mode)**: global + text の両方で注入し、dim を分割 (`dim_global = 128, dim_text = 128`)
  - メリット: style の多層性を捉えられる、表現力向上
  - デメリット: ハイパラ増、学習難易度上昇、fork との diff 増
- **speaker embedding のように合流**: emb_g に加算ではなく concat してから Linear 投影
  - メリット: 情報損失が少ない (加算だと埋もれやすい)
  - デメリット: 既存 emb_g shape との互換性喪失、既存 checkpoint load 不可

### 2. style_proj ゼロ初期化 vs 平均値初期化

**現状 (fork 準拠)**: `nn.init.zeros_(style_proj.weight)` で後方互換性を担保。

**代替案**:
- **平均値初期化**: style bank の平均ベクトルを初期値として注入
  - メリット: 学習初期から style 空間を認識、収束加速
  - デメリット: 後方互換性喪失、既存 ckpt から resume 時に挙動変化
- **正規乱数 + warmup**: 学習初期数 epoch は style_vector の影響を 0→1 で linear warmup
  - メリット: 学習安定性向上、爆発的な勾配回避
  - デメリット: warmup schedule ハイパラ追加、コード複雑化
- **Zero + Bias 学習可**: weight はゼロだが bias は学習対象 (現状は両方ゼロ)
  - メリット: weight がゼロのままでも bias で style の global shift を表現可能
  - デメリット: 後方互換性微損 (bias が gradient で動く)

### 3. CLI オプションの group 化

**現状 (fork 準拠)**: `--style-vector-dim`, `--style-condition-dropout`, `--style-condition-mode` がフラットに argparse に並ぶ。Phase 4 で `--pea-emotion-*` 13 個が追加される予定。

**代替案**:
- **argparse group 化**: `parser.add_argument_group("Style Conditioning")` でまとめる
  - メリット: `--help` 出力が整理される、将来の拡張が容易
  - デメリット: fork との diff 増加
- **設定ファイル化 (YAML/TOML)**: `--config style_config.yaml` で style 系パラメータを一括指定
  - メリット: CLI が短くなる、再現性向上
  - デメリット: 既存 CLI ユーザーへの影響大、移行工数増

### 4. Utterance の style_vector 格納方式

**現状 (fork 準拠)**: `Utterance.style_vector_path: Path | None` で独立 `.npy` ファイル指定。

**代替案**:
- **dataset.jsonl 内 base64 インライン化**: `{"style_vector_b64": "..."}` で 1 行に完結
  - メリット: ファイル数削減 (508k 発話 → 508k npy 問題を回避)、デプロイ簡単
  - デメリット: jsonl サイズ肥大 (256-dim float32 = ~1.4KB/行 base64 → +700MB/500k 行)、既存 npy 運用との互換性なし
- **Parquet 形式で一括保存**: `style_vectors.parquet` を memmap で lazy load
  - メリット: I/O 高速化、ディスク消費削減 (圧縮込み)
  - デメリット: pyarrow 依存追加、実装工数増
- **HDF5 形式**: キー = utterance_id で random access
  - メリット: 大規模データセットで効率的
  - デメリット: h5py 依存、fork との diff 増

### 5. Phase 1 でやらないこと (意図的スコープ外)

- **PE-A emotion loss**: Phase 4 に分離。models.py/lightning.py/__main__.py への pe-a 関連追加は一切しない
- **Style bank (自動生成)**: Phase 3 で `build_pea_style_bank.py` として実装
- **他ランタイム (Rust/C#/Go/WASM/C++) 対応**: Phase 2 の ONNX+ランタイムで対応
- **fine-tune recipe 実装**: Phase 5 で CLAUDE.md に並ぶ形で追加
- **save_last=True → False**: fork で PE-A と独立の変更だが、本家方針の別議論 → 別 PR で検討

---

## 成功基準

### 必達要件

1. `--style-vector-dim 0` (default) で既存 CI (`python-tests.yml`) が全て green
2. `--style-vector-dim 256 --style-condition-mode global` で 1 epoch dry-run が NaN なく完走
3. 新規 11 テスト (style 8 + load_weights 3) が全て green
4. CLAUDE.md に新セクション `### Style Vector Conditioning (--style-vector-dim)` が追加されている
5. PE-A emotion loss 関連コードが本 Phase のコードに混入していない (Phase 4 で分離取り込み)

### 品質要件

- `style_proj` のゼロ初期化により `dim=0` と `dim=N, style_vector=None` の forward 出力が bit-for-bit 一致
- `--load_weights_from_checkpoint` が shape 不一致テンソルを skip + warning ログで処理
- `style_condition_mode` バリデーションが `__init__` で実行 (`{"global", "text"}` 以外は ValueError)
- `global` mode で `gin_channels > 0` を要求 (違反時 ValueError)
- 既存の `--freeze-dp` / `--resume-from-multispeaker-checkpoint` と共存可能

### パフォーマンス要件 (目安)

- 学習 step 時間の増加は 5% 以内 (dim=256, 追加 Linear 層のみ)
- ckpt ファイルサイズ増加は +2MB 以内 (style_proj の 3 層分のパラメータ)
- CI 総実行時間の増加は 30 秒以内 (新規 11 テスト分)

---

## 参考リンク

- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- 全体調査: [`docs/research/peav-style-conditioning.md`](../../peav-style-conditioning.md)
- Phase 0-1 計画: [`docs/research/implementation-plan/phase-0-1.md`](../../implementation-plan/phase-0-1.md)
- Phase 2 計画: [`docs/research/implementation-plan/phase-2.md`](../../implementation-plan/phase-2.md)
- Phase 3-4 計画: [`docs/research/implementation-plan/phase-3-4.md`](../../implementation-plan/phase-3-4.md)
- Phase 5 計画: [`docs/research/implementation-plan/phase-5.md`](../../implementation-plan/phase-5.md)
- マイルストーン #11: https://github.com/ayutaz/piper-plus/milestone/11
