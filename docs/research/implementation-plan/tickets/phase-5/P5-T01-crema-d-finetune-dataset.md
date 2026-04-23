# P5-T01: CREMA-D ベース finetune データセット準備

| 項目 | 値 |
|------|-----|
| Phase | 5 |
| マイルストーン | [#15](https://github.com/ayutaz/piper-plus/milestone/15) |
| ステータス | 完了 (スクリプト + 10 テスト PASS、実機 CREMA-D DL は P3-T01 後の別セッション) |
| 優先度 | 最高 (T02 学習の前提) |
| Claude Code 工数 | 2〜3h |
| 依存チケット | P3-T01 (CREMA-D DL), P3-T02 (style bank 生成), P3-T03 (inject style labels), Phase 1 全タスク (dataset.jsonl 拡張フィールド受入れ) |
| 後続チケット | P5-T02, P5-T03, P5-T04 |
| 関連 PR | PR-G (`exp(finetune): CREMA-D fine-tune of 6lang base + evaluation report`) |
| 期日 | 2026-05-08 |

## 1. タスク目的とゴール

### 1.1 目的

CREMA-D 7,442 発話 (91 話者 / 6 感情 / 英語) を、6lang ベース (`epoch=74-step=504712.ckpt`) から fine-tune できる piper-train データセット形式 (`/data/piper/dataset-crema-d-emotion/`) に変換する。Phase 3 で既に整備されている `prepare_multilingual_dataset.py` 系ツールと `inject_style_labels.py` を組み合わせ、`dataset.jsonl` に `style_vector_path` と `emotion` フィールドを注入した状態にすることが本タスクのゴール。

既存の 6lang 用 `config.json` (173 シンボル、prosody_dim=16) を継承しつつ、Phase 1 で追加された `style_vector_dim`, `style_condition_mode`, `style_condition_dropout` を書き込んだ `config.json` を生成する。音声は CREMA-D オリジナルの 48kHz WAV を `/data/piper/norm_audio/` 相当の 22.05kHz (`--sample-rate` ベース値) に resample し、cache 化する。

### 1.2 ゴール (Definition of Done)

- [ ] `/data/piper/dataset-crema-d-emotion/` ディレクトリが作成され、以下のサブディレクトリ・ファイルが揃っている
    - [ ] `cache/` (norm audio + mel spectrogram キャッシュ)
    - [ ] `style_vectors/` (per-utterance .npy、P3-T02 の出力を symlink または copy)
    - [ ] `dataset.jsonl` (全発話、style_vector_path / emotion 注入済み)
    - [ ] `config.json` (6lang 継承 + style_vector_dim=256 + style_condition_mode="global" 等を反映)
- [ ] `dataset.jsonl` の全行に以下のフィールドが含まれている
    - [ ] `audio_path` (絶対パス)
    - [ ] `text` (原文)
    - [ ] `phoneme_ids` (英語 G2P 結果、173 シンボル中の ID)
    - [ ] `speaker` (91 CREMA-D 話者の ID、`"1001"` 〜 `"1091"` 相当)
    - [ ] `language` (`"en"` 固定)
    - [ ] `style_vector_path` (`style_vectors/<utterance_id>.npy`、絶対 or 相対パス一貫)
    - [ ] `emotion` (`"angry"` / `"disgusted"` / `"fearful"` / `"happy"` / `"neutral"` / `"sad"`)
- [ ] `config.json` に以下のキーが含まれている
    - [ ] `audio.sample_rate` (22050)
    - [ ] `phoneme_id_map` (6lang base と一致、173 シンボル)
    - [ ] `num_speakers` (91、CREMA-D 話者)
    - [ ] `num_languages` (6、6lang ベース継承)
    - [ ] `style_vector_dim` (256)
    - [ ] `style_condition_mode` (`"global"`)
    - [ ] `style_condition_dropout` (0.1)
    - [ ] `prosody_dim` (16)
- [ ] `style_vectors/*.npy` が全発話分存在し、shape が `(256,)` float32 で L2 正規化済み
- [ ] `dataset.jsonl` の行数が `style_vectors/*.npy` の個数と一致 (train+val split 前)
- [ ] サンプル 1 件を PiperDataset に食わせて `Utterance` にロード可能であることを smoke test で確認
- [ ] 既存 6lang `config.json` の `phoneme_id_map` と CREMA-D 用 `config.json` の `phoneme_id_map` が bit-for-bit 一致 (fine-tune における ID ずれ防止)

## 2. 実装内容の詳細

### 2.1 対象ファイル

- `/data/piper/dataset-crema-d-emotion/` (新規ディレクトリ、成果物一式)
- `src/python/piper_train/tools/prepare_emotion_finetune_dataset.py` (新規、Phase 3 の `prepare_multilingual_dataset.py` をベースに CREMA-D 向けカスタマイズ)
- `scripts/build_crema_d_dataset.sh` (新規 or 既存の data prep シェル、ワークフロー統合用)

### 2.2 実装手順

1. **前提確認**: P3-T01 が完了し `/data/piper/datasets/CREMA-D/AudioWAV/` に 7,442 WAV が存在することを確認
2. **話者 ID 採番**: CREMA-D ファイル名 `<speaker>_<sentence>_<emotion>_<intensity>.wav` から `speaker_id_map` を生成 (91 話者 → `"1001"` 〜 `"1091"`)
3. **G2P 実行**: 英語 phonemizer (`src/python/g2p/piper_plus_g2p/english.py`) で全発話の text → phoneme_ids を生成。6lang base の `phoneme_id_map` と同じ ID 空間を使用
4. **audio cache 生成**: `norm_audio/__init__.py` のエネルギー VAD + resample (48kHz → 22.05kHz) でキャッシュ化
5. **style_vector 抽出**: P3-T02 の `build_pea_style_bank.py` を `--per-utterance` オプション (または同等機能) で呼び、全発話の `style_vectors/*.npy` (shape=(256,)) を出力
6. **dataset.jsonl 生成**: 各行を以下の形式で書き出し
    ```json
    {
      "audio_path": "/data/piper/dataset-crema-d-emotion/cache/1001_DFA_ANG_XX.pt",
      "text": "Don't forget a jacket.",
      "phoneme_ids": [1, 8, 5, 39, ...],
      "speaker": "1001",
      "language": "en",
      "style_vector_path": "style_vectors/1001_DFA_ANG_XX.npy",
      "emotion": "angry"
    }
    ```
7. **config.json 生成**: 6lang base の `config.json` をテンプレートとしてコピーし、以下のキーを上書き or 追加
    - `num_speakers = 91` (CREMA-D)
    - `num_languages = 6` (6lang base 継承、emb_lang を壊さないため)
    - `style_vector_dim = 256`
    - `style_condition_mode = "global"`
    - `style_condition_dropout = 0.1`
    - `prosody_dim = 16`
    - `phoneme_id_map` はそのまま継承 (173 シンボル)
8. **ディレクトリ構造の最終確認**: `ls -la /data/piper/dataset-crema-d-emotion/` でエントリ検証
9. **smoke test**: 以下のスクリプトで 1 サンプルロード可能か確認
    ```bash
    uv run python -c "
    from piper_train.vits.dataset import PiperDataset
    ds = PiperDataset(
        '/data/piper/dataset-crema-d-emotion',
        style_vector_dim=256,
    )
    print(f'samples={len(ds)}')
    sample = ds[0]
    print(f'style_vector.shape={sample.style_vector.shape}, emotion={sample.emotion}')
    "
    ```

### 2.3 コード例 (抜粋)

```python
# src/python/piper_train/tools/prepare_emotion_finetune_dataset.py

import argparse
import json
import logging
import shutil
from pathlib import Path

_LOGGER = logging.getLogger("prepare_emotion_finetune_dataset")

EMOTION_MAP = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}


def build_crema_d_manifest(
    crema_d_dir: Path,
    style_vectors_dir: Path,
    output_dir: Path,
    base_config_path: Path,
    style_vector_dim: int = 256,
) -> None:
    """CREMA-D → piper-train dataset 変換."""
    audio_wav_dir = crema_d_dir / "AudioWAV"
    assert audio_wav_dir.exists(), f"AudioWAV not found: {audio_wav_dir}"

    # 1. 話者 ID 採番
    speakers = sorted({p.name.split("_")[0] for p in audio_wav_dir.glob("*.wav")})
    speaker_id_map = {spk: idx for idx, spk in enumerate(speakers)}
    _LOGGER.info("Found %d unique speakers", len(speakers))

    # 2. base config 継承
    with open(base_config_path) as f:
        base_config = json.load(f)

    # 3. dataset.jsonl 生成
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / "dataset.jsonl"
    n_written = 0

    with open(jsonl_path, "w") as f_out:
        for wav_path in sorted(audio_wav_dir.glob("*.wav")):
            # ファイル名: <speaker>_<sentence>_<emotion>_<intensity>.wav
            parts = wav_path.stem.split("_")
            if len(parts) != 4:
                continue
            spk, sent, emo, intensity = parts
            if emo not in EMOTION_MAP:
                continue

            style_vec_path = style_vectors_dir / f"{wav_path.stem}.npy"
            if not style_vec_path.exists():
                _LOGGER.warning("Missing style vector: %s", style_vec_path)
                continue

            record = {
                "audio_path": str(wav_path),
                "text": _get_crema_d_text(sent),  # 12 固定文
                "speaker": spk,
                "language": "en",
                "style_vector_path": str(style_vec_path),
                "emotion": EMOTION_MAP[emo],
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_written += 1

    _LOGGER.info("Wrote %d samples to %s", n_written, jsonl_path)

    # 4. config.json 生成
    config = dict(base_config)
    config["num_speakers"] = len(speakers)
    config["style_vector_dim"] = style_vector_dim
    config["style_condition_mode"] = "global"
    config["style_condition_dropout"] = 0.1

    config_path = output_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    _LOGGER.info("Wrote config: %s", config_path)


def _get_crema_d_text(sentence_code: str) -> str:
    """CREMA-D 12 固定文の sentence code → text."""
    CREMA_D_SENTENCES = {
        "IEO": "It's eleven o'clock.",
        "TIE": "That is exactly what happened.",
        "IOM": "I'm on my way to the meeting.",
        "IWW": "I wonder what this is about.",
        "TAI": "The airplane is almost full.",
        "MTI": "Maybe tomorrow it will be cold.",
        "IWL": "I would like a new alarm clock.",
        "ITH": "I think I have a doctor's appointment.",
        "DFA": "Don't forget a jacket.",
        "ITS": "I think I've seen this before.",
        "TSI": "The surface is slick.",
        "WSI": "We'll stop in a couple of minutes.",
    }
    return CREMA_D_SENTENCES.get(sentence_code, "")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--crema-d-dir", type=Path, required=True)
    parser.add_argument("--style-vectors-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--base-config", type=Path, required=True)
    parser.add_argument("--style-vector-dim", type=int, default=256)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    build_crema_d_manifest(
        crema_d_dir=args.crema_d_dir,
        style_vectors_dir=args.style_vectors_dir,
        output_dir=args.output_dir,
        base_config_path=args.base_config,
        style_vector_dim=args.style_vector_dim,
    )
```

### 2.4 実行コマンド例

```bash
uv run python -m piper_train.tools.prepare_emotion_finetune_dataset \
  --crema-d-dir /data/piper/datasets/CREMA-D \
  --style-vectors-dir /data/piper/style_vectors_crema_d \
  --output-dir /data/piper/dataset-crema-d-emotion \
  --base-config /data/piper/dataset-multilingual-6lang-filtered/config.json \
  --style-vector-dim 256
```

## 3. エージェントチーム構成

| 役割 | 人数 | 主な責務 |
|------|------|---------|
| Explorer | 1 | P3-T01/T02/T03 の出力物 (`/data/piper/datasets/CREMA-D/`, `style_vectors_crema_d/`) の構造確認、6lang base `config.json` の全キー列挙 |
| Implementer | 1 | `prepare_emotion_finetune_dataset.py` Write、`dataset.jsonl` / `config.json` 生成、audio cache 生成コマンド実行 |
| Reviewer | 1 | Phase 1 の dataset.py が `style_vector_path` / `emotion` フィールドを正しく読み込めるか (`PiperDataset` smoke test 検証)、`phoneme_id_map` の整合性チェック |

## 4. 提供範囲 (Deliverables)

- [ ] `/data/piper/dataset-crema-d-emotion/dataset.jsonl` (7,442 行)
- [ ] `/data/piper/dataset-crema-d-emotion/config.json`
- [ ] `/data/piper/dataset-crema-d-emotion/style_vectors/` (7,442 個の `.npy`)
- [ ] `/data/piper/dataset-crema-d-emotion/cache/` (norm audio キャッシュ)
- [ ] `src/python/piper_train/tools/prepare_emotion_finetune_dataset.py`
- [ ] smoke test ログ (1 サンプルロード、`style_vector.shape`, `emotion` 出力)

**提供範囲外**:
- fine-tune 学習実行 (P5-T02)
- ONNX エクスポート (P5-T04)
- style_vector 再抽出 (既に P3-T02 で実施済み前提)

## 5. テスト項目

### 5.1 Unit テスト

- 本タスクはデータ前処理のため unit テストは作成しない (Phase 1/3 で dataset.py / build_pea_style_bank.py のテストは既に存在)
- ただし smoke test として以下を満たすこと:
    - `PiperDataset(/data/piper/dataset-crema-d-emotion, style_vector_dim=256)` が例外なく構築可能
    - `len(dataset) == 7442`
    - `dataset[0].style_vector.shape == (256,)`, `dataset[0].emotion in {"angry", ...}`

### 5.2 E2E テスト

- `uv run python -m piper_train.tools.prepare_emotion_finetune_dataset ...` が exit code 0 で終了
- `/data/piper/dataset-crema-d-emotion/dataset.jsonl` の行数が 7,400 前後 (CREMA-D のスキップ分考慮)
- `/data/piper/dataset-crema-d-emotion/config.json` を `python -c "import json; json.load(open('...'))"` でロード可能、`style_vector_dim == 256` 確認
- `phoneme_id_map` が 6lang base と一致 (`diff <(jq '.phoneme_id_map' old.json) <(jq '.phoneme_id_map' new.json)` で差分なし)

## 6. 懸念事項とレビュー項目

### 6.1 懸念事項

- **話者数 91 の扱い**: 6lang base は 571 話者で学習されており、CREMA-D の 91 話者は部分集合でもない (全く別話者)。fine-tune 時に `emb_g` をリセットするか、新規拡張するかの設計が必要。Phase 1 の `--resume-from-multispeaker-checkpoint` ロジック (`emb_g` 除去 → 単一 mean 話者) を流用するか、`--load_weights_from_checkpoint` で部分 weight load のみにするか P5-T02 と調整
- **CREMA-D 原音 48kHz / 16bit の resample 品質**: 22.05kHz downsample で高域 loss。PE-A embedding は 16kHz 前提のため、style_vector 抽出時は 16kHz、学習音響特徴量は 22.05kHz と sample rate を分ける必要あり
- **英語 G2P の一貫性**: CREMA-D の 12 固定文のみ対応だが、P3 時点で 6lang base の英語音素 (`en` phonemizer) と整合する phoneme_id が生成されるか検証必須
- **style_vectors の重複**: CREMA-D は同一発話 (12 文) × 91 話者 × 6 感情 × 2 intensity で 7,442 発話を構成。感情クラスタは安定するが、同一テキストが多重出現するため validation split は話者ベースで切ることを推奨
- **dataset.jsonl のパス絶対/相対問題**: `audio_path`, `style_vector_path` が絶対パスか相対パスかで PiperDataset の挙動が変わる。既存 6lang dataset の運用 (絶対パス推奨) に合わせる
- **`num_languages=6` の維持**: CREMA-D は英語のみだが、6lang base の `emb_lang` を破壊しないため `num_languages=6` を継承し、`language_id_map[en]=1` を全発話に設定する

### 6.2 レビュー項目

- [ ] `dataset.jsonl` の全行に `style_vector_path`, `emotion` が含まれている (欠落・`null` なし)
- [ ] `config.json` の `phoneme_id_map` が 6lang base と一致 (173 シンボル)
- [ ] `config.json` の `style_vector_dim=256`, `style_condition_mode="global"`, `style_condition_dropout=0.1` が明示されている
- [ ] 話者 ID `speaker_id_map` が 0-indexed で 91 人分存在
- [ ] `audio_path` が存在するファイルを指している (1 件 spot check)
- [ ] `style_vector_path` が存在する `.npy` を指し、`numpy.load` で shape=(256,) が取得できる
- [ ] 6lang base の `emb_lang[1]` (英語) が fine-tune で置き換えられない運用 (後続 P5-T02 と調整)

## 7. 一から作り直すとしたら

### 7.1 代替案の検討

- **代替案 A: CREMA-D → ESD (英語+中国語) に変更**
    - 利点: 中国語感情も同時に取り込める、6lang base との言語整合性が高い
    - 欠点: ESD は研究目的ライセンス (商用不可懸念)、Web フォーム登録で 1〜2 営業日待ちが発生。Phase 5 の期日 (2026-05-08) に間に合うかリスク
- **代替案 B: CREMA-D + EmoV-DB 併用 (7,442 + 7,000 = 14,442 発話)**
    - 利点: 話者多様性が増す、CC-BY で商用 OK
    - 欠点: EmoV-DB は 4 話者と少なく話者偏重リスク、感情ラベル定義が CREMA-D と非互換 (`amused` vs `happy` 等)
- **代替案 C: 話者・感情の直積 (多話者 × 多感情) を一から構築**
    - 利点: fine-tune 後の speaker × emotion の直交制御が可能
    - 欠点: 新規収録が必要、工数 (声優確保・録音・品質管理) が Phase 5 の 1〜2 日工数に収まらない
- **代替案 D: dataset.jsonl を Parquet 化し mmap 読み込み**
    - 利点: I/O 高速化、7,442 行 × 256-dim float32 = 7.4MB で十分軽量
    - 欠点: pyarrow 依存追加、既存 jsonl パイプラインとの互換性が壊れる

### 7.2 現在の実装を選んだ理由

- CREMA-D は ODbL 商用可・話者 91 (十分な多様性)・入手容易 (GitHub clone) で、期日内に確実に整備できる
- Phase 3 で CREMA-D 対応のツールチェーン (`build_pea_style_bank.py`) が既に整備されているため、データセット側もそのまま CREMA-D 前提で組む方が diff 最小
- 代替案 A (ESD) は入手待ちリスクがあり、Phase 5 の Stage 5c (多言語) で後追い追加の方が安全

### 7.3 リファクタ機会 (将来)

- `prepare_emotion_finetune_dataset.py` を `prepare_multilingual_dataset.py` のサブコマンド化 (`--emotion-labels` フラグ追加) し、Phase 1 の他データセット処理と統一
- `audio_path` / `style_vector_path` の絶対/相対を制御するフラグ (`--relative-paths`) を追加し、データセット移送時の一貫性確保
- CREMA-D 以外の感情データセットにも対応できるよう、ファイル名フォーマットを設定ファイル (YAML) で定義可能にする

## 8. 後続タスクへの連絡事項

- **P5-T02 へ**: `--dataset-dir /data/piper/dataset-crema-d-emotion` を指定。話者数 91 だが `num_languages=6` を維持 (emb_lang 互換)。fine-tune 時は `--resume-from-multispeaker-checkpoint` ではなく `--load_weights_from_checkpoint` で部分 weight load を推奨 (emb_g は新規 91 話者用に再初期化)
- **P5-T03 へ**: validation split は話者ベース (91 話者の 20% ≒ 18 話者) で切ること。同一話者が train/val 両方に出ると SER 評価が過大評価になる
- **P5-T04 へ**: ONNX エクスポート時の `config.json` テンプレートとして `/data/piper/dataset-crema-d-emotion/config.json` をそのまま流用可能
- **P3 系 (既存データセット側) へ**: `inject_style_labels.py` で 6lang 既存データセットにも `emotion="neutral"` を注入する選択肢あり (シナリオ B 実施時)

## 9. 参考リンク

- `phase-5.md §5.2` データ前処理ツール設計
- `phase-3-4.md §3.1〜3.3` CREMA-D 詳細・`build_pea_style_bank.py` / `inject_style_labels.py`
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D
- CLAUDE.md 「前処理ツール」セクション (`prepare_multilingual_dataset.py`)
- 既存 6lang dataset: `/data/piper/dataset-multilingual-6lang-filtered/config.json`
- P1-T02 (dataset.py の `style_vector_path` / `emotion` フィールド設計)
