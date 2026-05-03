# PE-A Emotion Style Bank

PE-A (Perception Encoder - Audio) の音声埋め込みから生成される感情
**style bank** (`.npz`) のスキーマ、生成・検証ツール、および CREMA-D 以外の
データセットへの対応ガイド。

以下 3 ツールの使用リファレンスです:

| ツール | 役割 |
|-------|------|
| [`build_pea_style_bank.py`](#1-build_pea_style_bank) | 感情ラベル付き音声から PE-A embedding を抽出し `.npz` を生成 |
| [`inject_style_labels.py`](#2-inject_style_labels) | 既存 dataset manifest に `emotion` と `style_vector_path` を注入 |
| [`validate_style_bank.py`](#3-validate_style_bank) | `.npz` のスキーマと数値的整合性を検証 (CI 組込み可) |

---

## `.npz` スキーマ

fork `yusuke-ai/piper-plus` の `_init_pea_emotion_loss()` が読み込む
`.npz` と byte-for-byte 互換です。3 つのキーを含みます。

| キー | dtype | shape | 内容 |
|------|-------|-------|------|
| `emotion_names`     | `object` (Python `str`) | `[N]` | ソート済みの感情ラベル。重複・空文字列は不可。 |
| `emotion_centroids` | `float32` | `[N, D]` | 感情ごとの mean embedding を **L2-normalize** した centroid。各行の L2 norm は `1.0 ± 1e-3`。 |
| `global_centroid`   | `float32` | `[D]` | 全 embedding の **raw mean** (再正規化なし)。`_init_pea_emotion_loss()` 側で `F.normalize()` が再適用される。 |

ここで `D` は PE-A audio embedding の次元 (想定 `256` or `512`、モデル変種
による)。`emotion_names[i]` と `emotion_centroids[i]` は同じインデックスで
対応付けられます。

### スキーマ互換性メモ

- `emotion_names` は **`object` dtype** で保存してください。`np.str_` 固定長
  dtype だと fork の読込みで "E5" 等の短縮文字列になる場合があります。
- `emotion_centroids` / `global_centroid` は必ず **`float32`** にしてくだ
  さい。`float64` で保存すると fork の `register_buffer` の dtype が一致せ
  ず loss 計算で型エラーになります。
- `global_centroid` は敢えて **正規化しない** まま保存します (fork 側で
  `F.normalize()` が呼ばれる)。これは PE-A emotion loss 実装と
  一致させるため必須です。

---

## 1. `build_pea_style_bank.py`

### 1.1 概要

感情ラベル付きの音声データセットから、PE-A `facebook/pe-av-small` モデル
で audio embedding を抽出し、`.npz` の style bank を生成するツール。

2 段階の loader を順に試します:

1. `transformers.AutoModel.from_pretrained("facebook/pe-av-small", trust_remote_code=True)`
2. `facebookresearch/perception_models` pip パッケージ (`perception_models.pe_av.PEAudio`)

PoC 検証時点では **Option A (transformers) は
`model_type=pe_audio_video` が未対応で失敗**し、Option B (perception_models)
が実用パス。両方失敗した場合は `PEAModelError` にインストール手順を載せて
明確に raise します。

### 1.2 使用例

```bash
# CREMA-D (download_crema_d.py 出力) から style bank を生成
uv run python -m piper_train.tools.build_pea_style_bank \
  --input-dataset /data/piper/datasets/CREMA-D \
  --output-bank   /data/piper/style_bank_crema_d.npz \
  --per-utterance-dir /data/piper/style_vectors_crema_d \
  --device cuda

# CSV / JSONL manifest を使う場合
uv run python -m piper_train.tools.build_pea_style_bank \
  --manifest /data/piper/custom_emotions.csv \
  --output-bank /data/piper/style_bank_custom.npz
```

**CSV フォーマット** (`audio_path`, `emotion` 必須):

```csv
audio_path,emotion
/data/audio/utt_0001.wav,happy
/data/audio/utt_0002.wav,angry
```

**JSONL フォーマット** (1 行 1 発話):

```json
{"audio_path": "/data/audio/utt_0001.wav", "emotion": "happy"}
```

### 1.3 主要 CLI オプション

| オプション | デフォルト | 説明 |
|-----------|----------|------|
| `--input-dataset <dir>` | なし | CREMA-D 互換ディレクトリ (`AudioWAV/` を含む) |
| `--manifest <file>` | なし | CSV or JSONL (相互排他) |
| `--output-bank <file>` | 必須 | 出力 `.npz` パス |
| `--per-utterance-dir <dir>` | なし | 各発話の `<utt_id>.npy` を書き出すディレクトリ (inject_style_labels で再利用) |
| `--pe-model-name` | `facebook/pe-av-small` | HuggingFace / perception_models モデル ID |
| `--device` | `cpu` | `cuda` / `cuda:0` / `mps` も可 |
| `--sample-rate` | `16000` | PE-A は 16 kHz 固定。それ以外を渡すと自動 resample |
| `--report` | `<bank>.report.json` | emotion 統計 + cosine similarity matrix |

### 1.4 生成される report

`--report` で指定された JSON に以下を書き出します:

```json
{
  "emotion_names": ["angry", "happy", "sad", ...],
  "counts": {"angry": 1230, "happy": 1200, ...},
  "embedding_dim": 512,
  "cosine_similarity_matrix": [[1.0, 0.21, ...], ...],
  "global_centroid_norm": 0.84
}
```

- **対角成分は 1.0** (自己類似度)
- 非対角は typically `0.0 〜 0.8` (感情同士の類似度)
- `global_centroid_norm` が極端に小さい (< 0.3) 場合、embedding が打ち消しあ
  っている可能性あり。次元を確認してください。

---

## 2. `inject_style_labels.py`

### 2.1 概要

既存の piper-train dataset.jsonl に `emotion` と `style_vector_path` を注入
するツール。以下 3 モードをサポート:

| モード | 用途 |
|-------|------|
| `--default-emotion neutral` | 感情ラベルが無い既存データセット (MOE-Speech, 6lang 等) に `emotion=neutral` を一括付与 |
| `--emotion-csv <csv>` | CREMA-D のように utt_id ↔ emotion の CSV がある場合 |
| `--style-bank <npz> --output-dir <dir>` | `.npz` の centroid を感情ごとに per-utterance `.npy` として展開 (build 済み bank を別データセットに流用する場合) |

### 2.2 使用例

```bash
# (A) 6lang dataset に emotion=neutral を注入
uv run python -m piper_train.tools.inject_style_labels \
  --input-dataset /data/piper/dataset-multilingual-6lang-filtered/manifest.jsonl \
  --output-manifest /data/piper/dataset-multilingual-6lang-filtered/manifest.neutral.jsonl \
  --default-emotion neutral

# (B) CREMA-D CSV + per-utterance .npy 連携
uv run python -m piper_train.tools.inject_style_labels \
  --input-dataset /data/piper/datasets/CREMA-D/manifest.jsonl \
  --output-manifest /data/piper/datasets/CREMA-D/manifest.labelled.jsonl \
  --dataset-dir /data/piper/datasets/CREMA-D \
  --style-vectors-dir /data/piper/style_vectors_crema_d \
  --emotion-csv /data/piper/datasets/CREMA-D/emotions.csv \
  --style-bank /data/piper/style_bank_crema_d.npz

# (C) Emotion map JSON でコード変換
cat > /tmp/emotion_map.json <<'JSON'
{"happy": "HAP", "sad": "SAD", "angry": "ANG", "neutral": "NEU"}
JSON
uv run python -m piper_train.tools.inject_style_labels \
  --input-dataset manifest.jsonl --output-manifest labelled.jsonl \
  --emotion-csv external.csv --emotion-map /tmp/emotion_map.json
```

### 2.3 主要 CLI オプション

| オプション | 説明 |
|-----------|------|
| `--input-dataset <file>` | 入力 JSONL (piper-train 形式) |
| `--output-manifest <file>` | 出力 JSONL (省略時は入力を上書き) |
| `--dataset-dir <dir>` | dataset のルート。`style_vector_path` が相対パスで書き出される |
| `--style-vectors-dir <dir>` | 既存 `<utt_id>.npy` ディレクトリ |
| `--emotion-csv <file>` | `utt_id,emotion` 形式 CSV (先頭 `#` はコメント) |
| `--emotion-map <json>` | `{"friendly_label": "dataset_code"}` の JSON。CSV の生コードを friendly label に翻訳 |
| `--default-emotion <name>` | CSV にない utt_id 用のフォールバック (default: `neutral`) |
| `--style-bank <npz>` | 検証用 / または centroid 展開ソース |
| `--output-dir <dir>` | `--style-bank` と併用で per-utterance `.npy` を書き出す |

### 2.4 大規模 manifest での使用

6lang dataset (508,187 行) にも対応済み。内部でストリーミング書き出し
(`<output>.tmp` 経由でアトミックにリネーム) するため、メモリ使用量は
1 行分のみ。処理速度は SSD で約 50〜80k 行/秒。

---

## 3. `validate_style_bank.py`

### 3.1 概要

`.npz` の構造・数値を検証する CLI。CI で `exit_code != 0` の場合 PR を
block することを想定した設計。

### 3.2 使用例

```bash
# 基本検証
uv run python -m piper_train.tools.validate_style_bank \
  --style-bank /data/piper/style_bank_crema_d.npz

# 期待する感情と次元を指定
uv run python -m piper_train.tools.validate_style_bank \
  --style-bank /data/piper/style_bank_crema_d.npz \
  --expected-emotions angry disgusted fearful happy neutral sad \
  --expected-dim 512

# strict モード (global_centroid 一致性の warning も error 扱い)
uv run python -m piper_train.tools.validate_style_bank \
  --style-bank /data/piper/style_bank_crema_d.npz --strict
```

### 3.3 検証項目

| 項目 | 種別 | 備考 |
|------|------|------|
| 必須キー (3 つ) の存在 | Error | スキップ不可 |
| `emotion_names` dtype = object | Error | |
| `emotion_centroids` dtype = float32 / ndim = 2 | Error | |
| `global_centroid` dtype = float32 / ndim = 1 | Error | |
| `N = len(emotion_names) = emotion_centroids.shape[0]` | Error | |
| `D = emotion_centroids.shape[1] = global_centroid.shape[0]` | Error | |
| 各 `emotion_centroids` 行の L2 norm = `1.0 ± 1e-3` | Error | |
| NaN / Inf の不在 | Error | |
| `emotion_names` の非空 + 重複なし | Error | |
| `global_centroid` と `mean(emotion_centroids)` の cosine similarity ≥ 0.99 | **Warning** | `--strict` で Error |

### 3.4 CI 組込み例

```yaml
# .github/workflows/validate-style-bank.yml
- name: Validate style bank
  run: |
    uv run python -m piper_train.tools.validate_style_bank \
      --style-bank artifacts/style_bank_crema_d.npz \
      --expected-emotions angry disgusted fearful happy neutral sad
```

---

## 4. CREMA-D 以外のデータセット追加ガイド

### 4.1 対応データセット早見表

| Dataset | 言語 | 感情数 | 発話数 | サンプルレート | ライセンス | 商用可 |
|---------|------|------|-------|-------------|----------|-------|
| **CREMA-D** | EN | 6 | 7,442 | 16 kHz | ODbL 1.0 + Community | **○** |
| **EmoV-DB** | EN | 5 | 7,000 | 16 kHz | CC-BY 4.0 | **○** |
| **ESD** | EN + ZH | 5 | 35,000 | 16 kHz | 研究目的 | **△** (商用時は attribution 厳格化) |
| **JTES** | JA | 4 | ~20,000 | 48 kHz | 研究目的 | **△** |
| **RAVDESS** | EN | 8 | 7,356 | 48 kHz | CC-BY-NC-SA 4.0 | **✗** (非商用のみ) |

**凡例**: ○ = 商用可、△ = 研究用 (商用は要審査)、✗ = 商用不可

### 4.2 EmoV-DB (英語 / CC-BY 4.0, 商用可)

5 感情 (Amused / Angry / Disgusted / Neutral / Sleepy) × 4 話者の英語コーパス。
CREMA-D と並んで商用に使える数少ない選択肢。

**手順**:

1. `git clone https://github.com/numediart/EmoV-DB.git`
2. 48 kHz → 16 kHz にリサンプリング (build_pea_style_bank が自動で行う)
3. ファイル名規則: `<speaker>_<emotion>_<id>.wav` → 独自 CSV を作成
4. 感情ラベル変換:

```python
EMOV_DB_EMOTION_MAP = {
    "amused":    "happy",     # amused は CREMA-D の happy に近い
    "angry":     "angry",
    "disgusted": "disgusted",
    "neutral":   "neutral",
    "sleepy":    "neutral",   # sleepy は neutral に寄せる (or 独自ラベル)
}
```

5. `build_pea_style_bank.py --manifest emov_db.csv --output-bank emov_db_bank.npz`

**注意**: `amused` と `sleepy` を CREMA-D の 6 感情に写像する際、semantic な
類似度は低い。独立した感情として残す方が表現力は高いが、CREMA-D との
統合時は `--expected-emotions` で整合を取ってください。

### 4.3 ESD (英語 + 中国語 / 研究目的)

**ライセンス注意**: ESD は「research purposes only」と明記されています。商用
製品に組み込む場合は、ESD 由来の style bank を配布するのではなく、**一度
学習した TTS モデル単独で配布** する運用が安全です。

**手順**:

1. 公式配布ページ (https://hltsingapore.github.io/ESD/) からリクエスト
2. 5 感情 (Neutral / Angry / Happy / Sad / Surprise) × 10 話者 (EN) + 10 話者 (ZH)
3. ディレクトリ構造は `0001/Angry/0001_000001.wav` 形式
4. 独自 CSV を生成:

```python
import csv
from pathlib import Path

rows = []
for spk_dir in sorted(Path("ESD").glob("00??")):
    for emo_dir in spk_dir.iterdir():
        if emo_dir.is_dir():
            for wav in emo_dir.glob("*.wav"):
                rows.append({
                    "audio_path": str(wav),
                    "emotion": emo_dir.name.lower(),
                })

with open("esd.csv", "w", newline="") as fh:
    writer = csv.DictWriter(fh, fieldnames=["audio_path", "emotion"])
    writer.writeheader()
    writer.writerows(rows)
```

5. `build_pea_style_bank.py --manifest esd.csv --output-bank esd_bank.npz`

### 4.4 JTES (日本語 / 研究目的)

**ライセンス注意**: JTES (Japanese Twitter-based Emotional Speech Corpus) も
研究目的。商用時は利用規約を要確認。

**手順**:

1. https://research.nii.ac.jp/src/JTES.html から申請
2. 4 感情 (Neutral / Joy / Sadness / Anger)
3. 48 kHz → 16 kHz へのリサンプリング必須 (build_pea_style_bank が自動対応)
4. 日本語音声なので、CREMA-D などと統合する場合は言語横断での感情空間
   の整合性を確認してください。PE-A は多言語 audio encoder なので理論的に
   は言語非依存ですが、実際には言語によって centroid が分離する場合が
   あります。

### 4.5 独自データセット (CSV manifest 形式)

カスタム感情 (例: `excited`, `calm`, `fearful` を独自定義) を使う場合の
最小手順:

```bash
# (1) CSV を作る
cat > custom.csv <<'CSV'
audio_path,emotion
/data/my/utt_001.wav,excited
/data/my/utt_002.wav,calm
/data/my/utt_003.wav,excited
CSV

# (2) bank 生成
uv run python -m piper_train.tools.build_pea_style_bank \
  --manifest custom.csv --output-bank custom_bank.npz

# (3) 検証
uv run python -m piper_train.tools.validate_style_bank \
  --style-bank custom_bank.npz \
  --expected-emotions excited calm
```

---

## 5. FAQ

### Q1: PE-A loss で `.npz` が読み込まれない。どこを見ればよい?

A: まず `validate_style_bank.py` で構造検証してください。多くのケースは
以下いずれかです:

- `emotion_centroids` が float64 で保存されている (fork の buffer dtype
  と不一致) → `.astype(np.float32)` で再保存
- `emotion_names` が `np.str_` (固定長) で保存されている →
  `np.array(names, dtype=object)` で再保存
- `global_centroid` が 2-D shape になっている → squeeze で 1-D 化

### Q2: `build_pea_style_bank.py` で PE-A が読み込めない

A: PoC 検証時点では transformers AutoModel 経由の自動ロードは未
対応です。下記いずれかでインストールしてください:

```bash
# Option B (推奨): perception_models から直接
pip install git+https://github.com/facebookresearch/perception_models.git

# Option A: transformers が対応されたら (2026-05 以降見込み)
pip install "transformers>=4.45"  # 要確認
```

### Q3: CREMA-D 以外のデータセットを既存 CREMA-D bank とマージできる?

A: 可能ですが、**同じ PE-A モデル / sample rate / 正規化手順** で抽出された
embedding のみ統合してください。異なる前処理の embedding を混ぜると
centroid の方向がズレます。統合手順:

1. 各データセットで `--per-utterance-dir` を指定し per-utterance `.npy` を生成
2. それぞれの `.npy` を統合用ディレクトリにシンボリックリンク
3. 統合済み CSV (全データセットの `utt_id,emotion` を連結) を作成
4. `build_pea_style_bank.py --manifest <merged.csv>` で単一 bank を再生成

### Q4: PE-A の embedding 次元が変わった場合は?

A: `--expected-dim` を更新し、既存 bank は全て再生成が必要です。PE-A は
モデル亜種で次元が変わる可能性があるため、`.npz.report.json` の
`embedding_dim` を記録しておくことを推奨します。

---

## 6. ライセンス注意事項

- **CREMA-D**: ODbL 1.0 + Community License → attribution 必須 (自動的に
  `LICENSE_CREMA_D.txt` がデータディレクトリに配置されます)。
- **EmoV-DB**: CC-BY 4.0 → 商用可、attribution 必須。
- **ESD / JTES**: 研究目的 → **商用製品への直接組込みは避ける**。学習済み TTS
  モデルとして蒸留・統合した上で配布するのが安全。
- **PE-A model (facebook/pe-av-small)**: Apache-2.0 → 商用可。

**推奨**: 商用リリースでは CREMA-D + EmoV-DB のみを style bank 生成に使う
のが現時点で最も安全です。ESD / JTES / RAVDESS は R&D 目的に限定してくだ
さい。

---

## 7. 関連ドキュメント

- ORT セッション統一仕様: `docs/spec/ort-session-contract.toml`
- Style vector 6 ランタイム I/O 契約: `docs/spec/style-vector-contract.toml`
