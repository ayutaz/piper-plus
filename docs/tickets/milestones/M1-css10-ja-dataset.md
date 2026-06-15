# M1: CSS10 JA PoC データセット整備

## メタ情報

- ID: M1
- 期間見積: 0.2 週
- 依存マイルストーン: なし
- 含まれるチケット: [AI-01](../tickets/AI-01-css10-dataset-prep.md), [AI-02](../tickets/AI-02-baseline-training.md)
- ステータス: TODO
- ブランチ: feat/decoder-istftnet2-mswavehax-poc
- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md §5](../../research/implementation-plan-a1-a2-2026-06-16.md)

## フェーズの目的とゴール

A-1 (iSTFTNet2-MB 1D-2D backbone) と A-2 (MS-Wavehax dual vocoder) の PoC を 1 GPU 約 7 日で完走させるための共通基盤として、 CSS10 JA 単一話者データセットを整備し、 同時に既存 1D MB-iSTFT 経路の baseline ckpt を確保する。 親計画 §1 が示すとおり、 本マイルストーンの成果物は M2 (iSTFTNet2-MB 1D-2D backbone PoC) と M3 (FLY-TTS 並走 harness)、 M4 (MS-Wavehax vocoder-only FT) の三系統すべてが warm start 元として参照する起点である。

データセットを CSS10 JA に絞る理由は、 6lang base ckpt との phoneme set 互換性を保ちながらシングルスピーカー × 約 14h のスケールで「1 GPU でも 50 epoch を 1.5 日で回せる」 footprint に収めるためであり、 同時に CLAUDE.md Template B が前提とする `--samples-per-speaker 4` / `--batch-size 4` / `--base_lr 2e-5` の設定をそのまま流用可能とする。 baseline 学習を本マイルストーンに同梱するのは、 親計画 §4.6 が定める「[mb_istft_1d] 既存 baseline 完全不変」という regression guard を、 PoC ブランチ上で再生成可能な形で固定しておくためである (後続 M5 の `audio-parity-contract.toml` 比較対象となる)。

副次的な狙いとして、 PR #222 の noise_scale デフォルト変更影響を排除する目的で `noise_scale=0.667` を明示固定し、 また PR #537 merge 前の現行 torch 2.2 / py3.11 環境での baseline を確定しておくことで、 後続 M6 の bf16-mixed + TF32-on 再 benchmark との差分を 1 軸 (環境差) に閉じ込める。

## 達成判定 (Exit Criteria)

親計画 §5 Exit Criteria を以下に展開する。

- `/data/piper/dataset-css10-ja-poc/processed` 配下に train 6,200 / val 200 / test 200 utt の split が存在し、 disk 占有が ~8.3 GB (cached spec 含む) であること
  - 検証: `find /data/piper/dataset-css10-ja-poc/processed -type f | wc -l` と `du -sh /data/piper/dataset-css10-ja-poc/processed`、 `dataset.jsonl` の line count を split 別に集計
- `uv run python -m piper_train --dataset-dir /data/piper/dataset-css10-ja-poc/processed ... --max_epochs 1` で sanity 1 epoch が完走し、 WandB に audio sample が log されること
  - 検証: WandB run の `media/audio/*` artifact の存在確認、 training.log に `Epoch 1 completed` 行が出ていること
- 既存 1D MB-iSTFT baseline 50 epoch 学習が完了し、 ckpt が `/data/piper/output-css10-ja-poc/baseline-1d/checkpoints/` に保存されていること
  - 検証: `epoch=49-step=*.ckpt` の存在、 WandB の loss 曲線が plateau 付近で発散していないこと
- `decoder_type='mb_istft_1d'` で 6lang base ckpt (`/data/piper/output-multilingual-6lang-mb-istft/multilingual-6lang-mb-istft-scratch-75epoch.onnx` 由来の ckpt) から resume できること
  - 検証: `--resume-from-multispeaker-checkpoint` 指定での起動時に emb_g 除去 + emb_lang 補正のログが出ていること

## Deliverable

親計画 §5 Deliverable 列を以下に展開する。

- `/data/piper/dataset-css10-ja-poc/raw/` — Kyubyong/css10 Japanese subset の原音源 (~14h、 22050Hz 化前)
- `/data/piper/dataset-css10-ja-poc/processed/` — LJSpeech 形式に正規化済みの train / val / test 三分割 (~8.3 GB、 cached spec 含む)
  - `metadata.csv`、 `dataset.jsonl`、 `config.json`、 `wavs/`、 `spec/` (npz cache)、 `prosody/` (16dim a1/a2/a3 npz)
- `/data/piper/output-css10-ja-poc/baseline-1d/` — 既存 1D MB-iSTFT baseline 50 epoch 学習成果物
  - `checkpoints/epoch=49-step=*.ckpt`、 `training.log`、 WandB run URL
