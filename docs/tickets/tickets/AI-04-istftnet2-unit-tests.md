# AI-04: iSTFTNet2-MB ユニットテスト追加 (test_istftnet2_generator.py)

## メタ情報

- ID: AI-04
- 親マイルストーン: [M2](../milestones/M2-istftnet2-mb-backbone.md)
- 工数見積: 0.5 日
- 依存チケット: AI-03 (iSTFTNet2-MB 1D-2D backbone 実装)
- 後続チケット: AI-05 (iSTFTNet2-MB PoC 学習 50 epoch の前提)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 AI-04 / §4.2 A-1 backbone / §4.6 Benchmarks](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

AI-03 で `MBiSTFTGenerator` に追加した `decoder_type` 分岐 (`_forward_1d` 温存 + `_forward_1d2d` 新規) を、 PoC 学習 (AI-05、 50 epoch / 1 GPU で約 40h) に投入する**前段の安全弁**として、 形状 / params / 後方互換 / 既存 1D 経路非破壊を assert で固定する。 50 epoch の学習計算資源を投入してから shape mismatch や params drift が発覚すると 1.5d 分のロールバックが発生するため、 unit 段階で全部塞ぐのが本チケットの目的。

計画 §6 AI-04 の指示に従い、 **新規ファイル `src/python/tests/test_istftnet2_generator.py`** を起こす。 既存 `src/python/tests/test_mb_istft_generator.py` は **G-1.9 後方互換 gate** の対象として一切 touch しない (1D 経路の baseline behaviour を contract 化しているため)。 上流 (AI-03) から受け取るのは `decoder_type` 引数追加版 `MBiSTFTGenerator` クラスのみで、 下流 (AI-05) には「`decoder_type='istftnet2_mb_1d2d'` で forward が確実に通る」「params 0.83M ± 0.05M 帯域内」「6lang base ckpt の 1D 部分 conv が key 一致で warm start 可能」の 3 点を保証して引き渡す。

TDD 前提のため、 計画 §8 Immediate Next Steps 2 で示されているとおり AI-03 と並走で**先に test を書いて red を確認**してから AI-03 実装で green に持ち込むワークフローを取る。 本チケットは red → green の test 側半分を完成させる位置づけ。

## 実装内容の詳細

**新規ファイル:** `src/python/tests/test_istftnet2_generator.py` (~250-300 LoC、 既存 `test_mb_istft_generator.py` の helper 構造 `_make_generator()` を踏襲)

**編集対象:**

- `src/python/tests/test_istftnet2_generator.py` (新規)
- `src/python/tests/conftest.py` (既存、 追加 fixture が必要であれば末尾 append のみ。 既存 fixture 編集禁止)

**編集禁止 (G-1.9 後方互換 / G-1.2 baseline 編集禁止):**

- `src/python/tests/test_mb_istft_generator.py` (1D 経路 baseline contract、 1 行も触らない)
- `src/python/tests/test_mb_istft_utilities.py` (PQMF/sub_band ヘルパ contract)
- `src/python/tests/test_main_mb_istft.py` (CLI 経路 contract)
- `docs/spec/audio-parity-contract.toml` の `[mb_istft_1d]` section (AI-14 で `[istftnet2_mb_1d2d]` を別 section として併載するため、 本チケットでは contract 自体に触らない)

**新規テスト関数 (8 件想定):**

| 関数 | カバー領域 | 主な assert |
|------|----------|------------|
| `test_default_decoder_type_is_1d` | G-1.9 後方互換 | `MBiSTFTGenerator(**defaults).decoder_type == 'mb_istft_1d'`、 `_forward_1d` 経路を採用 |
| `test_forward_1d_unchanged_when_default` | 既存 1D 経路非破壊 | default 構築で fullband.shape == (2, 1, 8192)、 subbands.shape == (2, 4, 2048) (= 既存 `test_mb_istft_generator.py:test_generator_output_shape_training` と完全一致) |
| `test_forward_1d2d_output_shape_training` | 1D-2D 経路 forward 形状 | `decoder_type='istftnet2_mb_1d2d'`、 fullband.shape == (2, 1, 8192) (出力 shape `[B, 1, T]` 不変 = 計画 §4.2 互換性制約) |
| `test_forward_1d2d_output_shape_onnx_mode` | ONNX export 経路 | `onnx_export_mode=True` で single tensor 返却、 shape (2, 1, 8192) |
| `test_forward_1d2d_params_within_target` | params 帯域 (§4.6) | `sum(p.numel() for p in gen.parameters())` が 0.78M ≤ x ≤ 0.88M (= 0.83M ± 0.05M target) |
| `test_forward_1d2d_speaker_conditioning` | gin_channels 互換 | gin_channels=512 で g 入力時に fullband.shape[0] == 2 が成立 (PR #222 spk_proj 統合点との conflict 早期検知) |
| `test_forward_1d2d_warm_start_key_compat` | 6lang base ckpt warm start | `decoder_type='istftnet2_mb_1d2d'` の state_dict が `conv_pre.*` / `cond.*` / `subband_conv_post.*` の key を含み、 既存 1D ckpt から strict=False で load して missing_keys に 1D 部分が出ない |
| `test_forward_1d2d_convtranspose_localized` | R7 mitigation | `[m for n, m in gen.named_modules() if isinstance(m, torch.nn.ConvTranspose2d)] == []` (ConvTranspose2d 完全不使用、 ups[0]/[1] の ConvTranspose1d 2 段のみで mobile EP CPU fallback 回避) |

**疑似コード スケッチ (~25 行):**

```python
# src/python/tests/test_istftnet2_generator.py
import pytest

torch = pytest.importorskip("torch", reason="torch required")


def _make_generator(decoder_type=None, **overrides):
    from piper_train.vits.mb_istft import MBiSTFTGenerator
    defaults = dict(
        initial_channel=192, resblock="2",
        resblock_kernel_sizes=(3, 5, 7),
        resblock_dilation_sizes=((1, 2), (2, 6), (3, 12)),
        upsample_rates=(4, 4),
        upsample_initial_channel=256,
        upsample_kernel_sizes=(16, 16),
    )
    if decoder_type is not None:
        defaults["decoder_type"] = decoder_type
    defaults.update(overrides)
    return MBiSTFTGenerator(**defaults)


@pytest.mark.unit
def test_default_decoder_type_is_1d():
    """G-1.9: default は 1D 経路 (PR #222 noise_scale 変更とは独立に decoder_type も不変)。"""
    gen = _make_generator()  # decoder_type 未指定
    assert gen.decoder_type == "mb_istft_1d"


@pytest.mark.unit
def test_forward_1d2d_params_within_target():
    """計画 §4.6: 0.83M ± 0.05M params 帯域。"""
    gen = _make_generator(decoder_type="istftnet2_mb_1d2d")
    n = sum(p.numel() for p in gen.parameters())
    assert 0.78e6 <= n <= 0.88e6, f"params drift: {n/1e6:.3f}M not in 0.83M ± 0.05M"
```

**PR #222 / #537 conflict 回避策 (計画 §3 Conflict Map より):**

- `vs PR #222` (HIGH conflict on `mb_istft.py`): test 側で `decoder_type` 分岐の default 1D を assert 化しておくことで、 PR #222 rebase 時に `_apply_film` を rank-aware 化したあとも default 経路の behaviour drift を CI で即時検知できる
- `vs PR #537` (NONE on test code, LOW for lightning bf16-mixed): pytest 9 移行で deprecation を踏まないよう、 古い API (`pytest.warns(None)` 等) は使わない。 `pytest.importorskip` は 9 でも valid
- ONNX I/O 不変 (PR #222 二重同期回避): `test_forward_1d2d_output_shape_onnx_mode` で `[B, 1, T]` を assert することで、 companion ONNX 配布 (A-2) や PR #222 後の I/O 同期 diff と独立に 1D-2D 経路の I/O 契約を固定

**設定 default / 新規 CLI フラグ:**

本チケットは test のみで `__main__.py` CLI には触らない (AI-05 で `--decoder-type` フラグを露出するため)。 ただし `_make_generator(decoder_type="istftnet2_mb_1d2d")` のパス名と AI-05 で導入される CLI 引数値は **一致**させる (lower-snake、 ハイフンなし、 `'mb_istft_1d'` / `'istftnet2_mb_1d2d'` の 2 値固定)。

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|----------|---------|
| Test Engineer (Lead) | 1 | pytest / PyTorch / VITS architecture / 既存 piper-plus test 構造 | `test_istftnet2_generator.py` 起票、 8 関数のテストケース設計と assert 値固定、 `_make_generator` helper のシグネチャ整備 |
| ML Researcher (reviewer) | 1 | iSTFTNet2 論文知識 / PQMF / Conv2d params 計算 | params 0.83M ± 0.05M target の妥当性レビュー、 `unsqueeze(F=1)` + 2D Block × 4 + pixel-shuffle の形状計算検証、 warm start key compat の整合性確認 |
| CI Engineer | 1 | pytest marker / GitHub Actions / `python-ci.yml` | `pytest.mark.unit` marker の登録、 既存 `test_mb_istft_generator.py` との独立実行確認、 PR #537 の pytest 9 移行に備えた API 互換チェック |

合計 3 名。 0.5d スコープで PoC 投資の安全弁として最小構成。 ML Researcher は AI-03 担当と同一人物兼務でも可だが、 test の reviewer 役は実装者と分けることで TDD の red 確認 (test 単独で fail することの保証) を独立に担保する。

## 提供範囲 (Scope)

### 含むもの

- `src/python/tests/test_istftnet2_generator.py` の新規作成 (8 テスト関数、 `pytest.mark.unit` 付与)
- `_make_generator(decoder_type=...)` helper の独立実装 (既存 `test_mb_istft_generator.py` の `_make_generator` を**コピー**せず、 別ファイル内で類似 helper を新規定義することで G-1.9 既存テスト編集禁止を遵守)
- params 0.83M ± 0.05M assert の数値固定 (帯域は 0.78M-0.88M で hard-coded、 magic number コメント付き)
- ConvTranspose2d 不使用 assert (R7 mitigation、 mobile EP CPU fallback 防止)
- 6lang base ckpt warm start 互換性の key 名 assert (state_dict missing_keys 検査、 実 ckpt をロードせず synthetic state_dict で検証)
- `decoder_type` default が `'mb_istft_1d'` であることの G-1.9 後方互換 assert

### 含まないもの (Out of Scope)

- 実 6lang base ckpt をロードしての integration test (AI-05 学習開始時に initial sanity で別途実施)
- ONNX export round-trip test (AI-12 / AI-13 で `tools/benchmark/` + 7 ランタイム smoke として実施)
- audio parity / SNR / UTMOS proxy MOS の数値検証 (AI-14 で `audio-parity-contract.toml` に `[istftnet2_mb_1d2d]` section を追加してそこで管理)
- 7 ランタイム pairwise SNR ≥ 30dB 検証 (AI-13)
- CLI flag `--decoder-type` の test (AI-05 で CLI 露出時に `test_main_istftnet2.py` 等で追加)
- PR #222 `_apply_film` rank-aware 化の test (AI-17)
- PR #537 bf16-mixed / TF32-on 影響下の数値ドリフト検証 (AI-16)
- FLY-TTS ConvNeXt6 decoder の test (AI-06 で `test_fly_decoder.py` として別系統)
- MS-Wavehax `wavehax.py` の test (AI-08 / AI-09 で別チケット)

## テスト項目

### Unit Tests

新規ファイル `src/python/tests/test_istftnet2_generator.py` に以下 8 関数。 すべて `pytest.mark.unit` を付与し、 既存 `test_mb_istft_generator.py` の構造と命名規則を踏襲。

- `src/python/tests/test_istftnet2_generator.py::test_default_decoder_type_is_1d`
  - assert: `_make_generator().decoder_type == 'mb_istft_1d'`
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d_unchanged_when_default`
  - assert: `_make_generator()(torch.randn(2, 192, 32))` の fullband.shape == (2, 1, 8192)、 subbands.shape == (2, 4, 2048) (既存 `test_generator_output_shape_training` と完全一致)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_output_shape_training`
  - assert: `_make_generator(decoder_type='istftnet2_mb_1d2d')(torch.randn(2, 192, 32))` の fullband.shape == (2, 1, 8192)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_output_shape_onnx_mode`
  - assert: `onnx_export_mode=True` で返り値が `torch.Tensor` (not tuple)、 shape == (2, 1, 8192)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_params_within_target`
  - assert: `sum(p.numel() for p in gen.parameters())` ∈ [0.78e6, 0.88e6] (= 0.83M ± 0.05M、 計画 §4.6)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_speaker_conditioning`
  - assert: gin_channels=512 + g=torch.randn(2, 512, 1) で fullband.shape[0] == 2 が成立 (PR #222 spk_proj rebase 早期検知)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_warm_start_key_compat`
  - assert: `_make_generator(decoder_type='istftnet2_mb_1d2d').state_dict()` が `conv_pre.weight` / `cond.weight` (gin_channels>0 時) / `subband_conv_post.weight` を含む。 `_make_generator().state_dict()` を strict=False で load した結果、 missing_keys に上記 3 key が**含まれない** (1D 部分の warm start 互換)
- `src/python/tests/test_istftnet2_generator.py::test_forward_1d2d_convtranspose_localized`
  - assert: `[m for n, m in gen.named_modules() if isinstance(m, torch.nn.ConvTranspose2d)] == []` (R7 mitigation、 ConvTranspose1d は `ups[0]` / `ups[1]` の 2 段のみ許容)

### E2E Tests

本チケット範囲外 (上記 Out of Scope 参照)。 ただし unit 完走を**前提**として後続が呼ぶ:

- AI-05 で `decoder_type='istftnet2_mb_1d2d'` + 6lang base ckpt warm start で 1 epoch sanity (~45min)、 WandB audio log で耳触り確認
- AI-12 で `tools/benchmark/` に `istftnet2-mb` entry 追加 → UTMOS proxy MOS + Xeon E5-2650 v4 / 25 phoneme 英文 p50 < 20ms (target × 0.7) ベンチ
- AI-13 で 7 ランタイム smoke + pairwise SNR ≥ 30dB
- AI-14 で `audio-parity-contract.toml` に `[istftnet2_mb_1d2d]` section 追加 (PR #537 TF32 / bf16-mixed 後の tolerance 反映は AI-16 で再 baseline)

### 受入基準 (Acceptance Criteria)

- 8 unit test 全件 green (`uv run --no-sync pytest src/python/tests/test_istftnet2_generator.py --no-cov` で exit 0)
- 既存 `test_mb_istft_generator.py` / `test_mb_istft_utilities.py` / `test_main_mb_istft.py` が touch なしで引き続き green (G-1.9 / G-1.2 baseline 不変)
- params assert が 0.78e6 ≤ x ≤ 0.88e6 の hard-coded 帯域で固定 (計画 §4.6 の 0.83M ± 0.05M target)
- 出力 shape `[B, 1, T]` = (2, 1, 8192) 不変 (計画 §4.2 互換性制約、 PR #222 ONNX I/O 二重同期回避)
- ConvTranspose2d 使用箇所 0 件 assert (R7 mitigation、 ConvTranspose1d 2 段のみ)
- `decoder_type` default が `'mb_istft_1d'` (G-1.9 後方互換)
- pre-commit (ruff check + format) が green、 `pre-commit run --files src/python/tests/test_istftnet2_generator.py` で drift なし

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register より:

- **R1 (HIGH/HIGH)** PR #222 Multi-scale FiLM の `_apply_film` channel-axis split (dim=1) 前提が 4D `[B,C,F,T]` で破綻 → 本 test の `test_forward_1d2d_speaker_conditioning` を gin_channels>0 で fail 化させる early-warning として機能させる
- **R6 (MEDIUM/HIGH)** `audio-parity-contract.toml` baseline regression を A-1/A-2 が誤って書き換え → 本チケットでは contract に触らないが、 既存 1D test と数値が乖離した場合に test が即 fail する逆方向の防波堤として `test_forward_1d_unchanged_when_default` を配置
- **R7 (LOW/MEDIUM)** 2D op の mobile EP CPU fallback → `test_forward_1d2d_convtranspose_localized` で ConvTranspose2d 0 件 assert を CI 化

このチケット固有の細かい懸念:

- **params target drift**: 0.83M ± 0.05M の 0.05M tolerance は計画 §4.6 由来。 2D Block × 4 の kernel size / dilation を実装段階で微調整した結果 0.88M を超える可能性があり、 その場合は AI-03 担当に再設計を依頼 (test 側で帯域を緩めない)
- **synthetic state_dict での warm start 互換性検証は近似でしかない**: 実 6lang base ckpt の key naming (`generator.dec.*` 接頭辞、 lightning 経由) と異なる可能性。 AI-05 で実 ckpt load 時に missing/unexpected を再検証する前提で「key 部分文字列マッチ」レベルに留める
- **`onnx_export_mode=True` フラグの semantics**: AI-03 実装で 1D-2D 経路でも 1D 経路と同じ `(fullband_only_tensor)` を返すか確認必須。 戻り値型が分岐すると ONNX export (AI-12) で `infer_forward` 側に分岐が漏れる
- **pytest 9 移行 (PR #537)**: `pytest.importorskip("torch", reason=...)` は pytest 9 でも valid。 ただし `match=` 引数の正規表現 escape など細部の API drift に注意。 本 test は最小機能のみ使用

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (`MBiSTFTGenerator(**defaults).decoder_type == 'mb_istft_1d'`、 G-1.9 後方互換)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止、 `audio-parity-contract.toml` も touch しない)
- [ ] ONNX I/O 不変 (`onnx_export_mode=True` で `[B, 1, T]` float32 single tensor、 PR #222 二重同期回避)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み (本チケットでは contract に触らないため AI-14 / AI-16 で対応、 ここでは confirmed のみ)
- [ ] 既存 `test_mb_istft_generator.py` / `test_mb_istft_utilities.py` / `test_main_mb_istft.py` を **0 行 touch** で並走 green
- [ ] `_make_generator` helper は既存ファイルから import せず、 新規ファイル内で独立定義 (G-1.9 既存テスト編集禁止の運用)
- [ ] params 帯域 assert (0.78e6, 0.88e6) は magic number コメントで計画 §4.6 を参照
- [ ] ConvTranspose2d 0 件 assert を含む (R7 mitigation)
- [ ] `pytest.mark.unit` marker が全 8 関数に付与済み (CI 既存の unit 集約に組み込み)
- [ ] pre-commit (ruff check + format) clean、 imports は `pytest.importorskip("torch")` で torch 任意化
- [ ] AI-03 の `decoder_type` 引数命名 (`'mb_istft_1d'` / `'istftnet2_mb_1d2d'` の lower-snake 2 値) と完全一致
- [ ] AI-05 の CLI `--decoder-type` 値と整合 (AI-05 着手時に再 cross-check)

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「既存 `test_mb_istft_generator.py` を touch せず、 新規ファイルに helper を独立実装する」 TDD ファースト構成。 これは G-1.9 後方互換 gate と「baseline test の 1 行も触らない」 R6 mitigation を最優先した結果の現実解。 代替として「既存 test ファイルに `parametrize(decoder_type=['mb_istft_1d', 'istftnet2_mb_1d2d'])` を仕込んで 1 ファイル内で両経路を網羅する」案もある。 こちらは DRY (helper 重複排除) と「両経路が**同じ test 関数**で常に同時実行される」CI 強制力が魅力的だが、 (a) 既存 fixture の数値固定 (8192 / 2048) が parametrize 時に意図せず drift する可能性、 (b) PR #537 pytest 9 移行で parametrize id の dedup 仕様が変わる、 (c) AI-03 実装が不完全な段階で既存 test が collection error で全滅し dev 全員が pytest 不能になる、 の 3 リスクで却下。

別案として「integration-test 先行 (実 ckpt + 1 epoch sanity を test_integration.py に組み込む)」も検討した。 これだと params drift も output shape drift も warm start key drift も**実 forward 1 回で全部検出**できるので test 関数 8 個分の workload を 1 関数に圧縮できる。 しかし (i) 実 6lang base ckpt のサイズが ~150MB あり CI artifacts に乗せると billable な network egress が発生する、 (ii) GPU なしの CI runner で 1 epoch がタイムアウトする (Xeon E5-2650 v4 baseline で 25 phoneme 27ms でも dataset 6,200 utt × forward+backward は 45min)、 (iii) test failure 時に「shape か params か warm start のどれが原因か」の切り分けが困難、 という 3 つの実務上の欠点があり、 unit test 8 関数のほうが PoC 段階の debug loop には適している。 integration 経路は AI-05 学習開始時の initial sanity (1 epoch + WandB audio log) で別途カバーされる。

3 つ目の代替として「decoder_type 分岐をやめて `MBiSTFTGenerator` と `ISTFTNet2MBGenerator` を完全に独立クラス化する」設計があり得る。 PR #222 の Multi-scale FiLM が 1D 前提の `_apply_film(channel-axis split)` を後付けで rank-aware 化する作業は構造的に厄介で、 もし最初から別クラスにしておけば PR #222 は 1D クラスのみを rebase 対象にできて conflict map は LOW に下がる。 この案を捨てた理由は計画 §3 で「ONNX export 経路と 7 ランタイム ABI で同一 class name を期待」している既存資産との互換性、 および AI-03 工数見積 3d を「decoder_type 分岐実装」前提で組んでいる点。 完全独立クラス化に切り替えると `models.py` / `lightning.py` / `export_onnx.py` の 3 ファイルで if-isinstance 分岐が追加で必要になり、 AI-03 が 3d → 5d に膨らんで M2 全体が 1 週ずれる。 現状の decoder_type 分岐方式は「PR #222 rebase 時に `_apply_film` rank-aware 化の 1 箇所のみで吸収する」と R1 mitigation で名指しされており、 本チケットの test 設計も**その前提に整合**させる必要がある。

## 後続タスクへの連絡事項

AI-05 (iSTFTNet2-MB PoC 学習 50 epoch) への引き渡し:

- **test green の前提**: 本チケット完了時点で `uv run --no-sync pytest src/python/tests/test_istftnet2_generator.py --no-cov` exit 0、 8 関数すべて green。 AI-05 着手前に必ず確認
- **`decoder_type` 値の固定**: `'mb_istft_1d'` (default) / `'istftnet2_mb_1d2d'` (新規) の **lower-snake 2 値**。 AI-05 で `__main__.py` に CLI `--decoder-type` を露出する際は**この 2 値を choices として hard-code**。 ハイフン区切り (`mb-istft-1d` 等) や camelCase は使わない
- **params target 0.83M ± 0.05M の根拠**: 計画 §4.6 の `target: 18ms (× 0.7)` を成立させるために必要な capacity 上限。 AI-05 学習中に `model.dec.parameters()` の合計を WandB に metric として送り、 0.88M 超過で early-stop して AI-03 担当に reconfigure 依頼
- **6lang base ckpt warm start パス**: `/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` (ONNX) ではなく **対応する `.ckpt`** を使う。 AI-05 では `--resume-from-multispeaker-checkpoint <path>` で読み込み、 strict=False ロード後に missing_keys を log。 本 test の `test_forward_1d2d_warm_start_key_compat` は synthetic state_dict での近似なので、 実 ckpt load 時に `conv_pre.*` / `cond.*` / `subband_conv_post.*` が missing に出ないことを再確認
- **ConvTranspose2d 0 件 invariant**: R7 mitigation。 AI-05 学習中に net 構造が WandB graph で送られるが、 そこに ConvTranspose2d が現れた場合は AI-03 実装にバグあり (pixel-shuffle が ConvTranspose2d に fallback している可能性)、 即時 AI-03 担当に escalation
- **PR #222 rebase 時の影響**: 本 test は PR #222 merge 後に `test_forward_1d2d_speaker_conditioning` が fail する可能性が高い (Multi-scale FiLM 4D 化が `_apply_film` を破壊するため)。 AI-17 (PR #222 merge 後の FiLM rank-aware 化) で本 test を**再 green** に持ち込むのが正規ルート。 本チケット完了時点では gin_channels=512 で fullband.shape[0] == 2 が green であることのみを保証
- **暫定 decoder_type default**: `'mb_istft_1d'` 維持。 PoC 評価 (AI-18 採否判定) で A-1 採用と決定するまで切り替えない。 リリース時の default 切替は別 PR + マイグレーションガイド更新が必要
- **contract 更新ロケーション**: 本チケットでは `audio-parity-contract.toml` に**触らない**。 AI-14 で `[istftnet2_mb_1d2d]` を別 section として併載。 AI-16 で PR #537 後の TF32 / bf16-mixed tolerance を反映

## 関連ドキュメント

- 親マイルストーン: [../milestones/M2-istftnet2-mb-backbone.md](../milestones/M2-istftnet2-mb-backbone.md)
- 親計画 §6 (Action Items): [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 親計画 §4.2 A-1 backbone 詳細 / §4.6 Benchmarks 目標値 / §3 Conflict Map / §7 Risk Register (R1, R6, R7) / §8 Immediate Next Steps 2 (TDD 先行指示)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) §2 A-1 / §2.5 Phase 4 Risk 評価 (Risk 1 中→低 / Risk 3 中→低)
- 統合改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) §A-1
- 既存 test (touch しない baseline contract): `src/python/tests/test_mb_istft_generator.py` / `test_mb_istft_utilities.py` / `test_main_mb_istft.py`
- 実装対象クラス (AI-03 で `decoder_type` 追加予定): `src/python/piper_train/vits/mb_istft.py:MBiSTFTGenerator` (L133-296)
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) (本チケットでは編集禁止、 AI-14 で `[istftnet2_mb_1d2d]` section 追加予定)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) (ORT session 仕様、 AI-13 で参照)
- 影響 PR:
  - [#222 Zero-shot TTS](https://github.com/ayutaz/piper-plus/pull/222) (HIGH conflict on `mb_istft.py`、 AI-17 で rebase 後対応)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04](https://github.com/ayutaz/piper-plus/pull/537) (test 側は NONE / pytest 9 deprecation のみ警戒)
- 論文: [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023, NTT)
