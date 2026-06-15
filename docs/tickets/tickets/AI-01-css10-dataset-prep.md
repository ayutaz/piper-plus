# AI-01: CSS10 JA データセット取得 + 前処理

## メタ情報

- ID: AI-01
- 親マイルストーン: [M1](../milestones/M1-css10-ja-dataset.md)
- 工数見積: 0.5 日
- 依存チケット: なし
- 後続チケット: AI-02 (baseline 学習元), AI-03 (warm start), AI-06 (FLY-TTS 並走)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画 §: [§6 Action Items / §4.1 PoC 設計](../../research/implementation-plan-a1-a2-2026-06-16.md)

## タスク目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) と A-2 (MS-Wavehax dual vocoder) の PoC 評価対象データセットを確定する起点タスクである。 親計画 §6 Milestone 1 / §4.1 dataset: CSS10 JA に記載のとおり、 Kyubyong/css10 Japanese subset (約 14h、 シングルスピーカー、 22050Hz) を `/data/piper/dataset-css10-ja-poc/processed/` に train 6,200 / val 200 / test 200 utt の三分割で配置し、 後段の AI-02 (1D baseline 50 epoch)、 AI-03 (1D-2D backbone 実装) のテスト基盤、 AI-06 (FLY-TTS 並走) の共通入力となる成果物を提供する。

CSS10 JA を選定する根拠は親計画 §4 にあり、 6lang base ckpt との phoneme set 互換性を保ちながら「1 GPU で 50 epoch を 1.5 日で回せる」 footprint に収まる最小規模であること、 および CLAUDE.md Template B が前提とする `--samples-per-speaker 4` / `--batch-size 4` / `--base_lr 2e-5` をそのまま流用できることに尽きる。 本チケットは GPU 不要 (前処理は CPU only) のため PR #222 / #537 の merge 待ちなしに即時着手可能 (§8 Immediate Next Steps 1 番目)。

本チケットは「データ整備」 のみに範囲を限定し、 学習成果物の生成 (baseline ckpt) は AI-02 に分離している。 これは M1 内のクリティカルパスを「整備完了 → 即 baseline 学習着手」 と「整備完了 → 即 AI-03 (M2) / AI-06 (M3) の実装着手」 が並走できるよう設計してあるためで、 本タスク完了時点で 3 系統 (M1 baseline / M2 1D-2D / M3 FLY-TTS) すべてが同一データセットを参照する形になる。

## 実装内容の詳細