- 前処理コマンド再現用の README (本マイルストーンの worklog 末尾)
  - `prepare_multilingual_dataset.py --language ja --single-speaker --resample 22050` の正確な引数
  - `add_prosody_features.py` の prosody 16dim 抽出コマンド

## チケット一覧と進捗

| ID | 概要 | 工数 | 依存 | ステータス |
|----|------|------|------|-----------|
| [AI-01](../tickets/AI-01-css10-dataset-prep.md) | CSS10 JA データセット取得 + 前処理 | 0.5d | なし | TODO |
| [AI-02](../tickets/AI-02-baseline-training.md) | 既存 1D MB-iSTFT baseline 学習 50 epoch | 1.5d | AI-01 | TODO |

## このフェーズで考慮すべき主要リスク

親計画 §7 Risk Register から本フェーズ該当分を抜粋する。

- **R2 (HIGH likelihood / MEDIUM impact): PR #222 の emb_g 完全削除 + Flow dilation 1→2 で 6lang MB-iSTFT base ckpt が resume 不能になる懸念。**
  - 本フェーズでの mitigation: AI-02 を PR #222 merge **前**の現行 dev (torch 2.2 / py3.11) で実施し、 warm start 経路が成立することを 1 epoch sanity で確認する。 同時に `--from-scratch` での fall back baseline の学習コマンドを worklog に併記し、 PR #222 merge 後にも再現できるようにする。
- **R6 (MEDIUM likelihood / HIGH impact): `audio-parity-contract.toml` の baseline regression を A-1/A-2 が誤って書き換える。**
  - 本フェーズでの mitigation: M1 では contract 編集は一切行わず、 baseline 数値の取得のみを行う。 後続 M5 (AI-14) で `[istftnet2_mb_1d2d]` / `[mswavehax]` / `[fly_convnext6]` を**新 section として併載**する形で書き込むため、 M1 worklog には「`[mb_istft_1d]` section は touch しない」 ことを明示する。
- **R8 (MEDIUM likelihood / LOW impact): 1 GPU 直列スケジュールで AI-02 (1.5 day) が他作業と GPU 競合し M2/M3 の着手を遅延させる。**
  - 本フェーズでの mitigation: GPU 競合が予見される場合は CSS10 JA 14h を 7h subset に絞り epoch 数を 100 に倍増する代替プロトコルを worklog に明記し、 AI-02 着手判断のフォールバックとする。 また AI-01 完了直後に AI-03 (M2) と AI-06 (M3) の実装作業は GPU を使わないため、 AI-02 の GPU 学習と並行して着手可能であることを連絡事項に残す。

## 一から作り直すとしたら (Phase-level rethinking)

データセット選択を一から問い直すなら、 CSS10 JA (シングルスピーカー × 14h) ではなく **JSUT Basic5000 (シングルスピーカー × 約 10h、 高品質スタジオ収録)** を第一候補に据える検討は十分に成立する。 CSS10 JA は無償 CC0 で参入障壁が極めて低く 6lang ckpt との phoneme 互換性も維持しやすい一方、 録音 SN 比が JSUT より劣り、 後段の UTMOS proxy MOS で「データセット由来の天井」が baseline ± 0.1 圏内を狭めるリスクがある。 PoC の目的が「A-1 backbone 置換が baseline と等価かそれ以上か」 を判定することである以上、 baseline 自体のヘッドルームが狭い CSS10 JA は MOS 比較の sensitivity を下げる可能性があり、 もし再設計可能ならば JSUT で baseline を立てつつ CSS10 JA は phoneme coverage 補強用の secondary に回すという 2 段構えも検討の余地がある。

並走 vs 直列の判断についても再考の余地が大きい。 現計画は「AI-02 baseline 50 epoch」 を M1 内に同梱しているが、 これは M2 (AI-05) と M3 (AI-07) の warm start を baseline ckpt に依存させているためである。 もし baseline を warm start としてではなく**事後比較対象**としてのみ使うなら、 M1 は AI-01 のみに圧縮し、 AI-02 を M2 / M3 と並走の独立 milestone に切り出すことで「データ整備完了 → 即 PoC 着手」 のクリティカルパスを 1.5 day 短縮できる。 ただしこの場合 6lang base ckpt から直接 A-1 / A-2 backbone への warm start となり、 backbone 差分が大きい (1D → 1D-2D / dual vocoder) ことから収束が遅れる可能性があり、 epoch 数を 50 → 75 に増やす必要が出てトータルで損になるトレードオフがある。 1 GPU 制約下では現計画の「baseline を warm start として M2/M3 が利用」 構成が GPU 時間最小化として合理的だが、 2 GPU 確保できる前提では並走切り出しの方が wall clock 優位になる。

