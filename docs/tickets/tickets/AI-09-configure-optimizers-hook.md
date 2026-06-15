# AI-09: configure_optimizers に `_collect_g_params` hook 追加

## メタ情報

- ID: AI-09
- 親マイルストーン: [M4](../milestones/M4-mswavehax-dual-vocoder.md)
- 工数見積: 1 日
- 依存チケット: AI-08 (MS-Wavehax vocoder 実装 + dual vocoder 統合)
- 後続チケット: AI-10 (MS-Wavehax vocoder-only FT 学習 30 epoch)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items AI-09 / §4.3 A-2 MS-Wavehax dual vocoder / §3 Conflict Map](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

本チケットは `VitsModel.configure_optimizers` の生成器側 (G) パラメータ収集ロジックを `_collect_g_params` という単独 hook 関数に切り出すことを目的とする。 これ自体は学習挙動を 1 bit たりとも変更しない純粋なリファクタリング (現行の `[p for p in self.model_g.parameters() if p.requires_grad]` を関数化するだけ) であり、 本チケットの真の意義は **AI-08 で追加された `self.dec_wavehax` sibling の trainable parameters を集約点 1 箇所で扱える形にして、 M6 / AI-17 (PR #222 rebase) における WavLM-D + DINO opt_d/opt_g 拡張との衝突を構造的に回避する** ことにある (計画 §3 Conflict Map の `lightning.py` 行が「MEDIUM (WavLM-D + DINO 拡張)」と評価された主因)。

上流の AI-08 は `models.py:754` 直後に `enable_wavehax` フラグ条件下で `self.dec_wavehax` を生やすが、 この parameters を AdamW に通すための分岐を直接 `configure_optimizers` 本体に書き込んでしまうと、 後続 PR #222 の「WavLM-D + DINO で opt_d 側に追加判別器を、 opt_g 側に DINO student head を加える」差分と同じ関数の同じ if 連鎖が肥大化し、 rebase 時に行単位 conflict が確実に発生する。 hook 化することで PR #222 rebase 時の差分は「集約関数の差分のみ」に局所化でき、 計画 §6 AI-09 が「PR #222 rebase 時の WavLM-D + DINO opt_d/opt_g 拡張と非衝突に保つ (B5 mitigation)」と要求している前提を満たす。

下流の AI-10 (vocoder-only FT) は `--enable-wavehax --freeze-acoustic --wavehax-lr 2e-4` の組み合わせで起動するが、 freeze-acoustic 下では `requires_grad=False` となった acoustic 系 parameters が自然に hook 内で除外される必要があり、 かつ `--wavehax-lr` で wavehax 部のみ別 LR を当てる余地を残しておく必要がある (本チケットでは LR group 分割は実装せず、 hook の return 形式を 「集約関数 + 任意で named group 化可能な構造」 として AI-10 が param_group 拡張で吸収できる設計に留める)。

## 実装内容の詳細

### 編集対象ファイル

- `/Users/s19447/Documents/piper-plus/src/python/piper_train/vits/lightning.py`
  - 編集関数: `VitsModel.configure_optimizers` (現行 L845-L892)
  - 新規 method: `VitsModel._collect_g_params` (instance method、 `self.model_g` と hparams を参照、 想定 ~25 LoC)
  - 既存 `freeze_dp` ロジック (L847-L857) は touch しない (AI-08 / AI-10 共通の前提)

### 新規構造の擬似コード

```python
def _collect_g_params(self) -> list[torch.nn.Parameter]:
    """Collect trainable parameters of the generator side (G).

    Stable extension point. Subclasses / rebase migrations append here.
    PR #222 rebase: insert `dec.spk_proj.parameters()` and any DINO student head.
    AI-08 dual vocoder: include `dec_wavehax.parameters()` when sibling present.

    Returns a flat list of trainable Parameters (filtered by requires_grad).
    """
    # 1) base generator
    params: list[torch.nn.Parameter] = [
        p for p in self.model_g.parameters() if p.requires_grad
    ]
    # 2) dual vocoder sibling (AI-08): only when enable_wavehax was passed at __init__
    #    NOTE: model_g.dec_wavehax の parameters は (1) の self.model_g.parameters()
    #          に既に含まれるため二重計上を避ける。 hasattr check は「sibling 構造
    #          が壊れていないかの sentinel」 として実行時 assert に流用する。
    if getattr(self.hparams, "enable_wavehax", False):
        assert hasattr(self.model_g, "dec_wavehax"), (
            "enable_wavehax=True だが model_g.dec_wavehax が未生成 (AI-08 統合点崩壊)"
        )
    return params

def configure_optimizers(self):
    # freeze_dp (既存) — touch しない
    freeze_dp = getattr(self.hparams, "freeze_dp", False)
    if freeze_dp:
        ...  # 既存ロジックそのまま

    # G optimizer
    gen_params = self._collect_g_params()

    # D optimizer (既存)
    d_params = list(self.model_d.parameters())
    if self.model_d_wavlm is not None:
        d_params = d_params + list(self.model_d_wavlm.parameters())

    optimizers = [
        torch.optim.AdamW(gen_params, ...),
        torch.optim.AdamW(d_params, ...),
    ]
    schedulers = [...]
    return optimizers, schedulers
```

### 既存 default 値 / 互換維持の制約

- `return optimizers, schedulers` の **return 構造 (`[opt_g, opt_d]` の 2 optimizer + 2 scheduler)** は不変。 M4 milestone の Exit Criteria 「`_collect_g_params` hook が PR #222 と非衝突」「`configure_optimizers` の最終 return shape を変えず」を満たす制約。
- `enable_wavehax` hparams が未定義の checkpoint (= 既存 6lang base ckpt, つくよみちゃん FT ckpt 等、 全既存配布物) から resume した場合に `getattr(..., False)` で従来挙動に落ちる (G-1.9 後方互換 gate)。
- gen_params の **計算結果** が `enable_wavehax=False` 時に旧コードと**完全に同一**であることを bit-exact assert する unit test を AI-09 で用意 (下記 Test Plan)。
- `freeze_dp` 既存ロジックとの干渉なし: `freeze_dp` は `model_g.named_parameters()` 上で `requires_grad=False` を立てるだけで、 hook 内の `if p.requires_grad` filter で自然に除外される。

### PR #222 / PR #537 との conflict 回避策

計画 §3 Conflict Map から:

> `src/python/piper_train/vits/lightning.py` — `_collect_g_params` hook、 wavehax LR / vs PR #222 = MEDIUM (WavLM-D + DINO 拡張) / vs PR #537 = LOW (bf16-mixed) / merge 順推奨 = **A-1/A-2 先行で hook 化**

- **PR #222 rebase 時**: WavLM-D + DINO 拡張で必要となる追加 parameters (`dec.spk_proj`, DINO student head 等) は `_collect_g_params` の return 直前に 1-2 行追加するだけで取り込める。 hook 化していない場合は `configure_optimizers` 本体の if 連鎖と既に存在する `freeze_dp` ブロックの**間**に挿入する必要があり、 行単位 conflict が確実に発生する。
- **PR #537 rebase 時**: TF32-on + bf16-mixed の影響は `AdamW(fused=torch.cuda.is_available())` の引数経路には現れない (LOW)。 ただし `fused=` の挙動が torch 2.11 で変化した場合は別 PR で追従し本チケットの diff に乗せない。
- **PR #222 と本チケットの 7 ランタイム ABI 同期**: 本チケットは Python 側のみの変更で 7 ランタイム ABI は一切触らない (lightning.py は推論ランタイムにバンドルされない)。 R4 / R6 の機械 check 対象外。

### 設定 default 値、 新規 CLI フラグ

- 新規 CLI フラグ: **なし** (本チケットでは追加しない)。 `--enable-wavehax` / `--freeze-acoustic` / `--wavehax-lr` は AI-08 / AI-10 が追加する想定 (M4 Deliverable §`__main__.py`)
- 設定 default: `enable_wavehax` hparams が未定義の場合に False 扱い (`getattr(..., False)`)

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|----------|---------|
| Lead Implementer (Python ML) | 1 | PyTorch Lightning、 `configure_optimizers` / `automatic_optimization=False` の手動最適化フロー、 freeze-dp 既存実装の理解 | `_collect_g_params` hook 切り出し、 既存 freeze_dp ロジック非干渉確認、 擬似コード通りの実装と PR body 記述 |
| Test Engineer (Python pytest) | 1 | pytest、 bit-exact tensor assertion、 PyTorch ckpt mock の組み立て、 `pl.LightningModule` のテスト用 stub 構築 | `test_configure_optimizers_hook.py` の新規追加、 `enable_wavehax=False` での gen_params bit-exact 比較、 freeze_dp 互換 test、 hasattr sentinel assert の verification |
| Reviewer (PR #222 rebase 計画担当) | 1 | PR #222 の WavLM-D + DINO 拡張差分の理解、 rebase dry-run の手順、 git rebase の interactive 経験 (本チケットでは `-i` は使わない、 dry-run のみ) | hook 化後の `configure_optimizers` に PR #222 の opt_g 追加 parameters と opt_d 追加 discriminator を dry-run で merge し、 衝突が「集約関数差分のみ」に収まることを PR body に記録 |

合計 3 名。 本チケットは 1d 見積もりだが、 hook 化のメリットを担保する Reviewer 役 (PR #222 dry-run 担当) が必須であり、 これを省くと 「hook を入れる動機」 が PR body に記述されず後続の M6 で再説明コストが発生する (M4 milestone の rethinking 第三節で指摘された review burden 問題への対応)。

## 提供範囲 (Scope)

### 含むもの

- `src/python/piper_train/vits/lightning.py` 内 `VitsModel._collect_g_params` 新規追加 (instance method、 ~25 LoC)
- 同ファイル `VitsModel.configure_optimizers` 内の gen_params 算出を `self._collect_g_params()` 呼び出しに置換 (1 行差分)
- `src/python/tests/test_configure_optimizers_hook.py` 新規追加 (~80 LoC、 6 関数想定)
- PR body への「PR #222 rebase dry-run 記録」 セクション (Reviewer 役の成果物、 markdown ベタ書き)

### 含まないもの (Out of Scope)

- `--enable-wavehax` / `--freeze-acoustic` / `--wavehax-lr` の CLI フラグ追加 — AI-08 / AI-10 で扱う
- wavehax 部に**別 LR group** を当てる実装 (`--wavehax-lr 2e-4` 対応の param_group 分割) — AI-10 で hook の return 形式を拡張する想定
- `_collect_d_params` の対称 hook 化 — PR #222 の WavLM-D + DINO 拡張差分が確定するまで不要 (本チケットでは G 側のみ)
- 7 ランタイム同期 — lightning.py は推論ランタイム非対象 (M5 / AI-13 でも触らない)
- `audio-parity-contract.toml` への新 variant 追加 — M5 / AI-14 で扱う
- `text_splitter.py` の touch — decoder-agnostic 維持 (R6 / 計画 §3 で編集禁止)
- WandB logging への新メトリクス追加 — 本チケットは学習挙動を変更しないため不要

## テスト項目

### Unit Tests

`src/python/tests/test_configure_optimizers_hook.py` (新規):

- `test_collect_g_params_returns_only_requires_grad`
  - assert: `_collect_g_params()` の返り値が `all(p.requires_grad for p in params)` を満たす
  - assert: 個数が `sum(1 for p in model_g.parameters() if p.requires_grad)` と一致
- `test_collect_g_params_bit_exact_with_legacy_inline` (regression guard、 G-1.9 後方互換 gate)
  - 既存の inline 式 `[p for p in self.model_g.parameters() if p.requires_grad]` の結果と `_collect_g_params()` の結果が **同一 id list** (Python `id()` ベース) で並ぶこと
  - assert: `[id(p) for p in legacy] == [id(p) for p in hook]`
- `test_collect_g_params_respects_freeze_dp`
  - `freeze_dp=True` で `configure_optimizers` を呼んだ後、 `_collect_g_params()` から DP parameters (name が `dp.` で始まるもの) が完全に除外されること
  - assert: `all(not n.startswith("dp.") for n, p in model_g.named_parameters() if p in hook_result)`
- `test_collect_g_params_enable_wavehax_sentinel_assert`
  - `hparams.enable_wavehax=True` かつ `model_g` に `dec_wavehax` が**ない** mock で `_collect_g_params()` を呼ぶと AssertionError が「AI-08 統合点崩壊」メッセージ付きで上がる
  - assert: `pytest.raises(AssertionError, match="dec_wavehax が未生成")`
- `test_configure_optimizers_return_shape_unchanged`
  - return が `(list[Optimizer], list[Scheduler])` の 2-tuple で、 各 list の長さが 2 (opt_g + opt_d / sched_g + sched_d)
  - assert: M4 Exit Criteria 「最終 return shape を変えず」 を機械 check
- `test_configure_optimizers_smoke_no_wavehax`
  - `enable_wavehax` hparams を**設定しない** legacy ckpt 相当の mock で `configure_optimizers()` が例外なく完走
  - assert: 既存 6lang base ckpt 互換性 (G-1.9 後方互換 gate)

既存 `src/python/tests/test_freeze_dp.py` は **touch しない** (G-1.9 既存テスト保護)。

### E2E Tests

- **1 epoch sanity (CSS10 JA)**: `uv run python -m piper_train --dataset-dir /data/piper/dataset-css10-ja-poc --max_epochs 1 --batch-size 4` を `enable_wavehax=False` (default) で起動し、 既存 baseline と loss 曲線・gradient norm が**完全一致**することを WandB run の hash 比較で確認 (bit-exact runs は seed 固定下で期待)。 ただし PyTorch の非決定性で完全一致しない場合は 1e-6 magnitude tolerance で対比。
- **AI-08 統合点 forward smoke (forward-only、 学習なし)**: AI-08 が完了した時点で `enable_wavehax=True` の mock ckpt を loading し `configure_optimizers()` → `_collect_g_params()` が AssertionError なく完走、 かつ gen_params 個数が legacy baseline + dec_wavehax parameters の合計と一致 (重複なく集約されていることを件数 sanity で check)。
- **PR #222 rebase dry-run** (Reviewer 役の成果物): `git checkout origin/pull/222/head; git rebase feat/decoder-istftnet2-mswavehax-poc` を local sandbox で実行し、 `lightning.py` の conflict が `_collect_g_params` 内の 1-2 行追加で resolve できることを PR body に記録 (実際の rebase commit は AI-17 で行う、 本チケットは dry-run のみ)。

### 受入基準 (Acceptance Criteria)

計画 §4.6 / M4 Exit Criteria から該当箇所:

- **return shape 不変**: `configure_optimizers` の返り値が `([opt_g, opt_d], [sched_g, sched_d])` 構造で、 M4 Exit Criteria 「最終 return shape を変えず」を満たす
- **bit-exact regression guard**: `enable_wavehax=False` で `_collect_g_params()` の結果が legacy inline 式と `id()` ベースで完全一致 (G-1.9 後方互換 gate)
- **freeze-dp 互換**: 既存 `test_freeze_dp.py` が全 green で残ること
- **PR #222 rebase 容易性**: dry-run で「集約関数差分のみ」に conflict が局所化されていることを PR body に記録 (M4 Exit Criteria 「rebase dry-run を AI-09 PR body に記録」)
- **既存 baseline 編集禁止**: `[mb_istft_1d]` audio-parity baseline 不変 (G-1.2 gate)、 本チケットは contract 自体を touch しないが、 1 epoch sanity が baseline と乖離した場合は失格

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

計画 §7 Risk Register から該当:

- **R6 (`audio-parity-contract.toml` baseline 誤書換)**: 本チケットは contract を編集しないが、 hook 化が結果として gen_params 順序を変えると optimizer state の persistence (checkpoint) で「同名同形 parameters なのに state 連携が外れる」 silent regression を招く可能性がある。 → 対策: `id()` ベースの順序一致を Unit Test で bit-exact 検証。
- **R5 (PR #537 TF32-on + bf16-mixed)**: `AdamW(fused=torch.cuda.is_available())` 経路は PR #537 merge 後の torch 2.11 で挙動変化の可能性がある。 → 対策: 本チケットでは fused= の引数自体は触らない。 PR #537 merge 後の検証は M6 / AI-16 に切り出す。
- **本チケット固有の懸念**: `getattr(self.hparams, "enable_wavehax", False)` が pl.LightningModule の `hparams` (Namespace or dict-like) の attr lookup 仕様に依存しているため、 pytest mock で `Namespace` ではなく plain dict を `hparams` に bind した場合に `getattr` が AttributeError を上げる可能性がある。 → 対策: Unit Test で `pl.utilities.parsing.AttributeDict` を明示的に作って bind。
- **本チケット固有の懸念 2**: `_collect_g_params` を method 化することで、 PR #222 で「DINO student head が `model_g.parameters()` に**含まれない** (別 module として attach される)」設計が採用された場合、 hook の `self.model_g.parameters()` だけでは集約漏れが発生する。 → 対策: hook の docstring で「`self.model_g.parameters()` 以外の trainable G 系 module は明示的に append する」 規約を明文化し、 PR #222 reviewer (AI-17 担当) への引き継ぎノートに記載。

### レビュー項目 (チェックリスト)

- [ ] default `enable_wavehax=False` (hparams 未定義) で gen_params が legacy inline 式と `id()` ベース bit-exact (G-1.9 後方互換)
- [ ] `[mb_istft_1d]` audio parity 不変 (G-1.2 baseline 編集禁止、 本チケットは contract touch しないことを差分で確認)
- [ ] ONNX I/O 不変 (lightning.py は ONNX export 経路に関与しないが、 念のため `export_onnx.py` への touch が無いことを差分で確認)
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響は M6 / AI-16 に切り出し、 本チケットの `fused=` 引数を変えない
- [ ] `configure_optimizers` の return が `([opt_g, opt_d], [sched_g, sched_d])` 構造 (M4 Exit Criteria)
- [ ] freeze_dp 既存ロジック (L847-L857) を **touch していない** ことを diff で確認
- [ ] `text_splitter.py` / `audio-parity-contract.toml` / 7 ランタイム source を **touch していない** (R4 / R6)
- [ ] PR #222 rebase dry-run が PR body に記録され、 conflict が「集約関数差分のみ」に局所化されることが確認済み
- [ ] `_collect_g_params` の docstring に 「`self.model_g.parameters()` 以外の trainable G 系 module は明示的に append する」 規約と PR #222 / AI-17 引き継ぎ要約を記載
- [ ] `test_configure_optimizers_hook.py` が 6 関数すべて green、 かつ `pytest src/python/tests/test_freeze_dp.py` が green を維持

## 一から作り直すとしたら (Ticket-level rethinking)

本チケットを一から設計するとしたら、 まず **「hook 化を AI-08 (vocoder 実装 + sibling 統合) と同一 PR に統合して 1 PR 3.5d」 にまとめる選択肢** を真剣に検討したい。 M4 milestone の rethinking 第三節でも同じ問題が指摘されているが、 1d 単独 PR は review 観点が「リファクタリングしただけ」に映りやすく、 hook 化の真の動機 (PR #222 rebase コストの局所化) を都度説明する必要が生じる。 一方で AI-08 に統合してしまうと「vocoder 実装の review」 と 「configure_optimizers リファクタリング review」 が混在し reviewer の認知負荷が上がるトレードオフがある。 現実解として現行案 (別チケット) を維持しつつ、 PR body の冒頭に **「AI-08 / AI-09 / AI-10 は一連の dual vocoder PoC で、 AI-09 は PR #222 rebase 計画の中核」** という framing を明示することで AI-08 単独レビュー時の文脈欠落を補う形を採るのが妥当だと思う。

次に、 **hook の粒度を変える選択肢**。 現行案は `_collect_g_params` のみを切り出すが、 対称に `_collect_d_params` も同時に hook 化して将来の PR #222 WavLM-D + DINO discriminator 拡張に備える設計もあり得る。 ただし計画 §6 AI-09 は明示的に G 側だけを要求しており、 D 側を先取りすると 「使われていない hook」 が増えて YAGNI に反する。 PR #222 が ready になった時点 (現状 DRAFT + 25 日 stale で判断不能) で D 側 hook を別チケットで切る方が現実的。 早期失敗指標としては 「hook 化後 1 epoch sanity が legacy baseline と loss 曲線で 1e-3 以上ドリフトする」 ことを set し、 これが観測されたら hook 内の filter ロジック (特に `if p.requires_grad`) が param 順序を silently 入れ替えた可能性を疑って `id()` ベースの順序一致テストに戻る、 というフローを採りたい。

第三に、 **完全 from-scratch で書く場合の trade-off**。 現行案は legacy inline 式を関数化するだけのミニマル変更だが、 もし 「**param_group ベース** で wavehax 部に別 LR を当てる設計まで本チケットで完了させる」 拡張案を採るなら 2.5d 程度に膨れる代わりに AI-10 の `--wavehax-lr 2e-4` 対応が「hook の戻り値を `list[dict]` (param_group 形式) に変えるだけ」で済む。 ただしこの拡張は AI-10 着手前に 「acoustic freeze 下で本当に別 LR が必要か」 を経験的に確認していない段階で先取り設計するリスクがあり、 計画 §6 AI-10 が「`--freeze-acoustic` で勾配計算が vocoder 部のみに局所化される」と述べていることから、 通常の単一 LR で十分機能する可能性が高い。 結果として 「現行 1d ミニマル変更 + AI-10 で必要なら param_group 拡張」 という段階的アプローチが現実解として妥当。 一から作るとしたら、 ミニマル変更案を採りつつ hook の docstring に 「**戻り値を `list[dict]` に変える形での将来拡張ポイント**」 を 1 行 TODO で残しておく形を採りたい。

## 後続タスクへの連絡事項

AI-10 (MS-Wavehax vocoder-only FT 学習 30 epoch) への引き渡し:

- **hook 関数名と signature**: `VitsModel._collect_g_params(self) -> list[torch.nn.Parameter]` (現行案、 AI-10 で param_group 拡張する場合は `-> list[torch.nn.Parameter] | list[dict[str, Any]]` のように union return に拡張する想定。 hook 内の docstring TODO に明記)
- **AI-10 で hook を拡張する場合の安全な編集箇所**: `_collect_g_params` の `return params` 直前で `if getattr(self.hparams, "wavehax_lr", None) is not None:` 分岐を追加し、 wavehax 部 (`self.model_g.dec_wavehax.parameters()`) を別 param_group に切り出す形にする。 base group は `params` (acoustic + その他) に集約、 wavehax group に `{"params": list(wavehax_p), "lr": wavehax_lr}` を append して `list[dict]` を返す。 `configure_optimizers` の AdamW 呼び出しは `AdamW([{"params": ...}], lr=base_lr, ...)` 形式を受け付けるため return 構造変更だけで動作する。
- **CLI フラグの追加位置**: AI-10 で `--enable-wavehax` / `--freeze-acoustic` / `--wavehax-lr 2e-4` を `__main__.py` の `add_model_specific_args` 経由で hparams に流す。 本チケットは CLI 追加しない。
- **既存 baseline ckpt パス (acoustic model freeze 用)**: AI-02 完了時の `/data/piper/output-css10-ja-1d-baseline/last.ckpt` を `--resume-from-multispeaker-checkpoint` 相当の経路で acoustic 部のみロード、 hook 内で `requires_grad=False` 化された acoustic は自然に hook の filter で除外される。
- **WandB project 名**: `piper-mswavehax-poc` (AI-10 で確定、 本チケットの 1 epoch sanity は既存 `piper-css10-ja-poc` に流す)
- **PR #222 rebase 計画のメモ**: hook 内 docstring の 「PR #222 rebase: insert `dec.spk_proj.parameters()` and any DINO student head」 コメントを M6 / AI-17 担当者は変更しない (rebase dry-run の根拠としての anchor)。 dry-run 結果 (本チケット PR body に記載予定) は AI-17 着手時に URL リンクで参照されることを想定。
- **暫定設定の明示**: 本チケットでは LR group 分割を実装しないため、 AI-10 で `--wavehax-lr 2e-4` を実装する際は **gen_params 全体に 1 つの LR が当たる現行構造を一旦壊さず**、 param_group 形式への移行は AI-10 内で完結させる (AI-09 PR を後追い修正しない)。

## 関連ドキュメント

- 親マイルストーン: [../milestones/M4-mswavehax-dual-vocoder.md](../milestones/M4-mswavehax-dual-vocoder.md)
- 親計画 §6: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 親計画 §3 Conflict Map: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md) (lightning.py 行: MEDIUM vs PR #222 / LOW vs PR #537)
- 親計画 §7 Risk Register: R4 / R5 / R6 (本チケット該当)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md) §A-2
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md) §2.5 Phase 4 Risk 評価
- 既存実装参照:
  - `src/python/piper_train/vits/lightning.py:845-892` (現行 `configure_optimizers`、 本チケットの編集対象)
  - `src/python/piper_train/vits/lightning.py:847-857` (現行 `freeze_dp` ロジック、 本チケットは **touch しない**)
  - `src/python/tests/test_freeze_dp.py` (既存テスト、 本チケットは **touch しない** が green 維持を確認)
- 影響 PR:
  - [#222 Zero-shot TTS (CAM++ + DINO)](https://github.com/ayutaz/piper-plus/pull/222) — WavLM-D + DINO opt_d/opt_g 拡張時に hook の「集約関数差分のみ」 で取り込み可能にする (M6 / AI-17)
  - [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537) — `AdamW(fused=)` の torch 2.11 挙動変化検証は M6 / AI-16 に切り出し
