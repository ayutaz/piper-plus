# P1-T02: dataset.py に style_vector フィールドを追加

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 完了 |
| 優先度 | 高 |
| Claude Code 工数 | 30分〜1h |
| 依存チケット | なし (T01 と並行可能) |
| 後続チケット | P1-T03, P1-T06 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

`src/python/piper_train/vits/dataset.py` に Style Vector の読み込みとバッチ化機構を追加する。既存の dataset.jsonl 行に `style_vector_path` と `emotion` フィールドが含まれる場合に、テンソルとして load して batch に詰める。いずれも**オプション**で、未指定の場合は zeros fallback とする。

Phase 1 では `emotion` は**読み込むだけ**でロス計算には使用しない (Phase 4 で活用)。

### 1.2 ゴール (Definition of Done)

- [ ] `Utterance` データクラスに `style_vector_path: Path | None`, `emotion: str | None` フィールドが追加されている
- [ ] `UtteranceTensors` に `style_vector: FloatTensor`, `emotion: str` フィールドが追加されている
- [ ] `Batch` に `style_vectors: FloatTensor`, `emotions: list[str]` フィールドが追加されている
- [ ] `__getitem__` で `_load_tensor(style_vector_path)` により npy/pt ファイルから load する処理が動く
- [ ] style_vector_path が None または欠落の場合は zeros tensor を返す
- [ ] `BatchCollator.__call__` が style_vectors を事前割当 (`torch.zeros((batch_size, style_vector_dim))`) し slice-copy で詰める
- [ ] 既存 dataset.jsonl (style_vector_path なし) で regression しない
- [ ] emotion string は UtteranceTensors / Batch に格納されるが Phase 1 では参照されない

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `src/python/piper_train/vits/dataset.py` (修正、+80 行想定)

### 2.2 実装手順

1. Fork commit `314b3355` の `dataset.py` 差分を取得する
2. `Utterance` データクラスに `style_vector_path: Path | None = None`, `emotion: str | None = None` を追加
3. `UtteranceTensors` データクラスに `style_vector: torch.FloatTensor`, `emotion: str` を追加
4. `Batch` データクラスに `style_vectors: torch.FloatTensor`, `emotions: list[str]` を追加
5. dataset.jsonl 読み込み部で `style_vector_path` / `emotion` フィールドを pick (欠落時は None)
6. `__getitem__` で `_load_tensor(style_vector_path)` ヘルパーを呼ぶ実装を追加
   - `.npy` なら `np.load → torch.from_numpy`
   - `.pt` / `.pth` なら `torch.load(map_location='cpu')`
   - None なら `torch.zeros(style_vector_dim)` (ただし dim は `self.style_vector_dim` で事前把握)
7. `BatchCollator.__call__` で style_vectors 事前割当を追加
   - shape `[batch_size, style_vector_dim]`
   - slice-copy で `collated.style_vectors[i] = utt.style_vector`
8. `style_vector_dim` を `PiperDataset.__init__` で受け取る必要あり (0 なら全て zeros、無効化扱い)
9. `emotion` は `list[str]` で batch に詰める (None は `""` に変換)

### 2.3 コード例 (phase-0-1.md §1.4 Patch 3 相当)

```python
@dataclass
class Utterance:
    # ... 既存フィールド ...
    style_vector_path: Path | None = None
    emotion: str | None = None


@dataclass
class UtteranceTensors:
    # ... 既存フィールド ...
    style_vector: torch.FloatTensor
    emotion: str


@dataclass
class Batch:
    # ... 既存フィールド ...
    style_vectors: torch.FloatTensor
    emotions: list[str]


class PiperDataset(torch.utils.data.Dataset):
    def __init__(self, ..., style_vector_dim: int = 0, ...):
        self.style_vector_dim = style_vector_dim
        # ... 既存 ...

    def __getitem__(self, idx):
        utt = self.utterances[idx]
        # ... 既存の音素・音響特徴量読み込み ...
        if self.style_vector_dim > 0 and utt.style_vector_path is not None:
            style_vector = _load_tensor(utt.style_vector_path)
        else:
            style_vector = torch.zeros(self.style_vector_dim)
        emotion = utt.emotion or ""
        return UtteranceTensors(..., style_vector=style_vector, emotion=emotion)


class BatchCollator:
    def __call__(self, utterances: list[UtteranceTensors]) -> Batch:
        # ... 既存のパディング処理 ...
        batch_size = len(utterances)
        style_vectors = torch.zeros((batch_size, self.style_vector_dim))
        emotions: list[str] = []
        for i, utt in enumerate(utterances):
            style_vectors[i] = utt.style_vector
            emotions.append(utt.emotion)
        return Batch(..., style_vectors=style_vectors, emotions=emotions)
```

完全な diff は `gh api "repos/yusuke-ai/piper-plus/commits/314b3355"` で取得。PE-A 関連コード (emotion loss 用のロジック) は除外すること。

## 3. エージェントチーム構成

- **Implementation Agent**: 1 名 (Claude Code、`dataset.py` 修正)
  - fork diff 取得 → `Utterance`/`UtteranceTensors`/`Batch`/`PiperDataset`/`BatchCollator` に追加
- **Verification Agent**: 1 名 (Claude Code、既存データセットでの非破壊確認)
  - `dataset-multilingual-6lang-filtered` の jsonl で style_vector_path / emotion が None のまま dataset iter できること