TDD アプローチについても A-1 backbone と異なり M1 は「データ整備」 が中心であり、 ユニットテストよりも **integration-first** (1 epoch sanity → 5 epoch smoke → 50 epoch full) の段階的 gate のほうが本質的な健全性検査になる。 現計画は AI-04 (`test_istftnet2_generator.py`) を M2 で TDD 着手することを推奨しているが、 M1 のデータセット側にも「split 比率 unit test」 「prosody 16dim shape unit test」 「6lang phoneme set 包含 unit test」 を `src/python/tests/test_css10_ja_prep.py` として先行配置することで、 後の AI-02 → AI-05 → AI-07 / AI-10 の warm start チェーン全体で「データセット契約」 を機械検査できる。 これは現計画には明示されていない補強案として有効。

最後にアーキテクチャ観点で、 CSS10 JA の前処理を `prepare_multilingual_dataset.py --single-speaker` で行うことは 6lang 互換性の点で合理的だが、 これは「多言語前提のスクリプトをシングルに退化させる」 形であり、 PoC 専用のミニマル前処理 (例: `tools/prepare_css10_ja_poc.py` を 100 行程度で書く) を独立させる選択肢もあった。 後者は再現性とドキュメント簡潔性で勝るが、 multilingual パイプラインとの drift リスクを抱えるため、 6lang base ckpt resume を成功させる前提なら現計画の「既存スクリプト流用」 が正しい選択である。

## 後続マイルストーンへの連絡事項

本マイルストーン完了時点で次の成果物と注意点を M2 / M3 / M4 に引き渡す。

- **baseline ckpt パス (warm start 起点):** `/data/piper/output-css10-ja-poc/baseline-1d/checkpoints/epoch=49-step=*.ckpt`
  - M2 (AI-05): `decoder_type='istftnet2_mb_1d2d'` で本 ckpt の 1D 部分 (conv_pre / cond / iSTFT / PQMF) を warm start として再利用する
  - M3 (AI-07): FLY-TTS は backbone 構造が大きく異なるため warm start せず scratch、 ただし dataset path は本 ckpt と同一を使う
  - M4 (AI-10): A-1 baseline ckpt (= M2 完了後) を acoustic model として freeze、 本 M1 baseline は M4 の比較対照として使う
- **dataset 共通パス:** `/data/piper/dataset-css10-ja-poc/processed/`
  - 三分割 split (train 6,200 / val 200 / test 200) は固定。 split 比率は contract として後続でも変更しない
  - `lid=0` 固定 (CSS10 JA はシングル言語のため 6lang コード `ja=0` をそのまま使用)
- **noise_scale 固定値:** baseline 学習で `noise_scale=0.667` を明示固定済み。 PR #222 default 変更を排除するため M2 / M3 / M4 でも同値を維持
- **暫定パス・仮置き:** WandB run URL は AI-02 完了時に worklog 末尾に追記。 6lang base ckpt 由来の resume 元 ckpt パス (`/data/piper/output-multilingual-6lang-mb-istft/`) は CLAUDE.md 記載のまま参照
- **PR #222 / #537 状況:** AI-02 完了時点での両 PR の状態 (DRAFT / OPEN、 mergeable) を worklog にスナップショット記録。 M6 (AI-16 / AI-17) での rebase 戦略の起点とする
- **`audio-parity-contract.toml` 未編集:** 本マイルストーンでは contract に一切手を入れない。 M5 (AI-14) で新 variant section を併載する際の対照値として M1 baseline の benchmark 数値のみ worklog に保存する

## 関連ドキュメント

- 親計画: [../../research/implementation-plan-a1-a2-2026-06-16.md](../../research/implementation-plan-a1-a2-2026-06-16.md)
- 改善調査: [../../research/improvement-survey-2026-06-15.md](../../research/improvement-survey-2026-06-15.md)
- Deep-dive: [../../research/decoder-upgrades-istftnet2-and-mswavehax.md](../../research/decoder-upgrades-istftnet2-and-mswavehax.md)
- 既存仕様: [../../spec/audio-parity-contract.toml](../../spec/audio-parity-contract.toml) — 本マイルストーンでは編集しない、 M5 で `[istftnet2_mb_1d2d]` 等の新 section 併載のみ
- CLAUDE.md Template B (single-speaker FT) — 本マイルストーンの AI-02 学習コマンドの母型
- 既存前処理スクリプト: `src/python/piper_train/tools/prepare_multilingual_dataset.py`、 `src/python/piper_train/tools/add_prosody_features.py`
- 6lang base ckpt 配置: `/data/piper/output-multilingual-6lang-mb-istft/` (CLAUDE.md §現在の状態 参照)
