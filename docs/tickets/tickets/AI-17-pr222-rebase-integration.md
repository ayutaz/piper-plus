# AI-17: PR #222 merge 後の FiLM rank-aware 化 + ONNX I/O 同期

## メタ情報

- ID: AI-17
- 親マイルストーン: [M6](../milestones/M6-pr-rebase-integration.md)
- 工数見積: 3 日
- 依存チケット: AI-16 (PR #537 merge 後の bf16-mixed + TF32-on 再 benchmark)、 **PR #222 merge**
- 後続チケット: AI-18 (採否判定レポート作成と統合 PR 提出)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-17 / §3 Conflict Map / §7 Risk Register R1+R4](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

PR #222 (Zero-shot TTS, CAM++ + DINO + Multi-scale FiLM) が dev に merge された後、 A-1 (iSTFTNet2-MB 1D-2D backbone) と A-2 (MS-Wavehax dual vocoder companion ONNX) を新 FiLM 構造に rebase 取込する。 計画 §6 AI-17 が要求する 3 つの差分 — (a) `_apply_film` の rank-aware 化 (1D=split dim=1 / 2D=split dim=1 維持 + spatial broadcast)、 (b) `cond_layers` の channel schedule を `decoder_type` 別に保持、 (c) ONNX I/O の `sid → speaker_embedding[192]` 変更を A-1 backbone と A-2 companion ONNX export 経路の両方で反映 — を 1 チケット内で完了させる。

本チケットは M6 の中核リスク R1 (HIGH/HIGH: PR #222 Multi-scale FiLM と A-1 1D-2D backbone の forward 構造 HIGH conflict) を正面突破する位置づけにある。 M2-M4 で `_forward_1d` / `_forward_1d2d` を分離済みのため forward 本体への侵襲はゼロだが、 `_apply_film` が channel-axis split (dim=1) 前提で書かれていると 4D ([B,C,F,T]) backbone で破綻する。 加えて R4 (MEDIUM/MEDIUM: A-2 companion ONNX と PR #222 の ONNX I/O 変更の二重同期) を「PR #222 既存 diff に乗せて 1 回で完了」 戦略で吸収する。

上流からは AI-16 で bf16-mixed + TF32-on tolerance に拡張された `audio-parity-contract.toml` と全 variant の 5 epoch sanity ログを受け取り、 PR #222 merge 後の `_apply_film` / `cond_layers` / ONNX I/O 仕様を fork して A-1/A-2 経路に同期する。 下流の AI-18 (採否判定) には rebase 後の audio-parity test green / 7 ランタイム smoke pairwise SNR≥30dB / 4 指標判定可能な状態を引き渡す。

## 実装内容の詳細

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/src/python/piper_train/vits/mb_istft.py`
  - `MBiSTFTGenerator._apply_film` (PR #222 で新規追加される想定の private method、 行範囲は merge 後に確定。 既存 `MBiSTFTGenerator.__init__` L133 周辺 + `_forward_1d` / `_forward_1d2d` 分岐との接点) を rank-aware 化
  - 1D 経路 (`x.shape == [B, C, T]`、 dim=1 split) は PR #222 既存挙動を完全保存
  - 2D 経路 (`x.shape == [B, C, F, T]`、 dim=1 split + F/T 方向 spatial broadcast) を新規追加
- `/Users/s19447/Documents/piper-plus/src/python/piper_train/vits/models.py`
  - `SynthesizerTrn.__init__` の `cond_layers` 構築箇所 (L754 周辺、 A-2 sibling 追加点と同位置) で `decoder_type` 別の channel schedule を保持
  - PR #222 が前提とする統一 channel schedule を default 経路として残し、 `decoder_type='istftnet2_mb_1d2d'` 時は 2D backbone 用の (C_in, C_mid, C_out) tuple を別途構築
  - A-2 `self.dec_wavehax` (sibling) への FiLM 入力経路も rank-aware 化済み `_apply_film` を共有
- `/Users/s19447/Documents/piper-plus/src/python/piper_train/export_onnx.py`
  - A-1 backbone export 経路で `sid → speaker_embedding[192]` 入力同期 (PR #222 既存 diff に追従)
  - A-2 companion ONNX (`tsukuyomi.wavehax.onnx`) export 経路も同一 I/O 契約に固定
  - `--decoder-branch wavehax` フラグ経路で companion ONNX 専用の input_names / output_names を維持
- `/Users/s19447/Documents/piper-plus/src/rust/piper-core/src/synth.rs` ほか 6 ランタイム inference 入口 (Rust / Go / C# / WASM / C++ / C-API) — PR #222 既存 diff に乗る形で 1 回完了。 本チケットでは PR #222 が既に変更済みの sid→speaker_embedding[192] 経路に A-1/A-2 専用 wrapper (Rust `new_with_wavehax` / Go option pattern / C-API 新 entry) を整合させる

### 新規ファイル

- `/Users/s19447/Documents/piper-plus/src/python/tests/test_film_rank_aware.py` (~120 LoC)
  - `_apply_film` の 1D / 2D 両 rank に対する形状・値域テスト
  - PR #222 既存 `test_zero_shot_film.py` (1D 専用) と非衝突に保つ
- `/Users/s19447/Documents/piper-plus/src/python/tests/test_onnx_io_sync_a1_a2.py` (~80 LoC)
  - A-1 backbone + A-2 companion ONNX 双方が `speaker_embedding[192]` を input_names に持つことの assert

### 既存 default 値 / 互換維持の制約 (G-1.9 / G-1.2)

- **G-1.9 後方互換 gate:** `decoder_type` default は `'mb_istft_1d'` 不変。 PR #222 既存の 1D 経路 `_apply_film(x: [B,C,T], gamma_beta)` を **完全に温存** し、 2D 経路は新規分岐として追加するのみ
- **G-1.2 baseline 編集禁止 gate:** `audio-parity-contract.toml` の `[mb_istft_1d]` section は触らない。 AI-16 で拡張された `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` の tolerance のみで PR #222 後の数値を吸収する
- **ONNX I/O 不変原則の精密化:** A-1/A-2 PoC 段階では「ONNX I/O 不変」 を維持してきたが、 本チケットで PR #222 既存 diff の `sid → speaker_embedding[192]` 変更に **意図的に追従** する。 これは PR #222 と本ブランチの I/O 整合を「1 回で完了」 させる R4 mitigation の核心である

### PR #222 / PR #537 conflict 回避策

計画 §3 Conflict Map から該当行を引用:

> `mb_istft.py` | A-1 backbone 1D-2D 化、 `_forward_1d2d` 追加 | **HIGH** (Multi-scale FiLM 衝突) | NONE | **A-1 先行**、 PR #222 rebase で FiLM rank-aware 化
> `models.py` | `dec_wavehax` sibling 追加、 `decoder_type` 受領 | **HIGH** (spk_proj 統合点) | NONE | **A-1/A-2 先行**で隔離
> `export_onnx.py` | A-1 Conv2d export、 `--decoder-branch wavehax` | MEDIUM (ONNX I/O 変更) | NONE | A-1/A-2 先行、 PR #222 rebase で I/O 同期
> 7 ランタイム inference | A-2 companion ONNX load、 ABI 互換維持 | **HIGH** (PR #222 sid→speaker_embedding[192]) | LOW | **PR #222 と同時 sync** (二重同期回避)

- **vs PR #222 (本チケット中核):** `_apply_film` rank-aware 化と `cond_layers` channel schedule 分岐を PR #222 既存 diff の上から追加する。 PR #222 既存 1D test (`test_zero_shot_film.py` 等) は完全 green 維持を絶対条件とし、 本チケットの差分は 2D 経路に限定する
- **vs PR #537:** AI-16 で既に ubuntu-24.04 + py3.13 + torch 2.11 + bf16-mixed sandbox を通過済み。 本チケットでは tolerance 拡張の前提に乗るのみで再 benchmark しない

### 設定 default 値、 新規 CLI フラグ

- `decoder_type` default: `'mb_istft_1d'` 不変 (G-1.9)
- 新規 CLI フラグなし (本チケットは既存 `--decoder-branch wavehax` / `--enable-wavehax` を再利用)
- `export_onnx.py` の入力名 default は PR #222 既存値 `speaker_embedding` に追従

### 疑似コード スケッチ (rank-aware `_apply_film`)

```python
def _apply_film(
    self,
    x: torch.Tensor,           # [B, C, T] (1D) or [B, C, F, T] (2D)
    gamma: torch.Tensor,       # [B, C] (rank-agnostic)
    beta: torch.Tensor,        # [B, C]
) -> torch.Tensor:
    if x.dim() == 3:
        # 1D path (PR #222 既存挙動を完全保存)
        return gamma.unsqueeze(-1) * x + beta.unsqueeze(-1)
    elif x.dim() == 4:
        # 2D path (本チケットで新規追加)
        # gamma/beta は F/T 方向に broadcast
        return (
            gamma.unsqueeze(-1).unsqueeze(-1) * x
            + beta.unsqueeze(-1).unsqueeze(-1)
        )
    else:
        raise ValueError(f"_apply_film: unsupported rank {x.dim()} (expected 3 or 4)")
```

```python
# models.py: cond_layers の decoder_type 別 channel schedule
if decoder_type == "istftnet2_mb_1d2d":
    cond_schedule = ((192, 256), (256, 128), (128, 64))  # 2D backbone 用
else:
    cond_schedule = ((192, 192), (192, 192), (192, 192))  # PR #222 既存 (1D 用)
self.cond_layers = nn.ModuleList(
    [nn.Linear(in_c, out_c) for in_c, out_c in cond_schedule]
)
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Lead Implementer (ML / FiLM) | 1 | PyTorch / FiLM conditioning / VITS-2 / `torch.einsum` & broadcast | `_apply_film` rank-aware 化、 `cond_layers` channel schedule 分岐、 1D / 2D 両経路の数値検証 |
| ONNX Engineer | 1 | ONNX opset 15 / torch.onnx.export dynamic_axes / Conv2d export / op set audit | A-1 backbone + A-2 companion ONNX の `speaker_embedding[192]` 入力同期、 export 後 op 列の visual diff、 `--decoder-branch wavehax` 経路維持 |
| Runtime Integration Engineer | 1 | Rust trait / Go option pattern / C# named arg / C-API ABI / WASM exports | 7 ランタイム入口での `speaker_embedding[192]` 受領を PR #222 既存 diff に整合、 A-1/A-2 専用 wrapper (Rust `new_with_wavehax` 等) の ABI 互換維持、 pairwise SNR ≥ 30 dB の continuity 検証 |
| Test Engineer | 1 | pytest / hypothesis / parametrize / pytest 7&9 両対応 | `test_film_rank_aware.py` 新規、 `test_onnx_io_sync_a1_a2.py` 新規、 PR #222 既存 1D test の non-regression 監視、 audio-parity test の green 維持 |

4 名構成。 本チケットは「PR #222 merge」 という外部 event をトリガーとするため、 4 名は PR #222 merge の見込みが立った時点で同時アサインし、 merge 当日から並走着手する想定。

## 提供範囲 (Scope)

### 含むもの

- `mb_istft.py` の `_apply_film` を rank-aware (1D split dim=1 / 2D split dim=1 + spatial broadcast) に拡張
- `models.py` の `cond_layers` channel schedule を `decoder_type` 別に保持 (default 経路は PR #222 既存挙動完全保存)
- `export_onnx.py` の A-1 backbone export と A-2 companion ONNX export 経路で `sid → speaker_embedding[192]` 入力同期
- 7 ランタイム inference (Rust / Go / C# / WASM / C++ / C-API) の入力 spec 同期 (PR #222 既存 diff に乗る形)
- `test_film_rank_aware.py` 新規 (1D / 2D 両 rank の単体テスト)
- `test_onnx_io_sync_a1_a2.py` 新規 (ONNX input_names assert)
- `audio-parity-contract.toml` の `[istftnet2_mb_1d2d]` / `[mswavehax]` section が PR #222 後も green であることを test で確認 (tolerance 値の変更はしない、 AI-16 で確定済み)

### 含まないもの (Out of Scope)

- **`[mb_istft_1d]` baseline section の編集** — G-1.2 baseline 編集禁止 gate (AI-14 / AI-15 で機械 check 済み)
- **tolerance 値の再計算** — AI-16 で bf16-mixed + TF32-on 環境向けに確定済み
- **PR #537 関連の再 benchmark** — AI-16 で完了済み (本チケットは前提として利用するのみ)
- **採否判定レポート作成** — AI-18 で扱う (本チケットはあくまで「採否判定可能な状態」 を作るところまで)
- **新 epoch 学習** — 既存 AI-05 / AI-10 / AI-07 ckpt を流用、 PR #222 後の再学習は AI-18 採否判定で必要と判明した場合のみ別途実施
- **FiLM 以外の PR #222 機能 (CAM++ / DINO / emb_g 削除)** — PR #222 既存実装をそのまま乗せるのみ、 本チケットで触らない
- **`text_splitter.py` / `text-splitter-contract.toml`** — decoder-agnostic 維持 (G-1.x 系列、 計画 §4.3)

## テスト項目

### Unit Tests

- `src/python/tests/test_film_rank_aware.py::test_apply_film_1d_unchanged`
  - assert: `_apply_film(x_1d, gamma, beta)` の出力が PR #222 既存実装 (1D 専用版) と数値完全一致 (`torch.allclose(rtol=0, atol=0)`)
  - 入力: `x_1d.shape == [2, 192, 100]`, `gamma.shape == beta.shape == [2, 192]`
- `src/python/tests/test_film_rank_aware.py::test_apply_film_2d_shape`
  - assert: `_apply_film(x_2d, gamma, beta).shape == x_2d.shape` (`[2, 192, 4, 100]`)
- `src/python/tests/test_film_rank_aware.py::test_apply_film_2d_broadcast_correctness`
  - assert: 出力の `[b, c, f, t]` 値が `gamma[b, c] * x[b, c, f, t] + beta[b, c]` と数値一致 (`rtol=1e-6, atol=1e-7`)
- `src/python/tests/test_film_rank_aware.py::test_apply_film_invalid_rank_raises`
  - assert: rank 2 / rank 5 の入力に対して `ValueError` を raise
- `src/python/tests/test_film_rank_aware.py::test_cond_layers_schedule_decoder_type_branch`
  - assert: `decoder_type='mb_istft_1d'` で `cond_layers[0].in_features == 192` (PR #222 既存値)
  - assert: `decoder_type='istftnet2_mb_1d2d'` で `cond_layers[0].in_features == 192` かつ `out_features == 256` (2D 用)
- `src/python/tests/test_onnx_io_sync_a1_a2.py::test_a1_backbone_onnx_input_names_includes_speaker_embedding`
  - assert: A-1 backbone export の ONNX `input_names` に `'speaker_embedding'` が含まれる、 `'sid'` が含まれない
  - assert: `speaker_embedding` の shape が `[1, 192]` (PR #222 既存仕様)
- `src/python/tests/test_onnx_io_sync_a1_a2.py::test_a2_companion_onnx_input_names_sync`
  - assert: A-2 companion ONNX (`tsukuyomi.wavehax.onnx`) も同じ I/O 契約を持つ
- 既存 PR #222 `test_zero_shot_film.py` の全 case は **touch しない** (G-1.9 後方互換 gate)
- 既存 `test_mb_istft_generator.py` も **touch しない** (G-1.2 baseline 編集禁止 gate)

### E2E Tests

- **A-1 backbone 学習 resume sanity (1 epoch):**
  ```
  uv run --no-sync python -m piper_train \
      --dataset-dir /data/piper/dataset-css10-ja-poc \
      --resume-from-multispeaker-checkpoint /data/piper/output-istftnet2-mb-poc/last.ckpt \
      --decoder-type istftnet2_mb_1d2d \
      --max_epochs 1 --batch-size 4 --accelerator gpu --devices 1
  ```
  - assert: 1 epoch 完走 (loss NaN なし、 grad explosion なし)、 WandB audio log で出力 wav が `[1, 1, T]` 形状
- **A-2 companion ONNX export round trip:**
  ```
  uv run --no-sync python -m piper_train.export_onnx \
      /data/piper/output-istftnet2-mb-poc/last.ckpt \
      out/istftnet2-mb-rebased.onnx --decoder-branch wavehax
  ```
  - assert: ONNX export 成功、 `out/istftnet2-mb-rebased.wavehax.onnx` の companion file が `speaker_embedding[1,192]` を input に持つ
  - assert: onnxruntime で load → run → 出力 shape `[1, 1, T]` float32
- **7 ランタイム pairwise SNR (`audio-parity-contract.toml` 検証):**
  - Python anchor (AI-12 で生成済みの `/tmp/ai12_samples/`) と Rust / Go / C# / WASM / C++ / C-API の合成結果を pairwise 比較
  - assert: 全 6 pair で SNR ≥ 30 dB (計画 §4.6)
- **README canonical 環境再現:** Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs で `istftnet2_mb_1d2d` p50 が `expected_p50_ms ± 3ms` (AI-16 で確定済みの値)
- **WandB audio log:** rebase 後 1 epoch sanity の出力 wav 5 サンプルを WandB へアップロードし聴感品質を人間 review

### 受入基準 (Acceptance Criteria)

計画 §4.6 / §5 / §6 AI-17 から該当数値を引用:

- **UTMOS proxy MOS** (200 test utt、 PR #222 後 environment): rebase 前 (AI-16 完了時) ± 0.05 以内 (rebase で品質劣化なし)
- **CPU RTF p50** (Xeon E5-2650 v4 / 25 phoneme 英文 / warmup 5 + 30 runs): `istftnet2_mb_1d2d` < 20ms (計画 §4.6 target)
- **params**: 0.83M ± 0.05M (PR #222 後も保持、 `cond_layers` schedule 変更で params 増減があれば再 assert)
- **7 ランタイム smoke**: 全 7 で `[1, 1, T]` float32 / pairwise SNR ≥ 30 dB
- **audio-parity test green**: `uv run --no-sync pytest src/python/tests/test_audio_parity.py --no-cov` が全 variant pass
- **PR #222 既存 1D test green**: `test_zero_shot_film.py` 等が完全 non-regression
- **既存 `test_mb_istft_generator.py` green**: G-1.2 baseline 編集禁止 gate (touch せず pass)
- **ONNX op coverage**: A-1 backbone export の op set が Conv2d / Reshape / Transpose / Conv1d / iSTFT 系のみで構成され、 PR #222 後の新 op (DynamicQuantize 等) が混入していない

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から関連項目:

- **R1 (HIGH/HIGH): PR #222 Multi-scale FiLM と A-1 1D-2D backbone の forward 構造 HIGH conflict** — 本チケットの中核リスク。 `_apply_film` を rank-aware に拡張する差分のみで吸収する戦略を採るが、 PR #222 の Multi-scale FiLM が「scale 軸」 という別次元の concept を `cond_layers` 列で表現している場合、 本チケットの 2 引数 (gamma, beta) シグネチャでは表現不足になる可能性がある。 mitigation: PR #222 merge 直後に `_apply_film` のシグネチャと内部実装を読み込み、 `cond_layers` の戻り値が `(gamma, beta)` の単一 pair か `[(gamma_s, beta_s) for s in scales]` の list か事前確認、 後者なら本チケットを 2 PR (rank-aware 化 + multi-scale 化) に分割する判断を AI-18 着手前に行う
- **R4 (MEDIUM/MEDIUM): A-2 companion ONNX と PR #222 の ONNX I/O 変更の二重同期** — 「1 回完了」 戦略を本チケットで実行する。 mitigation: companion ONNX も同 contract に固定し、 Rust new_with_wavehax / Go option pattern / C-API 新 entry の ABI 互換性を維持しつつ I/O 変更だけを差分として乗せる。 本チケット完了時に 7 ランタイム全てで pairwise SNR ≥ 30 dB を確認することが必須
- **ONNX op set 微妙な drift:** PR #222 が emb_g 削除 + Flow dilation 1→2 で「速度面の op 構成」 を変えている可能性。 mitigation: `export_onnx.py` 経由で生成した ONNX を `onnxruntime` の `get_inputs()` / `get_outputs()` で op 列を visual diff 化し、 期待外の op (DynamicQuantize / GatherND など) が混入していないことを目視 + CI で確認
- **`cond_layers` channel schedule の memory footprint 増:** `decoder_type='istftnet2_mb_1d2d'` で `(192, 256), (256, 128), (128, 64)` のような拡張 schedule を採る場合、 params が +0.05M を超える可能性。 mitigation: params 上限 `0.83M ± 0.05M` を pytest で assert、 超過した場合は `cond_layers` の隠れ次元を縮小して再構成
- **PR #222 既存 1D test の non-regression が暗黙の breakage を見逃す可能性:** PR #222 が 200 epoch 再学習未実施で merge された場合、 既存 test の数値 tolerance が緩く、 本チケットの `_apply_film` 改造が silently 1D 経路の挙動を変えている可能性。 mitigation: PR #222 既存 1D test に加えて `_apply_film` 単体の `torch.allclose(rtol=0, atol=0)` test を `test_film_rank_aware.py::test_apply_film_1d_unchanged` で追加し byte-for-byte 一致を強制

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換、 `decoder_type='mb_istft_1d'` default)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止、 `audio-parity-contract.toml` 該当 section に書き込まない)
- [ ] ONNX I/O 同期は PR #222 既存 diff に乗る形 (本チケットで `sid` を別 entry として残さない、 二重同期回避)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響は AI-16 で audio-parity-contract tolerance に反映済み (本チケットでは再反映しない)
- [ ] `_apply_film` 1D 経路が PR #222 既存実装と byte-for-byte 一致 (`torch.allclose(rtol=0, atol=0)`)
- [ ] PR #222 既存 1D test (`test_zero_shot_film.py` 等) を touch せず全 case pass
- [ ] 既存 `test_mb_istft_generator.py` を touch せず pass (G-1.2)
- [ ] `cond_layers` schedule 変更で params が 0.83M ± 0.05M を超えない (計画 §4.2)
- [ ] A-1 backbone + A-2 companion ONNX 両方が `speaker_embedding[192]` を input に持つ
- [ ] 7 ランタイム入口 (Rust / Go / C# / WASM / C++ / C-API) の入力受領が PR #222 既存 diff に整合 (新規 ABI surface を増やさない)
- [ ] `_apply_film` の rank 判定が `x.dim()` ベース (`isinstance` でなく) で書かれ、 torch.jit / torch.onnx export 経路で trace 可能
- [ ] PoC 段階で touch しないと宣言した `text_splitter.py` / `text-splitter-contract.toml` に変更が入っていない

## 一から作り直すとしたら (Ticket-level rethinking)

採用案は「PR #222 が merge された後で `_apply_film` を rank-aware 化する差分を A-1/A-2 ブランチに当てる」 という追従型である。 これは計画 §3 Conflict Map の戦略 (A-1 先行 → PR #222 後の FiLM rank-aware 化のみで吸収) を素直に実装したものだが、 代替案として「**`_apply_film` を最初から rank-aware に書いた fork 版を A-1 着手時点 (AI-03) で作っておき、 PR #222 merge 時に upstream の 1D 版と merge する**」 案が考えられる。 これは PR #222 merge 当日の改修時間を短縮できる利点があるが、 「PR #222 の Multi-scale FiLM が実装される前の API 表面」 と「merge 後の表面」 が大きく異なる場合、 fork 版が無駄になるリスクがある。 PR #222 が 25 日 stale で実装表面が固まっていない現状 (計画 §2.1) では、 採用案 (追従型) のほうが投機実装の手戻りを避けられる。

代替案 2 として **「FiLM 自体を `decoder_type` 別に独立 module 化」** (`MBiSTFTFilm1D` / `MBiSTFTFilm2D` の 2 class 化) が考えられる。 これは rank 判定を class 選択で表現するため `_apply_film` 内の `if x.dim() == 3` 分岐を削除でき、 torch.jit trace の安定性が増す。 ただし PR #222 既存 1D 経路が `MBiSTFTGenerator._apply_film` を直接呼んでいる場合、 2 class 化のリファクタリングが PR #222 の test を破壊する可能性が高い。 採用案 (rank 判定 1 関数) のほうが PR #222 既存 surface を保存できる点で保守的に優れる。

代替案 3 として **「7 ランタイム ABI 同期を本チケットから切り離し独立 PR 化」** が考えられる。 これは reviewer の cognitive load を「FiLM rank-aware 化」 と「ONNX I/O 同期」 に分離でき、 review 品質が上がる。 ただし R4 mitigation の核心 (「PR #222 既存 diff に乗せて 1 回完了」) と矛盾するため、 採用案 (1 チケット 4 タスク詰め込み) のほうが二重同期回避の戦略整合性が高い。 ただし PR #222 が ONNX I/O 同期を含んだまま merge されない場合 (`speaker_embedding[192]` 変更を別 PR に切り出されるケース) は、 採用案を即座に分割 PR に切り替える escape hatch が必要。 AI-18 着手前にこの判断を行う前提で本チケットの scope を固定する。

採用案を 「現実解」 として位置づけ、 別案の利点 (代替 1 の事前準備 / 代替 2 の module 独立 / 代替 3 の PR 分離) は本チケットの制約 (PR #222 が固まらない / PR #222 既存 surface 保存 / R4 mitigation 整合) と相反するため捨てた。 PR #222 merge 当日の状況次第で escape hatch を発動する余地は AI-18 採否判定に残す。

## 後続タスクへの連絡事項

AI-18 (採否判定レポート作成と統合 PR 提出) に引き渡す具体的成果物:

- **rebase 後 ckpt パス (仮置き):**
  - `/data/piper/output-istftnet2-mb-poc-rebased/last.ckpt` (A-1 backbone、 PR #222 後の 1 epoch sanity 経由 ckpt、 学習延長は AI-18 採否判定で決定)
  - `/data/piper/output-mswavehax-poc-rebased/last.ckpt` (A-2 companion)
- **rebase 後 ONNX パス (仮置き):**
  - `out/istftnet2-mb-rebased.onnx` (A-1 backbone、 `speaker_embedding[192]` 入力)
  - `out/istftnet2-mb-rebased.wavehax.onnx` (A-2 companion、 同 I/O 契約)
- **暫定 decoder_type default:** `'mb_istft_1d'` 不変。 リリース時に `'istftnet2_mb_1d2d'` に切替えるかは AI-18 採否判定 PR で決定する
- **audio-parity-contract.toml の状態:** `[istftnet2_mb_1d2d]` / `[mswavehax]` section は AI-16 で確定済みの bf16-mixed + TF32-on tolerance のまま、 PR #222 後も green を維持できていることを確認済み (本チケットで再 calibrate しない)
- **7 ランタイム ABI 同期完了状態:** 全 7 で `speaker_embedding[192]` 入力受領 + A-1/A-2 専用 wrapper (Rust `new_with_wavehax` / Go option pattern / C# named arg / C-API 新 entry) が PR #222 既存 diff に整合。 AI-18 の 4 指標判定では「7 ランタイム smoke」 を本状態で測定する
- **PR #222 既存 1D test の non-regression 確認済み:** AI-18 で「A-1 採用判断時の 1D 経路の安全性」 を主張する根拠として、 本チケットで `test_zero_shot_film.py` 等が green であることを記録
- **escape hatch 発動状況:** 採用案 (1 チケット 4 タスク詰め込み) のまま完了したか、 代替 3 (7 ランタイム ABI 同期を分離) に切替えたかを AI-18 PR body に明記
- **PR #222 rebase 時に AI-18 で再確認すべき箇所:**
  - `_apply_film` のシグネチャが Multi-scale 対応に拡張されていないか (R1 mitigation の事前確認結果)
  - `cond_layers` schedule の params 増加が `0.83M ± 0.05M` 範囲内に収まっているか
  - ONNX op set audit (Conv2d / Reshape / Transpose / Conv1d / iSTFT のみ) に新 op が混入していないか
- **採否判定 4 指標の入力データ:** UTMOS proxy MOS / CPU RTF p50 / ONNX op coverage / 7 ランタイム smoke の 4 指標を AI-12 で確立した `metrics.json` schema で出力し、 AI-18 がそのまま判定表に流し込めるようにする

## 関連ドキュメント

- 親マイルストーン: [../milestones/M6-pr-rebase-integration.md](../milestones/M6-pr-rebase-integration.md)
- 親計画 §6 AI-17 / §3 Conflict Map / §7 R1+R4: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査統合: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Decoder Upgrade deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) (§2.5 Phase 4 Risk 評価)
- 前提チケット: [AI-16](AI-16-pr537-rebase-benchmark.md) (PR #537 merge 後の再 benchmark)
- 後続チケット: [AI-18](AI-18-adoption-report.md) (採否判定と統合 PR 提出)
- 関連 spec:
  - [`docs/spec/audio-parity-contract.toml`](../../spec/audio-parity-contract.toml) — `[istftnet2_mb_1d2d]` / `[mswavehax]` section の green 維持対象 (本チケットでは編集しない)
  - [`docs/spec/ort-session-contract.toml`](../../spec/ort-session-contract.toml) — bf16-mixed 環境での ORT session 設定継続性
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/pull/222) — 本チケットの merge 依存先、 FiLM Multi-scale 化 + ONNX I/O `sid → speaker_embedding[192]` 変更
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — AI-16 で吸収済み、 本チケットでは前提として利用
- 論文:
  - [arXiv 2308.07117](https://arxiv.org/pdf/2308.07117) iSTFTNet2 (Kaneko et al., Interspeech 2023, NTT)
  - FiLM 原典: Perez et al., "FiLM: Visual Reasoning with a General Conditioning Layer", AAAI 2018