P1-T01 と並行で進めて問題ない。

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| 修正済み dataset.py | `src/python/piper_train/vits/dataset.py` |
| ヘルパー関数 `_load_tensor` | 同ファイル (または既存のヘルパー module) |

**提供範囲外**:
- Style bank 生成スクリプト (Phase 3 で実装予定)
- `speaker_balanced_sampling` との同時動作検証 (既存機能、今回の変更で影響なしを確認するのみ)
- dataset.jsonl への `style_vector_path` 追加 (運用者が style bank 生成後に追記)

## 5. テスト項目

### 5.1 Unit テスト (P1-T06 で一部カバー)

本チケットでは主要な dataset の疎通確認を実施。以下は T06 で追加してもよい:
- `test_dataset_style_vector_none_fallback`: `style_vector_path=None` で zeros tensor が返ること
- `test_dataset_style_vector_npy_load`: `.npy` ファイルから load できること
- `test_batch_collator_style_vectors_shape`: batch.style_vectors.shape == `[batch_size, style_vector_dim]`
- `test_dataset_legacy_jsonl_no_style_vector_path`: 既存 jsonl (フィールドなし) で KeyError/AttributeError が出ない

### 5.2 E2E テスト (本チケットのスモーク)

- `python -c "from piper_train.vits.dataset import PiperDataset, Batch; print('ok')"` が成功
- 既存 `dataset-multilingual-6lang-filtered/dataset.jsonl` (style_vector_path なし) を `style_vector_dim=0` で iterate して 10 件取得
- 同 jsonl を `style_vector_dim=256` で iterate して全件 zeros が返ることを確認

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **dataset.jsonl フォーマット互換**: 既存 jsonl に `style_vector_path` / `emotion` キーがない場合 `KeyError` で落ちる可能性。→ `utterance.get("style_vector_path")` パターンで必ず None 許容にする
- **BatchCollator の事前割当サイズ**: `style_vector_dim=0` のときに `torch.zeros((batch_size, 0))` が下流の TextEncoder で想定通り動くか要確認 (P1-T01 の `style_proj is None` 分岐と整合)
- **npy vs pt の両対応**: fork が `.npy` のみ対応の場合、本家では `.pt` も受けるなど拡張する？ → fork 準拠にする (拡張は Phase 3 で判断)
- **メモリ消費**: 100k サンプルで 256-dim float32 style_vector を dataset worker ごとに保持すると ~100MB/worker。→ ディスク load 方式 (lazy) を維持し in-memory cache はしない
- **`emotion` string の type consistency**: None を空文字列に変換するか、None のまま batch に渡すか要設計決定。→ `list[str]` 型安定のため空文字変換を採用

### 6.2 レビュー項目

- [ ] `style_vector_path` が jsonl 側で optional (欠落可能)
- [ ] `style_vector_dim=0` で既存挙動と一致 (P1-T06 で検証)
- [ ] `.npy` と `.pt` 両対応 (fork 準拠)
- [ ] `BatchCollator` の事前割当が `torch.zeros` で初期化されている
- [ ] `emotion` 列が Phase 1 では読み捨て (使われない)
- [ ] DataLoader multiprocessing (`num_workers >= 1`) でピクル可能なデータクラス構造を維持

## 7. 一から作り直すとしたら

- **代替案 A**: Utterance の `style_vector_path` を独立 file ではなく dataset.jsonl 内の base64 にインライン化
  - メリット: ファイル数削減 (100k 発話 → 100k npy ファイル問題を回避)、jsonl 1 行で完結
  - デメリット: jsonl サイズ肥大 (256-dim float32 = 1.4KB/行 base64 → +140MB/100k 行)、既存 npy 運用との互換性なし
- **代替案 B**: Parquet 形式で style_vector を先に一括保存し、dataset worker が mmap で読む
  - メリット: I/O 高速化、ディスク消費削減 (圧縮込み)
  - デメリット: pyarrow 依存追加、実装工数増
- **代替案 C**: style_vector を memmap tensor で起動時に一括 load (CPU RAM 常駐)
  - メリット: 完全ゼロ I/O で最速
  - デメリット: 大規模データセット (508k サンプル × 256-dim = 500MB) を常駐するので制約環境で OOM

**採用理由**: fork 実装との diff 最小化、既存 npy 生成パイプライン (Phase 3 `build_pea_style_bank.py` 想定) との接続性を優先。大規模化した際は代替案 B/C を再検討。

## 8. 後続タスクへの連絡事項

- **P1-T03 へ**: `batch.style_vectors` / `batch.emotions` が使えるようになる。`lightning.py` の `training_step` で `style_vector=batch.style_vectors` を SynthesizerTrn.forward に渡すこと
- **P1-T04 へ**: `PiperDataset` コンストラクタに `style_vector_dim` 引数が追加される。`__main__.py` 側で args からこの値を渡す必要がある
- **P1-T06 へ**: テストで使う `_load_tensor` のパブリック/プライベート区分を連絡 (同モジュール内 private を推奨)
- **P3 へ (Style bank 構築)**: dataset.jsonl に `style_vector_path` フィールドを追加する仕様を承継すること。ファイル形式は `.npy` を基本とする

## 9. 参考リンク

- Fork commit (取り込み元): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- phase-0-1.md §1.2-C `src/python/piper_train/vits/dataset.py`
- phase-0-1.md §1.4 Patch 3: `vits/dataset.py`
- 既存データセット: `/data/piper/dataset-multilingual-6lang-filtered/`
- CLAUDE.md 「前処理ツール」セクション (`prepare_multilingual_dataset.py`)