新規ファイル生成および既存スクリプトの呼び出しが中心で、 piper_train 本体コードへの編集は一切発生しない (PR #222 / #537 との conflict ゼロ)。

### 編集対象 / 利用対象ファイル

| 区分 | パス | 用途 |
|------|------|------|
| 既存スクリプト呼び出し | `src/python/piper_train/tools/prepare_multilingual_dataset.py` | LJSpeech 形式正規化 + 22050Hz リサンプル + lid 付与 |
| 既存スクリプト呼び出し | `src/python/piper_train/tools/add_prosody_features.py` | 16dim prosody (a1/a2/a3) npz 抽出 |
| 新規 (任意、 ~80 LoC) | `src/python/piper_train/tools/fetch_css10_ja.py` | Kyubyong/css10 Japanese subset DL + checksum verify + raw 配置 |
| 新規 (任意、 ~40 LoC) | `src/python/piper_train/tools/split_css10_ja_poc.py` | metadata.csv を train/val/test = 6200/200/200 で確定 split |
| 新規テスト | `src/python/tests/test_css10_ja_prep.py` | split 比率 / prosody shape / phoneme set 包含の契約検証 |

### 新規ディレクトリレイアウト

```text
/data/piper/dataset-css10-ja-poc/
├── raw/                          # Kyubyong/css10 ja subset 原音源 (約 14h、 リサンプル前)
│   ├── meian/
│   ├── gongitsune/
│   └── transcript.txt
└── processed/                    # LJSpeech 形式、 22050Hz、 lid=0 固定
    ├── metadata.csv              # filename|text|phoneme_ids|speaker_id=0|lid=0
    ├── dataset.jsonl             # 学習側が直接読む形式
    ├── config.json               # sample_rate=22050 / num_symbols / lang_code=ja
    ├── wavs/                     # 22050Hz mono WAV
    ├── spec/                     # cached mel-spec npz
    ├── prosody/                  # 16dim a1/a2/a3 npz (AI-03 1D-2D backbone 入力)
    └── splits/
        ├── train.txt             # 6,200 lines
        ├── val.txt               # 200 lines
        └── test.txt              # 200 lines
```

### 既存 default 値 / 互換維持の制約

- `prepare_multilingual_dataset.py` は既存の multilingual 経路と完全に互換 (`--single-speaker` で speaker_id を 0 に固定するのみ、 phoneme set / config schema は 6lang base ckpt と同一を維持)。 これにより AI-02 の `--resume-from-multispeaker-checkpoint` 経路が成立する。
- `add_prosody_features.py` の prosody_dim=16 は CLAUDE.md Template B のデフォルトと一致 (`--prosody-dim 16`)。 AI-03 の 1D-2D backbone は backbone 入力 shape を変えないため prosody 次元も同一で良い。
- `noise_scale` は本タスクでは扱わない (学習・推論側の責務、 AI-02 / AI-05 で `noise_scale=0.667` 明示固定)。

### PR #222 / #537 との conflict 回避策

親計画 §3 Conflict Map から本チケット該当行を抜粋すると、 9 ターゲットファイルのうち本タスクで触るのは tools 配下のスクリプトおよび `src/python/tests/` のみで、 vs PR #222 / vs PR #537 ともに **NONE**。 ただし以下を予防的に守る:

- `src/python_run/piper/text_splitter.py` は **編集禁止** (decoder-agnostic 維持、 §3 表 6 行目)。 データセット前処理側からも参照しない。
- `audio-parity-contract.toml` の `[mb_istft_1d]` section は触らない (G-1.2 baseline 編集禁止 gate、 R6 mitigation)。 本タスクは contract には一切手を入れない (M5 / AI-14 の責務)。
- 6lang base ckpt パス `/data/piper/output-multilingual-6lang-mb-istft/` は CLAUDE.md 記載のまま参照。 ckpt のコピーや改変は禁止 (PR #222 merge 後の resume 不能リスク R2 の予防)。

### CLI 実行スケッチ

```bash
# 1. raw 取得 (checksum verify)
uv run python -m piper_train.tools.fetch_css10_ja \
    --output-dir /data/piper/dataset-css10-ja-poc/raw

# 2. LJSpeech 形式正規化 + 22050Hz リサンプル + lid=0
uv run python -m piper_train.tools.prepare_multilingual_dataset \
    --input-dir /data/piper/dataset-css10-ja-poc/raw \
    --output-dir /data/piper/dataset-css10-ja-poc/processed \
    --language ja --single-speaker --resample 22050 \
    --speaker-id 0 --lid 0

# 3. 16dim prosody (a1/a2/a3) 抽出
uv run python -m piper_train.tools.add_prosody_features \
    --dataset-dir /data/piper/dataset-css10-ja-poc/processed \
    --prosody-dim 16

# 4. train/val/test = 6200/200/200 split (deterministic seed=42)
uv run python -m piper_train.tools.split_css10_ja_poc \
    --dataset-dir /data/piper/dataset-css10-ja-poc/processed \
    --train 6200 --val 200 --test 200 --seed 42

# 5. 1 epoch sanity (AI-02 着手前の health check)
uv run python -m piper_train \
    --dataset-dir /data/piper/dataset-css10-ja-poc/processed \
    --prosody-dim 16 --accelerator gpu --devices 1 --precision 32-true \
    --max_epochs 1 --batch-size 4 --samples-per-speaker 4 \
    --quality medium --no-wavlm --audio-log-epochs 1 \
    --default_root_dir /tmp/css10-ja-sanity
```

## エージェントチームの役割と人数

| 役割 | 人数 | 必要スキル | 責任範囲 |
|------|-----|-----------|---------|
| Data Engineer | 1 | Python / librosa / pyopenjtalk-plus / shell | Kyubyong/css10 DL スクリプト、 22050Hz リサンプル、 LJSpeech 形式正規化、 split deterministic seed 固定、 disk 占有 ~8.3 GB 範囲管理 |
| QA / Test Engineer | 1 | pytest / numpy / 6lang phoneme set | `test_css10_ja_prep.py` 新規作成、 split 比率 / prosody 16dim shape / phoneme set 6lang 互換性の契約検証、 1 epoch sanity の WandB audio log 確認 |
| Domain Expert (日本語音声) | 1 (review-only) | 音声収録 SN 比 / phoneme coverage の感覚 | CSS10 JA の本/朗読タイトル別の収録ばらつき、 句読点分布、 prosody (a1/a2/a3) の極端値検出を review 視点で確認、 後段 MOS 評価への影響を事前 flag |

GPU 不要 (CPU only)、 wall-clock 0.5 日想定のため小規模チーム。 Data Engineer がメイン実装、 QA が並走で test 作成、 Domain Expert は完了直前の review として 1-2 時間関与する形が想定。

## 提供範囲 (Scope)

### 含むもの

- `/data/piper/dataset-css10-ja-poc/raw/` への Kyubyong/css10 Japanese subset (約 14h) DL + checksum verify
- `/data/piper/dataset-css10-ja-poc/processed/` への LJSpeech 形式正規化 (22050Hz / mono / lid=0 / speaker_id=0)
- `metadata.csv` / `dataset.jsonl` / `config.json` / `wavs/` / `spec/` / `prosody/` の生成
- train 6,200 / val 200 / test 200 utt の deterministic split (seed=42)
- 16dim prosody (a1/a2/a3) npz 抽出
- `src/python/tests/test_css10_ja_prep.py` での split 比率 / prosody shape / phoneme set 包含の契約検証
- 1 epoch sanity 実行 (WandB audio log 確認まで)
- 前処理コマンドの再現用 README (M1 worklog 末尾に追記)

### 含まないもの (Out of Scope)

- 50 epoch baseline 学習および ckpt 生成 → AI-02 の責務
- `mb_istft.py` / `models.py` などの本体コード編集 → AI-03 (1D-2D backbone) / AI-08 (wavehax 統合) の責務
- `audio-parity-contract.toml` への新 section 追加 → AI-14 (M5) の責務
- 7 ランタイム ABI 同期 / smoke test → AI-13 (M5) の責務
- FLY-TTS 用 dataset スキーマ拡張 (PQMF 無し用 spec cache) → AI-06 (M3) 側で必要なら追補
- JSUT Basic5000 等の追加データセット整備 (本 PoC では CSS10 JA で確定)

## テスト項目

### Unit Tests

- `src/python/tests/test_css10_ja_prep.py::test_split_ratio_exact`
  - assert: train.txt の行数 == 6200、 val.txt == 200、 test.txt == 200、 三者の集合に重複 0、 和集合 == metadata.csv 全体
- `src/python/tests/test_css10_ja_prep.py::test_split_deterministic_with_seed`
  - assert: seed=42 で 2 回 split を回したときに train/val/test の line set が完全一致 (set 比較で intersection == union)
- `src/python/tests/test_css10_ja_prep.py::test_prosody_npz_shape_16dim`
  - assert: 任意の 10 utt サンプルで `prosody/<id>.npz` の shape が `[T_phoneme, 16]` であること、 a1/a2/a3 のいずれの index も nan / inf を含まないこと
- `src/python/tests/test_css10_ja_prep.py::test_phoneme_set_compatibility_6lang`
  - assert: `processed/config.json` の `num_symbols` および phoneme id map が 6lang base config (`/data/piper/output-multilingual-6lang-mb-istft/config.json`) の subset であること (CSS10 JA は ja のみだが phoneme set の id schema を共有)
- `src/python/tests/test_css10_ja_prep.py::test_sample_rate_and_mono`
  - assert: `wavs/` 配下の任意 5 wav が sample_rate == 22050 / channels == 1 / dtype == int16
- `src/python/tests/test_css10_ja_prep.py::test_lid_speaker_id_constant`
  - assert: `dataset.jsonl` の全行で `lid == 0` かつ `speaker_id == 0`
- 既存 `test_mb_istft_generator.py` は touch しない (G-1.9 後方互換)

### E2E Tests

- 1 epoch sanity (smoke): `uv run python -m piper_train --dataset-dir ... --max_epochs 1` が exit code 0 で終了し、 WandB run の `media/audio/*` artifact が 1 件以上 log されていること
- disk 占有チェック: `du -sh /data/piper/dataset-css10-ja-poc/processed` が 7.5 〜 9.0 GB の範囲に収まる (~8.3 GB の許容幅)
- 6lang ckpt resume dry-run: `--resume-from-multispeaker-checkpoint <6lang-ckpt> --max_epochs 1` で起動時の emb_g 除去 + emb_lang 補正ログが両方出ること (R2 の予防的検査)
- 受入の数値目標は本タスクでは benchmark 系を含まない (親計画 §4.6 の数値目標は AI-02 以降で測定)。 本タスクは「データセット契約」 のみが対象

### 受入基準 (Acceptance Criteria)

親計画 §5 Milestone 1 Exit Criteria から本チケット該当分を抜粋:

- `/data/piper/dataset-css10-ja-poc/processed/` 配下に train 6,200 / val 200 / test 200 utt の split が存在し、 disk 占有 ~8.3 GB
- `uv run python -m piper_train --dataset-dir ... --max_epochs 1` で 1 epoch sanity が完走し、 WandB に audio sample が log される
- 上記 6 件の unit test がすべて green
- `decoder_type='mb_istft_1d'` (現行 default) で 6lang base ckpt から resume 起動可能であること (1 epoch dry-run のログで確認)
- `audio-parity-contract.toml` を 1 文字も編集していないこと (`git diff docs/spec/audio-parity-contract.toml` が空)

## 懸念事項とレビュー項目

### 懸念事項 (リスク)

親計画 §7 Risk Register から本チケット該当分を引用 + 細目:

- **R2 (HIGH likelihood / MEDIUM impact):** PR #222 の emb_g 完全削除で 6lang base ckpt が将来 resume 不能になる懸念。 本タスクは PR #222 merge 前の現行 dev で前処理を実施するためデータ側は影響しないが、 後段 AI-02 の `--resume-from-multispeaker-checkpoint` の成否を 1 epoch dry-run で予防確認しておく
- **R6 (MEDIUM likelihood / HIGH impact):** `audio-parity-contract.toml` の baseline regression を誤って書き換えるリスク。 本タスクは contract 一切 touch せず、 PR checklist で `git diff docs/spec/audio-parity-contract.toml` が空であることを mechanical check
- **R8 (MEDIUM likelihood / LOW impact):** GPU 競合は本タスクでは無関係 (CPU only)、 ただし `prepare_multilingual_dataset.py` の spec cache 生成が CPU 数十分 〜 1 時間程度かかるため並列度 (`--num-workers`) の妥当性を Data Engineer が事前確認
- CSS10 JA 独自リスク: 朗読タイトル別 (`meian` / `gongitsune` 等) で SN 比 / 句末イントネーションにばらつきがあり、 split が偏ると prosody 統計が train/val 間で乖離する可能性 → seed=42 + stratified split (タイトル比率を train/val/test で均等化) で予防
- pyopenjtalk-plus の OpenJTalk 辞書バージョン依存: 6lang base ckpt 学習時と異なる辞書バージョンを使うと phoneme set id map が drift する → `requirements.txt` の `pyopenjtalk-plus` バージョン pin を CLAUDE.md / pyproject.toml と一致させる
- disk 占有見積もり超過: cached spec が想定 (~8.3 GB) を超えるケース (mel hop / win 設定が default と異なる場合) → e2e の disk check で flag

### レビュー項目 (チェックリスト)

- [ ] default decoder_type 不変 (G-1.9 後方互換) — 本タスクは config を生成するのみ、 `decoder_type` フィールドは config に含めない (AI-03 で追加)
- [ ] [mb_istft_1d] audio parity 不変 (G-1.2 baseline 編集禁止) — `audio-parity-contract.toml` への変更がないこと
- [ ] ONNX I/O 不変 (PR #222 二重同期回避) — 本タスクは ONNX を扱わないため自動的に満たす
- [ ] PR #537 merge 後の TF32 / bf16-mixed 影響を audio-parity-contract tolerance に反映済み — 本タスクの責務外 (AI-16 で対応)。 ただし 1 epoch sanity の precision は `32-true` 固定で実施し PR #537 merge 前後の数値差を排除
- [ ] `src/python_run/piper/text_splitter.py` を 1 文字も編集していないこと (decoder-agnostic 維持)
- [ ] 6lang base ckpt パス (`/data/piper/output-multilingual-6lang-mb-istft/`) を copy / 改変していないこと (R2 予防)
- [ ] `pyopenjtalk-plus` バージョンが 6lang base ckpt 学習時と一致 (phoneme set id map drift 防止)
- [ ] split が deterministic (seed=42 で再現可能) であり、 朗読タイトル別の stratified サンプリングを採用していること
- [ ] WandB run URL を M1 worklog 末尾に追記済みであること
- [ ] CLAUDE.md の「学習済みモデル」 表に虚偽の更新を行っていないこと (本タスクで新モデルは生成しない)

## 一から作り直すとしたら (Ticket-level rethinking)

データセット選定を一から問い直すなら、 CSS10 JA (シングル × 14h、 CC0、 朗読) ではなく **JSUT Basic5000 (シングル × 10h、 スタジオ収録、 高 SN 比)** を第一候補に置く案は十分検討に値する。 CSS10 JA は無償 CC0 のため CI で都度 DL してもライセンス上の摩擦が無い反面、 録音 SN 比は 30-35 dB 程度であり、 後段 UTMOS proxy MOS で baseline ± 0.1 圏内を判定する際の「データセット由来の天井」 を狭める可能性がある。 PoC の目的が「A-1 backbone 置換が baseline 等価以上か」 を 50 epoch という短期間で判定することである以上、 baseline 自体のヘッドルームを高めるなら JSUT を採るのが筋であり、 CSS10 JA を採用したのはあくまで「CI で都度 DL 可能 / 6lang phoneme 互換 / CC0」 の運用簡便性を優先した妥協と理解しておくべきである。 もし 2 GPU 確保かつ wall-clock に余裕があるなら JSUT で baseline / CSS10 JA で phoneme coverage 補強の 2 段構えが品質判定 sensitivity の点で優位。

前処理アプローチについても再考の余地が大きい。 現計画は既存 `prepare_multilingual_dataset.py --single-speaker` を流用するが、 これは「多言語前提のスクリプトをシングルに退化させる」 形であり、 内部で不要なコードパス (lang_balanced sampling 等) を回避するためのフラグ管理が将来発生するリスクを抱える。 代替として `tools/prepare_css10_ja_poc.py` を 100 行程度の薄いスクリプトとして独立化する案もあり、 後者は再現性とドキュメント簡潔性で勝るが、 multilingual パイプライン側の進化 (例: 新 prosody dim) と drift するリスクを抱える。 6lang ckpt resume を成功させる前提なら現計画の「既存スクリプト流用」 が phoneme set 一致を機械的に保証する点で正しいが、 もし PoC を「6lang 系列から独立した実験ライン」 として走らせる思想なら独立スクリプト化のほうが clean。 ここでは「6lang base ckpt warm start を成功させる」 ことを優先しており、 既存スクリプト流用が現実解。

split 設計を再考するなら、 現計画の deterministic seed=42 + train 6200 / val 200 / test 200 は「再現性」「6lang base config との num_symbols 共有」 の点で堅いが、 朗読タイトル別 (`meian` / `gongitsune` / `kokoro` 等) の SN 比 / 話速ばらつきを stratified に均等化していない案が残っている (現計画の文面上は seed 固定の random split を示唆)。 もし integration-first で進めるなら、 まず非 stratified で 1 epoch sanity を回し、 val/test 間の prosody 統計差が閾値以上ならば stratified 化に切り替えるという段階的アプローチが現実的であり、 これは TDD アプローチ (`test_css10_ja_prep.py` を先に書く) と並走可能。 完全 from-scratch 設計なら、 朗読タイトルを「talk-id」 として扱い speaker_id とは別軸の secondary id にする選択もあり得るが、 6lang phoneme set との互換性を崩すコストが高いため採用しない。 採用した現実解は「6lang 互換 phoneme set 維持 + deterministic seed 固定 + stratified 化は事後判断」 の保守的ライン。

## 後続タスクへの連絡事項

本チケット完了時点で次の成果物と注意点を AI-02 / AI-03 / AI-06 に引き渡す:

- **dataset 共通パス (AI-02 / AI-03 / AI-06 全員):** `/data/piper/dataset-css10-ja-poc/processed/`
  - 三分割 split (train 6,200 / val 200 / test 200) は contract として後続でも変更しない
  - `lid=0` 固定 (CSS10 JA はシングル言語、 6lang コード ja=0 を流用)
  - `speaker_id=0` 固定 (シングルスピーカー)
- **raw 配置 (再生成用):** `/data/piper/dataset-css10-ja-poc/raw/` + `transcript.txt`
- **config.json (phoneme set id map):** 6lang base ckpt と互換、 `num_symbols` は 6lang config の subset
- **prosody dim:** 16 (`--prosody-dim 16`)、 npz shape `[T_phoneme, 16]` で AI-03 1D-2D backbone の入力にもそのまま使用
- **noise_scale 暫定値:** AI-02 / AI-05 / AI-07 で `noise_scale=0.667` 明示固定 (PR #222 default 変更影響を排除、 M1 連絡事項より転送)
- **WandB run URL (sanity 1 epoch):** 本チケット完了時に M1 worklog 末尾に追記、 AI-02 はこの run の audio sample を 50 epoch 学習の比較対照に使用可
- **6lang base ckpt resume 元 (AI-02 が直接利用):** `/data/piper/output-multilingual-6lang-mb-istft/` (CLAUDE.md §現在の状態 記載のまま、 本タスクで copy / 改変しない)
- **AI-03 への注意:** 本データセットは backbone 非依存 (raw 音声 + phoneme ids + prosody)。 1D-2D backbone は spec の shape 変換のみで対応、 dataset スキーマ追加は不要
- **AI-06 への注意:** FLY-TTS は PQMF 不使用 / sub-band loss 無効 (`--c-sub-stft 0.0`) のため spec cache の hop / win は変える必要があるかもしれない。 本タスクの spec/ は MB-iSTFT 系前提なので、 FLY-TTS 用にもし別 spec cache が必要なら `processed/spec_fly/` を AI-06 側で追加生成する想定 (本タスクでは生成しない)
- **PR #222 / #537 状況スナップショット:** 本チケット完了時の両 PR の status (DRAFT / OPEN、 mergeable) を M1 worklog にスナップショット記録、 M6 (AI-16 / AI-17) rebase 戦略の起点
- **`audio-parity-contract.toml` 未編集確認:** 本タスクで contract には一切手を入れていない。 M5 (AI-14) で `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` を新 section として併載する形で書き込む

## 関連ドキュメント

- 親マイルストーン: [../milestones/M1-css10-ja-dataset.md](../milestones/M1-css10-ja-dataset.md)
- 親計画 §6 / §4.1: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive (backbone / vocoder 詳細): [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- CLAUDE.md Template B (single-speaker FT) — AI-02 学習コマンドの母型、 本タスクのデータセット契約と一致
- 既存前処理スクリプト: `src/python/piper_train/tools/prepare_multilingual_dataset.py`、 `src/python/piper_train/tools/add_prosody_features.py`
- 既存仕様 (本タスクでは編集しない): [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml)、 [../../spec/text-splitter-contract.toml](../../spec/text-splitter-contract.toml)
- 6lang base ckpt 配置: `/data/piper/output-multilingual-6lang-mb-istft/` (CLAUDE.md §現在の状態)
- 影響 PR: [#222 Zero-shot TTS](https://github.com/ayutaz/piper-plus/pull/222) / [#537 Python 3.13 + CUDA 12.8 + Ubuntu 24.04 統一](https://github.com/ayutaz/piper-plus/pull/537)
- Kyubyong/css10 オリジナル: [github.com/Kyubyong/css10](https://github.com/Kyubyong/css10)

## Worklog

### 2026-06-16 — skeleton-pass landed

スケルトン実装が dev ブランチに着地。 後続の data-prep 実行ステップ (GPU/network/disk 必要分) を未完 TODO として明示記録する。

**landed (skeleton scope):**

- `src/python/piper_train/tools/fetch_css10_ja.py` — argparse + `download_archive` / `extract_archive` / `verify_layout` 関数シグネチャ。 `CSS10_JA_URL` / `CSS10_JA_SHA256` / `EXPECTED_HOURS=14.0` の定数定義。 実 DL は `NotImplementedError` で gate 済み (network 不要)
- `src/python/piper_train/tools/split_css10_ja_poc.py` — 6200/200/200 deterministic split を pure-Python で完全実装 (skeleton 段階で動作)、 `--seed 42`、 `--stratify-by-title` フラグ (default off)
- `src/python/tests/test_css10_ja_prep.py` — 6 contract assertions (split ratio / determinism / prosody 16-dim / 6lang phoneme set 互換 / 22050Hz mono / lid==0 & speaker_id==0)。 FS 依存テストは `/data/piper/dataset-css10-ja-poc/processed/` 不在時 skip、 split-logic 2 件は 6,600 件 synthetic fixture で即時実行
- `BASE_6LANG_CONFIG = "/data/piper/output-multilingual-6lang-mb-istft/config.json"` 定数を test 側に pin

**piper_train core への編集なし** (G-1.2 / G-1.9 / audio-parity-contract 不変条件は自動的に満たす)。

**残 TODO (本スケルトン外、 training host 上で実行):**

- [ ] Kyubyong/css10 Japanese subset の DL + SHA256 確定 (`fetch_css10_ja.py` の URL / SHA pin を実値に置換、 ~8.3 GB compressed)
- [ ] `prepare_multilingual_dataset.py --single-speaker` で 22050Hz LJSpeech 正規化 + spec cache 生成 (CPU 数十分〜1h)
- [ ] `add_prosody_features.py` で 16-dim prosody npz 生成 (`pyopenjtalk-plus` バージョンは 6lang base ckpt と一致確認)
- [ ] `split_css10_ja_poc.py --seed 42` で `splits/{train,val,test}.csv` 出力 (skeleton 実装で即実行可)
- [ ] 1 epoch sanity 学習 (`uv run python -m piper_train --max_epochs 1 ... --precision 32-true`) で 6lang base ckpt resume dry-run + WandB audio sample 確認
- [ ] WandB run URL を本 Worklog 末尾に追記
- [ ] disk occupancy 7.5-9.0 GB 範囲内であることを `du -sh processed/` で確認

**Blockers (parent agent への返し):** network DL / CPU 前処理 / GPU sanity run はすべて GPU 訓練ホスト依存のため、 本セッションでは skeleton 着地までで一旦完。
