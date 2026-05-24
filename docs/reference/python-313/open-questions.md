# Issue #527 未決事項 (Open Questions)

> 実装着手前に **stakeholder / 学習担当 / リポジトリオーナーで決める必要がある事項**を列挙する。 全てが解消した時点で M1 着手の go サインとする。

文書ID: PP-OQ-527
版: 1.0
適用: dev branch (Issue #527 完了まで)
最終更新: 2026-05-25

---

## サマリ (一覧)

| ID | カテゴリ | 質問 | 重要度 | 必要タイミング | 状態 |
|---|---|---|---|---|---|
| **OQ-01** | 運用前提 | 学習・推論サーバーの host driver R570+ アップグレードは誰が・いつやるか | **高** | M3 着手前 | 未決 |
| **OQ-02** | 運用前提 | nvidia-container-toolkit 1.14+ への bump は誰が確認するか | **高** | M3 着手前 | 未決 |
| **OQ-03** | 学習方針 | torch 2.2 → 2.11 で 6lang base ckpt が resume 不可だった場合のフォールバック (再学習 vs 維持) | **高** | M4 着手前 (smoke 失敗時) | ✅ **決定済 (2026-05-25): resume 非対応 (新規学習のみ対応)** |
| **OQ-04** | バージョニング | 本変更は v1.13.0 (minor) か v1.12.x (patch) か | **高** | M5 着手前 | ✅ **決定済 (2026-05-25): v1.13.0** |
| **OQ-05** | PR 分割 | M1 内で floor drift 統一を別 PR にするか 1 PR に混ぜるか | 中 | M1 着手前 | 未決 |
| **OQ-06** | PR 分割 | M3 と M4 を統合 PR にするか分離 PR にするか (DR-004 では分離が推奨) | 中 | M3 着手前 | 推奨案あり (分離) |
| **OQ-07** | CUDA patch | `nvidia/cuda:12.8.0` か `12.8.1` (or 最新 patch) | 中 | M3 着手前 | 推奨案あり (12.8.1) |
| **OQ-08** | スコープ判断 | `docker/cpp-dev/Dockerfile` の python3.12 → 3.13 統一を今やるか別 issue にするか | 低 | M1 着手前 | 別 issue 推奨 |
| **OQ-09** | スコープ判断 | `docker/cpp-inference/Dockerfile.distroless` の debian12 → debian13 統一を今やるか | 低 | M2 着手前 | 別 issue 推奨 |
| **OQ-10** | dependabot | CUDA 12.8 統一後の dependabot ignore policy 更新 | 低 | M5 後 | 未決 |
| **OQ-11** | CHANGELOG | breaking change 文言の正式版確定 | 中 | M5 着手前 | 草案あり |
| **OQ-12** | 検証 | TF32 enable を opt-in flag にするか default ON にするか | 中 | Phase 4 着手前 | 推奨案あり (default ON) |
| **OQ-13** | 検証 | bf16-mixed を CLAUDE.md Template の default にするか optional 推奨にとどめるか | 中 | Phase 4 着手前 | 推奨案あり (optional 推奨) |
| **OQ-14** | リリース | v1.12 系の旧 Docker image tag を registry に残すか削除するか | 中 (DR-006 で昇格) | M5 着手前 | ✅ **決定済 (2026-05-25): 残す** (DR-006 で旧 ckpt 継続学習者の唯一の選択肢) |

合計: **14 件** (高 4 / 中 7 / 低 3)

---

## 高優先度 (M1/M3/M4 着手の blocker)

### OQ-01: host driver R570+ アップグレード計画

**質問:** 学習サーバー (Ada 6000 + RTX 5090) / 推論サーバー (T4) の host NVIDIA driver を R570+ に bump する作業は **誰が、 いつ**やるか。

**コンテキスト:**
- RTX 5090 (Blackwell sm_120) は CUDA 12.8 wheel と driver R570+ が必須
- M3 (CUDA Docker 統一) の Entry Criteria に「host driver R570+ 確認済」 がある
- 現状の host driver version は把握できていない

**選択肢:**
- A. M1 着手と並行してサーバー管理者に依頼 (M3 開始時には完了想定)
- B. 学習担当が自分で bump (権限ある場合)
- C. M3 着手時にトリガーで bump (M3 が driver 待ちで blocked)

**推奨:** A (M3 開始前に確実に完了させる)

**決定すべき人:** リポジトリオーナー + サーバー管理者

---

### OQ-02: nvidia-container-toolkit 1.14+ への bump

**質問:** Docker host の `nvidia-container-toolkit` を 1.14+ に上げる作業は OQ-01 と同タイミングで対応可能か。

**コンテキスト:**
- CUDA 12.8 image を `--gpus all` で実行するには nvidia-container-toolkit 1.14+ が必要
- 1.10 以下では device mount で失敗するケースあり
- 通常 driver bump とセットで実施されるので OQ-01 と同タイミングで吸収可能

**選択肢:**
- A. OQ-01 と同時に対応 (推奨)
- B. 別タイミングで対応 (二度手間)

**推奨:** A

**決定すべき人:** サーバー管理者

---

### OQ-03: torch 2.2 → 2.11 ckpt resume 失敗時のフォールバック

**質問:** Phase 4 で 6lang base ckpt (`/data/piper/output-multilingual-6lang/`) を torch 2.11 環境で resume したときに失敗した場合、 どう対応するか。

**コンテキスト:**
- DR-001 (Fully-aligned 戦略) の前提として「torch 2.11 で既存 ckpt が lazy load できる」 を想定
- PyTorch upstream の互換ポリシーは「model weights は forward 互換、 optimizer state_dict は保証なし」
- 既存 piper-train は `--resume-from-multispeaker-checkpoint` で optimizer 破棄して再開する仕様 (CLAUDE.md Template B)
- それでも load 不可な場合の fallback が未定

**選択肢:**
- A. 6lang base を torch 2.11 環境で再学習 (75 epoch 規模、 1-2 週間)
- B. 旧 image (torch 2.2) で生成した ONNX のみ運用継続、 新 ckpt は torch 2.11 から作る (M3 完了後)
- C. torch 2.5 等の中間 version でブリッジ (複雑、 非推奨)

**推奨:** B (既存 ONNX 推論は不変、 新規学習のみ 2.11 に乗せる)

**決定すべき人:** 学習担当 + リポジトリオーナー

**✅ 決定 (2026-05-25): 過去 ckpt の resume は対応しない (B より大胆な選択)**

- torch 2.11 環境で旧 ckpt (torch 2.2 で生成) の resume は **保証しない・サポート対象外**
- 既存 ONNX (生成済) はランタイム側で推論継続 (forward 互換は ONNX レベルで成立)
- 新規学習は torch 2.11 環境で**スクラッチ or 新 ckpt 経由のみ**
- M4 の Entry Criteria から「6lang base ckpt の resume smoke」 を削除、 代わりに「新規学習 1 epoch smoke (Ada 6000 で from scratch、 もしくは torch 2.11 で新規生成した base からの FT)」 に置換
- 詳細は [`specifications.md DR-006`](specifications.md#dr-006-過去-ckpt-resume-非対応を許容) 参照

---

### OQ-04: バージョン番号 (v1.13.0 vs v1.12.x)

**質問:** 本変更は SemVer 上 minor bump (v1.12.0 → v1.13.0) か patch bump (v1.12.0 → v1.12.1) か。

**コンテキスト:**
- Docker base image / Python interpreter / torch version 全て変更 → ユーザ環境への影響大
- ただし PyPI `piper-plus` ランタイム API は無変更 (NFR-01 で 3.11 サポート維持)
- v1.11 → v1.12 の前回 breaking は Migration guide を伴った minor bump (`docs/migration/v1.11-to-v1.12.md`)

**選択肢:**
- A. **v1.13.0 (minor bump)** — Docker 利用者向け breaking として明示、 Migration guide 添付
- B. v1.12.1 (patch) — PyPI API 互換なので patch、 Docker 利用者は release note で周知

**推奨:** A (Docker 利用者にとって breaking 級の変更、 v1.13.0 にして Migration guide を添付)

**決定すべき人:** リポジトリオーナー

**✅ 決定 (2026-05-25):** **A. v1.13.0 (minor bump)** を採用。 Migration guide `docs/migration/v1.12-to-v1.13.md` を M5 で作成。 詳細は [`specifications.md DR-005`](specifications.md#dr-005-リリースバージョンは-v1130-minor-bump) 参照。

---

## 中優先度 (PR 構成判断)

### OQ-05: M1 内で floor drift 統一を別 PR にするか

**質問:** M1 (Phase 0 + 1) の 17 library floor 統一を、 同じ PR にするか分離するか。

**コンテキスト:**
- DR-002 で「M1 内で `chore(deps): unify floor pins` PR を別に切る選択肢あり (実装者判断)」 と記載
- 同じ PR にまとめると review 範囲が拡大 (3.11→3.13 と floor 統一の 2 軸)
- 別 PR にすると revert 可能性が独立

**選択肢:**
- A. 1 PR にまとめる (M1 全体を 1 commit chain で)
- B. 2 PR に分離 (`chore(deps): unify floor pins` を先に merge → 3.11→3.13 PR)

**推奨:** B (revert 単位の独立性、 review 集中)

**決定すべき人:** リポジトリオーナー (PR review style preference)

---

### OQ-06: M3 と M4 を統合 PR にするか分離 PR にするか

**質問:** M3 (CUDA Docker 統一) と M4 (新 GPU 学習最適化) を 1 PR にまとめるか分離するか。

**コンテキスト:**
- DR-004 で「分離推奨」 と決定済 (Phase 3 = infra、 Phase 4 = code + docs)
- ただし「実装者判断で統合 PR も可」 と余地を残している

**選択肢:**
- A. 分離 (M3 = infra PR、 M4 = optimization PR) — DR-004 推奨
- B. 統合 (1 つの大型 PR で M3 + M4)

**推奨:** A (DR-004 通り)、 ただし review 担当が同じで余裕があれば B も可

**決定すべき人:** リポジトリオーナー

---

### OQ-07: CUDA 12.8 の patch version 選択

**質問:** `nvidia/cuda:12.8.x-cudnn-runtime-ubuntu24.04` の `x` をどれにするか。

**コンテキスト:**
- 12.8.0 (初期) / 12.8.1 (bugfix) / より新しい minor patch が存在する可能性
- specifications.md FR-02-04 で「12.8.1 を選択」 と記載済 (草案)

**選択肢:**
- A. **12.8.1** (specifications.md 草案) — より bugfix が含まれる
- B. 12.8.0 — 最も保守的、 ただし bugfix なし
- C. 実装時の最新 12.8.x patch を選ぶ

**推奨:** C → A (実装時の最新を確認、 fallback で 12.8.1)

**決定すべき人:** 実装者 (大きな判断ではない、 M3 実装時に確定)

---

### OQ-11: CHANGELOG breaking 表記の文言

**質問:** CHANGELOG.md の `[1.13.0]` セクションに記載する breaking 表記の正式文言。

**コンテキスト:**
- M5 deliverable に「BREAKING: Docker now uses CUDA 12.8 + Ubuntu 24.04, requires host driver R570+」 と草案
- ユーザ migration 周知のため正確性が重要

**草案 (要レビュー):**

```markdown
### Breaking Changes

- **Default Docker images now require CUDA 12.8 + host NVIDIA driver R570+**
  (`docker/python-train/Dockerfile`, `docker/python-inference/Dockerfile`).
  Base image bumped from `nvidia/cuda:12.6.3-...-ubuntu22.04` to
  `nvidia/cuda:12.8.x-...-ubuntu24.04`. Hosts running NVIDIA driver R525 (12.6)
  or older will fail to start the new images. See
  [docs/migration/v1.12-to-v1.13.md](docs/migration/v1.12-to-v1.13.md).
- **Default Python interpreter inside Docker images is 3.13** (was 3.11).
  `requires-python = ">=3.11"` is unchanged; PyPI installs on Python 3.11/3.12
  remain supported. Only the Docker image default has shifted.
- **PyTorch wheel bumped from 2.2.1+cu121 to 2.11.0+cu128** in the training
  image (`docker/python-train/Dockerfile`). Existing 6lang base checkpoint
  loads successfully via `--resume-from-multispeaker-checkpoint`, but
  bit-exact reproducibility from torch 2.2.1 is not guaranteed.
- **distroless final images bumped from debian12 to debian13**
  (`docker/python-inference/Dockerfile.cpu.distroless`,
  `docker/webui/Dockerfile.distroless`). Internal Python paths shifted from
  `/usr/local/lib/python3.11` to `/usr/local/lib/python3.13`.
- **TF32 is now enabled by default in training** via
  `torch.backends.cuda.matmul.allow_tf32 = True`. This is a noop on sm_75
  and older GPUs (T4 included). For Ada Lovelace / Blackwell, matmul is
  ~1.3-1.5x faster but loses bit-exact reproducibility vs FP32.
```

**選択肢:**
- A. 上記草案をそのまま採用
- B. 修正 (具体的に指摘箇所)

**推奨:** A (修正があれば user 指示で adjust)

**決定すべき人:** リポジトリオーナー

---

### OQ-12: TF32 enable を opt-in にするか default ON にするか

**質問:** `torch.backends.cuda.matmul.allow_tf32 = True` を全 GPU で default ON にするか、 CLI flag (`--enable-tf32`) で opt-in にするか。

**コンテキスト:**
- specifications.md FR-08 では default ON で記載 (sm_75 以下は noop)
- TF32 は数値精度に影響 (matmul mantissa 23-bit → 10-bit)、 bit-exact reproducibility 喪失
- TTS workload では perceptual 影響なし (要 deterministic 用途では opt-out 必要)

**選択肢:**
- A. **default ON** (specifications.md 草案) — シンプル、 全ユーザに恩恵
- B. opt-in (`--enable-tf32` flag) — 既存挙動維持、 慎重派向け
- C. opt-out (`--disable-tf32` flag) — default ON だがフラグで OFF 可能

**推奨:** A (default ON、 deterministic 要件は別 issue で `--disable-tf32` 追加検討)

**決定すべき人:** リポジトリオーナー + 学習担当

---

### OQ-13: bf16-mixed を CLAUDE.md Template の default にするか

**質問:** CLAUDE.md Template A/B の `--precision` default を bf16-mixed に格上げするか、 16-mixed 据置で「Ada/Blackwell では bf16 推奨」 と注記のみとするか。

**コンテキスト:**
- specifications.md FR-09 では「default は据置 (16-mixed)、 docs で bf16 を新メイン推奨候補と記載」 と草案
- Template default 変更はサンプル学習ジョブの canonical 仕様変更に該当

**選択肢:**
- A. **default 据置 + 注記** (specifications.md 草案) — 既存学習との一貫性、 新 GPU 利用者が opt-in
- B. default を bf16-mixed に変更 — 新 GPU が主流になる前提、 古い GPU 利用者は opt-out
- C. GPU 自動検出 (Lightning の `precision="bf16-mixed-if-supported"` 等) — 複雑

**推奨:** A (Template 変更は慎重、 ユーザが明示的に bf16 を選ぶ形)

**決定すべき人:** リポジトリオーナー + 学習担当

---

## 低優先度 (実装中・後で決められる)

### OQ-08: `docker/cpp-dev/Dockerfile` python3.12 → 3.13

**質問:** dev tool 用 (python3.12 が入っている) を 3.13 統一の対象にするか。

**推奨:** **別 issue 推奨** (dev tool として動けば何でもよく、 Issue #527 のスコープ外)

**決定すべき人:** 実装者 (本 Issue 範囲に含めるかを M1 で判断)

---

### OQ-09: `docker/cpp-inference/Dockerfile.distroless` debian12 → 13

**質問:** Python 利用なし (C++ のみ) の distroless を debian13 に揃えるか。

**推奨:** **別 issue 推奨** (統一性のみが動機、 機能影響なし、 PR スコープを絞る)

**決定すべき人:** 実装者 (M2 で同時にやる選択肢もあり、 reviewer 判断)

---

### OQ-10: dependabot ignore policy の更新

**質問:** `.github/dependabot.yml` で `nvidia/cuda` minor bump を ignore しているが、 12.8 統一後はどうするか。

**コンテキスト:**
- 現状 `version-update:semver-minor` を ignore (line 263-265)
- 12.8 → 12.9 / 13.0 が出たときに自動 PR を出すか手動 bump 方針継続か

**選択肢:**
- A. 据置 (手動 bump 方針継続)
- B. ignore 解除 (12.x patch のみ自動 PR、 minor は手動)
- C. major のみ ignore (12.x → 13.x は手動、 12.8 → 12.9 は自動)

**推奨:** A (据置、 PR #427 の経緯通り)

**決定すべき人:** リポジトリオーナー

---

### OQ-14: v1.12 系の旧 Docker image tag を残すか削除するか

**質問:** Registry に push 済の v1.12.x Docker image tag を v1.13.0 release 後も保持するか。

**コンテキスト:**
- v1.12.x tag は CUDA 12.6 + Python 3.11、 一部の 3rd party ユーザが利用継続する可能性
- Registry storage コスト vs ユーザ移行ペース のバランス

**選択肢:**
- A. **残す** (推奨) — ユーザが任意のタイミングで移行、 storage コスト許容
- B. v1.13.0 release 後 N ヶ月で削除予告
- C. 即削除 (推奨しない、 ユーザ環境を壊す)

**推奨:** A (草案)

**決定すべき人:** リポジトリオーナー

**✅ 決定 (2026-05-25): A. 残す** — DR-006 により過去 ckpt 継続学習が v1.12 image に依存するため、 旧 image tag の保持は必須事項に格上げ。 削除予定は設定しない (長期保持)。

---

## 解決プロセス

### Phase 0 着手前 (今すぐ決めるべき)

- [ ] OQ-04: バージョン番号 (v1.13.0 vs v1.12.x)
- [ ] OQ-05: M1 内で floor drift 統一を別 PR にするか
- [ ] OQ-08: cpp-dev Dockerfile スコープ判断 (in / out)
- [ ] OQ-09: cpp-inference distroless スコープ判断 (in / out)

### M3 着手前 (Phase 3 開始前)

- [ ] OQ-01: host driver R570+ アップグレード完了
- [ ] OQ-02: nvidia-container-toolkit 1.14+ 確認完了
- [ ] OQ-06: M3 + M4 統合 vs 分離
- [ ] OQ-07: CUDA 12.8.x patch 選択

### M4 着手前 (Phase 4 開始前)

- [ ] OQ-03: ckpt resume 失敗時のフォールバック (smoke で NG だった場合のみ発動)
- [ ] OQ-12: TF32 default ON vs opt-in
- [ ] OQ-13: bf16-mixed Template default 化判断

### M5 着手前 (リリース前)

- [ ] OQ-11: CHANGELOG breaking 表記の正式版確定
- [ ] OQ-14: 旧 image tag 保持判断

### M5 後 (リリース後)

- [ ] OQ-10: dependabot ignore policy 更新

---

## 決定の記録方法

各 OQ-XX が決定したら:
1. 本ドキュメントの「状態」 列を `未決` → `決定済 (YYYY-MM-DD)` に更新
2. 大きな判断 (OQ-01〜04 等) は新規 ADR (DR-005, DR-006...) として [`specifications.md §10.6`](specifications.md#106-決定事項記録-decision-records) に追加
3. 関連する Phase / Milestone の Entry Criteria に決定を反映

---

## 関連ドキュメント

| 文書 | 内容 |
|---|---|
| [`requirements.md`](requirements.md) | 要求定義 (前提 A-XX、 制約 C-XX) |
| [`specifications.md`](specifications.md) | 要件定義 + ADR (DR-XX) |
| [`milestones.md`](milestones.md) | M1-M5 (Entry/Exit Criteria) |
| [`README.md`](README.md) | 実装計画 (Phase 別 diff) |

---

定義日: 2026-05-25
適用範囲: dev branch (Issue #527 完了まで)
版数: 1.0 (初版)
