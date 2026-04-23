# P1-T06: Unit テスト作成 (style_vector 8件 + load_weights 3件)

| 項目 | 値 |
|------|-----|
| Phase | 1 |
| マイルストーン | [#11](https://github.com/ayutaz/piper-plus/milestone/11) |
| ステータス | 完了 |
| 優先度 | 高 |
| Claude Code 工数 | 1h |
| 依存チケット | P1-T01, P1-T02, P1-T03, P1-T04, P1-T05 |
| 後続チケット | P1-T07 |
| 関連 PR | PR-B |

## 1. タスク目的とゴール

### 1.1 目的

Phase 1 で実装した Style Vector Conditioning 機能の Unit テストを 2 ファイルに分けて作成する:

1. `tests/test_style_vector_conditioning.py` — TextEncoder / SynthesizerTrn / dataset / infer 側の動作確認 (8 テスト)
2. `tests/test_load_weights_from_checkpoint.py` — shape-aware loader の動作確認 (3 テスト)

**最重要要件**: `style_vector_dim=0` (default) で既存モデルと bit-for-bit 一致することを検証 (regression test)。

### 1.2 ゴール (Definition of Done)

- [ ] `tests/test_style_vector_conditioning.py` に 8 テストが実装され、全て pass する
- [ ] `tests/test_load_weights_from_checkpoint.py` に 3 テストが実装され、全て pass する
- [ ] `pytest tests/test_style_vector_conditioning.py tests/test_load_weights_from_checkpoint.py -v` がローカルで green
- [ ] Python CI (`python-tests.yml`) でも pass する (P1-T07 で最終確認)
- [ ] テストは GPU なし (CPU のみ) で動く
- [ ] caplog / tmp_path などの pytest fixture を適切に利用
- [ ] テストケースごとに docstring で目的を明記

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `tests/test_style_vector_conditioning.py` (新規作成、+200 行想定)
- `tests/test_load_weights_from_checkpoint.py` (新規作成、+80 行想定)

### 2.2 実装手順

1. phase-0-1.md §1.5 のテストケース設計をベースにスケルトンを作成
2. 各テストで SynthesizerTrn / TextEncoder / PiperDataset を最小構成で生成
3. フィクスチャを共通化 (hidden_channels, vocab_size, 音素ダミーデータなど)
4. `test_style_vector_conditioning.py` 8 ケース実装 (詳細は §2.3)
5. `test_load_weights_from_checkpoint.py` 3 ケース実装 (詳細は §2.4)
6. pytest 実行で全て green 確認
7. fork 実装のテストコード (もしあれば) を参考にするが、本家側で書き直す

### 2.3 test_style_vector_conditioning.py のテストケース

phase-0-1.md §1.5 に従い以下 8 テストを実装:

```python
import pytest
import torch
from piper_train.vits.models import TextEncoder, SynthesizerTrn


class TestStyleVectorConditioning:
    def test_backwards_compatible_dim_0(self):
        """style_vector_dim=0 で既存挙動と完全に等価であることを確認."""
        # 2 つのエンコーダ (dim=0 明示と default) を作成
        # 同じ seed/input で forward 出力が bit-for-bit 一致
        torch.manual_seed(42)
        enc_default = TextEncoder(
            n_vocab=100, out_channels=192, hidden_channels=192,
            filter_channels=768, n_heads=2, n_layers=6,
            kernel_size=3, p_dropout=0.1,
        )
        torch.manual_seed(42)
        enc_explicit_0 = TextEncoder(
            n_vocab=100, out_channels=192, hidden_channels=192,
            filter_channels=768, n_heads=2, n_layers=6,
            kernel_size=3, p_dropout=0.1,
            style_vector_dim=0,
        )
        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        enc_default.eval()
        enc_explicit_0.eval()
        with torch.no_grad():
            out1 = enc_default(x, x_lengths)
            out2 = enc_explicit_0(x, x_lengths)
        for o1, o2 in zip(out1, out2):
            assert torch.allclose(o1, o2, atol=0.0, rtol=0.0)

    def test_global_mode_projection_zero_init(self):
        """Global mode の style_proj がゼロ初期化されていること."""
        model = SynthesizerTrn(
            # ... 多話者構成で gin_channels > 0 ...
            style_vector_dim=256,
            style_condition_mode="global",
            gin_channels=512,
            n_speakers=10,
        )
        # style_proj の最終層 weight/bias を確認
        # Linear → SiLU → Linear の最終 Linear がゼロ初期化されているべき
        for param in model.style_proj.parameters():
            # 最終層がゼロなら全体でもゼロ出力 (SiLU 経由でもゼロ)
            pass
        style_vector = torch.randn(2, 256)
        out = model.style_proj(style_vector)
        assert torch.allclose(out, torch.zeros_like(out))

    def test_style_vector_none_fallback(self):
        """style_vector=None で zeros fallback."""
        model = TextEncoder(
            # ... 最小構成 ...
            style_vector_dim=256,
        )
        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        out_none = model(x, x_lengths, style_vector=None)
        zeros = torch.zeros(2, 256)
        out_zeros = model(x, x_lengths, style_vector=zeros)
        # style_proj がゼロ初期化されているので None と zeros は同一出力
        for o1, o2 in zip(out_none, out_zeros):
            assert torch.allclose(o1, o2)

    def test_dropout_training_mode(self):
        """Training mode で dropout が効く (複数回実行で異なる出力)."""
        model = TextEncoder(
            # ... 構成 ...
            style_vector_dim=256,
            style_condition_dropout=0.5,
        )
        model.train()
        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        style_vector = torch.randn(2, 256)
        # Note: style_proj がゼロ初期化なので出力差を観察するには
        # style_proj.weight をランダム化してから実行
        with torch.no_grad():
            torch.nn.init.normal_(model.style_proj.weight)
        outputs = []
        for _ in range(5):
            outputs.append(model(x, x_lengths, style_vector=style_vector)[0])
        # 少なくとも 1 組は異なる
        all_same = all(torch.allclose(outputs[0], o) for o in outputs[1:])
        assert not all_same

    def test_dropout_eval_mode(self):
        """Eval mode で dropout が効かない (決定的)."""
        model = TextEncoder(
            style_vector_dim=256,
            style_condition_dropout=0.5,
        )
        model.eval()
        x = torch.randint(0, 100, (2, 10))
        x_lengths = torch.tensor([10, 8])
        style_vector = torch.randn(2, 256)
        with torch.no_grad():
            out1 = model(x, x_lengths, style_vector=style_vector)[0]
            out2 = model(x, x_lengths, style_vector=style_vector)[0]
        assert torch.allclose(out1, out2)

    def test_text_mode_works_with_dim_0(self):
        """text mode + dim=0 で style_proj=None."""
        model = SynthesizerTrn(
            # ... 最小構成 ...
            style_vector_dim=0,
            style_condition_mode="text",
        )
        assert model.style_proj is None

    def test_global_mode_requires_gin_channels(self):
        """Global mode で gin_channels<=0 なら ValueError."""
        with pytest.raises(ValueError, match="gin_channels"):
            SynthesizerTrn(
                # ... 構成 ...
                style_vector_dim=256,
                style_condition_mode="global",
                gin_channels=0,
                n_speakers=1,
            )

    def test_invalid_mode_raises(self):
        """未知の mode で ValueError."""
        with pytest.raises(ValueError):
            SynthesizerTrn(
                # ... 構成 ...
                style_condition_mode="invalid",
            )
```

### 2.4 test_load_weights_from_checkpoint.py のテストケース

phase-0-1.md §1.5 の 3 テスト:

```python
import pytest
import torch
from piper_train.vits.models import SynthesizerTrn


def test_shape_aware_partial_load(tmp_path):
    """既存 6lang checkpoint から style_proj 付きモデルへロード."""
    # 1. 既存モデル (style_vector_dim=0) を保存
    model_old = SynthesizerTrn(
        # ... 構成 ...
        style_vector_dim=0,
    )
    ckpt_path = tmp_path / "old.ckpt"
    torch.save({"state_dict": model_old.state_dict()}, ckpt_path)

    # 2. 新規モデル (style_vector_dim=256) を構築
    model_new = SynthesizerTrn(
        # ... 同じ構成 + style_vector_dim=256 ...
        style_vector_dim=256,
        style_condition_mode="global",
    )

    # 3. load_weights_from_checkpoint 相当の処理
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    state_dict = checkpoint["state_dict"]
    model_sd = model_new.state_dict()
    filtered_sd = {
        k: v for k, v in state_dict.items()
        if k in model_sd and model_sd[k].shape == v.shape
    }
    model_new.load_state_dict(filtered_sd, strict=False)

    # 4. 既存層は復元、style_proj は初期値 (zero) のまま
    # チェック: model_new の共通層が model_old と一致
    for key, tensor in state_dict.items():
        if key in model_sd:
            assert torch.allclose(model_new.state_dict()[key], tensor)
    # style_proj の weight は zero のまま
    assert torch.allclose(
        model_new.style_proj[-1].weight,
        torch.zeros_like(model_new.style_proj[-1].weight),
    )


def test_skip_mismatched_shape_logs_warning(caplog, tmp_path):
    """Shape 不一致テンソルはスキップ、warning ログ出力."""
    # 意図的に shape 不一致を作る (例: 異なる vocab size)
    # ... checkpoint 保存 ...
    # ... load_weights_from_checkpoint 実行 ...
    # caplog で warning レベルのログに "skipped" または "shape" を含むか確認
    pass


def test_strict_true_raises_on_missing(tmp_path):
    """strict=True なら不足テンソルで RuntimeError."""
    # strict=True で load → RuntimeError with "Missing key(s)"
    with pytest.raises(RuntimeError, match="Missing|Unexpected"):
        pass  # 実装詳細
```

## 3. エージェントチーム構成

- **Test Implementation Agent**: 1 名 (Claude Code)
  - 既存 `tests/test_freeze_dp.py` / `tests/test_export_onnx.py` のスタイルを踏襲
- **Verification Agent**: 1 名 (Claude Code、全テストが pass することを確認)
  - pytest 実行 → 失敗したら原因特定 → 必要に応じて T01-T05 側の修正依頼

## 4. 提供範囲 (Deliverables)

| アーティファクト | パス |
|---------------|------|
| Style vector 統合テスト | `tests/test_style_vector_conditioning.py` (新規) |
| Load weights テスト | `tests/test_load_weights_from_checkpoint.py` (新規) |
| pytest 実行結果ログ | PR-B コメントに添付 |

**提供範囲外**:
- E2E テスト (1 epoch 学習) は P1-T07 で CI リグレッション確認として実施
- 他ランタイム (Rust/C#/Go) のテスト (Phase 2)

## 5. テスト項目

### 5.1 Unit テスト (本チケットで実装)

上記 §2.3 §2.4 の全 11 ケース (8+3)。

### 5.2 メタテスト (本チケット完了確認)

- `pytest tests/test_style_vector_conditioning.py -v` で 8 green
- `pytest tests/test_load_weights_from_checkpoint.py -v` で 3 green
- `pytest tests/ -v` で既存 freeze_dp / export_onnx 等のテストも全て green (regression なし)

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **SynthesizerTrn の最小構成生成**: 既存モデル構築パラメータが多数あり、テストごとに boilerplate が膨らむ。→ `conftest.py` にヘルパー fixture を作る or ローカルヘルパー関数
- **test_backwards_compatible_dim_0**: bit-for-bit 一致を検証する際、dropout 層のランダム性で seed を確実に固定する必要あり。`torch.manual_seed(42)` を複数回呼ぶ
- **test_dropout_training_mode の決定性**: dropout の挙動を "少なくとも 1 回は異なる出力" で確認。seed を制御しすぎると常に同じになる
- **test_strict_true_raises_on_missing の API 形**: `--load_weights_from_checkpoint` が strict= を取るかどうか fork 実装を確認。取らない場合は `model.load_state_dict(filtered_sd, strict=True)` をテスト中で直接呼ぶ
- **GPU なしでの実行**: 全テストが CPU で完結すること (CI 環境考慮)
- **ファイルサイズ**: SynthesizerTrn の full モデル保存は MB 単位。tmp_path を使うので CI 実行時にはクリアされるが、RAM が足りない CI では削減を検討

### 6.2 レビュー項目

- [ ] 全 11 テストが独立して実行可能 (fixture 依存のみ)
- [ ] `@pytest.mark.slow` などで重いテストを分離していない (今回は分離不要なサイズ)
- [ ] テストケースごとに明示的な docstring
- [ ] `caplog.records` の level と message が明示的にチェックされている
- [ ] `pytest.raises(ValueError, match="...")` で match 指定されている
- [ ] `tmp_path` fixture を適切に利用
- [ ] GPU 非依存 (`torch.device("cpu")` 固定)

## 7. 一から作り直すとしたら

- **代替案 A**: Hypothesis ベースの property-based testing
  - メリット: edge case カバレッジ向上
  - デメリット: 実装工数増、piper-plus の既存 pytest スタイルから逸脱
- **代替案 B**: `conftest.py` で `synthesizer_factory` fixture を作り boilerplate を削減
  - メリット: テストコード簡潔化、再利用性向上
  - デメリット: fixture が複雑化、デバッグ難化
- **代替案 C**: テストを 1 ファイルに統合 (`test_style_conditioning.py`)
  - メリット: 関連テストが 1 箇所に集約
  - デメリット: ファイル肥大化 (11 テスト + boilerplate で 300+ 行)

**採用理由**: 既存 `test_freeze_dp.py` / `test_export_onnx.py` のスタイルに合わせ、1 トピック 1 ファイル (style_vector と load_weights) の分割を採用。将来 Phase 4 の PE-A loss テストを追加するときに統合性を保ちやすい。

## 8. 後続タスクへの連絡事項

- **P1-T07 へ**: 本チケットで新規テストが 11 件追加されているので、既存 CI で timeout が起きないこと確認。CI 実行時間が 5 分以内なら問題なし
- **Phase 4 (PE-A loss) へ**: `tests/test_style_vector_conditioning.py` と似たパターンで `tests/test_pea_emotion_loss.py` を追加予定
- **Phase 2 (ONNX) へ**: ONNX 側のテストは `tests/test_export_onnx.py` を拡張する形で追加

## 9. 参考リンク

- phase-0-1.md §1.5 テストケース設計 (本チケットのベース)
- Fork commit (取り込み元、テスト参考): https://github.com/yusuke-ai/piper-plus/commit/314b3355
- 既存テスト参考: `tests/test_freeze_dp.py`, `tests/test_export_onnx.py`, `tests/test_speaker_embedding.py`
- pytest caplog docs: https://docs.pytest.org/en/stable/how-to/logging.html
