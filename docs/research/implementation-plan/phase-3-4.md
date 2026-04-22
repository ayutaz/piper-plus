# Phase 3-4 実装計画: Style Bank 生成ツール + PE-A Emotion Loss 統合

**Phase 3 工数**: 3 日
**Phase 4 工数**: 1.5 週間
**依存**: Phase 0 完了 (PE-A モデルロード方法確定)、Phase 1 完了 (style vector conditioning)
**後続**: Phase 5 (fine-tune 実験で style bank と PE-A loss を使用)

---

## Phase 3: Style Bank 生成ツール

### 3.1 CREMA-D データセット詳細

**公式リポジトリ**: https://github.com/CheyneyComputerScience/CREMA-D

| 項目 | 詳細 |
|-----|------|
| ライセンス | Open Database License (ODbL) 1.0 + Community License |
| 商用可否 | ✅ 可能 |
| 学習利用 | ✅ 可能 (属性表示が推奨) |
| 言語 | 英語のみ |
| 規模 | 7,442 発話 / 91 話者 (46 女性 + 45 男性) / 6 感情 |
| 感情 | angry (ANG), disgusted (DIS), fearful (FEA), happy (HAP), neutral (NEU), sad (SAD) |
| サンプルレート | 16 kHz (PE-A と一致、再サンプリング不要) |
| ビット深度 | 16-bit WAV |
| 発話時間 | 1.5〜3.0 秒 |
| ストレージ | ~27GB (圧縮) / ~48GB (解凍) |
| ダウンロード時間 | 2〜3 時間 (100Mbps) |

**ディレクトリ構造**:
```
CREMA-D/
  AudioWAV/
    1001_IWW_ANG_HI.wav  # Speaker_Sentence_Emotion_Intensity
    1001_IWW_ANG_LO.wav
    1001_IWW_ANG_MD.wav
    1001_IWW_ANG_XX.wav  # XX = neutral emotion
    ...
```

**Intensity levels**: XX (neutral), LO (low), MD (medium), HI (high)

### 3.2 build_pea_style_bank.py 完全実装

**配置**: `src/python/piper_train/tools/build_pea_style_bank.py`

```python
#!/usr/bin/env python3
"""Generate PE-A emotion style bank from audio dataset with emotion labels."""

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torchaudio
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm

_LOGGER = logging.getLogger("build_pea_style_bank")

PE_A_SAMPLE_RATE = 16000

EMOTION_CODE_MAP = {
    "ANG": "angry",
    "DIS": "disgusted",
    "FEA": "fearful",
    "HAP": "happy",
    "NEU": "neutral",
    "SAD": "sad",
}


class EmotionAudioDataset(Dataset):
    """Load audio + emotion pairs from CREMA-D or CSV manifest."""

    def __init__(
        self,
        data_dir: Path,
        manifest_path: Optional[Path] = None,
        sample_rate: int = PE_A_SAMPLE_RATE,
    ):
        self.data_dir = Path(data_dir)
        self.sample_rate = sample_rate
        self.samples = []

        if manifest_path:
            self._load_from_manifest(manifest_path)
        else:
            self._load_from_crema_d()

    def _load_from_manifest(self, manifest_path: Path):
        """Load from CSV/JSONL manifest: 'audio_path,emotion'."""
        with open(manifest_path, "r") as f:
            for line_idx, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if manifest_path.suffix == ".jsonl":
                    item = json.loads(line)
                    audio_path = item.get("audio_path")
                    emotion = item.get("emotion")
                else:
                    parts = line.split(",", 1)
                    if len(parts) != 2:
                        _LOGGER.warning("Skipping malformed line %d: %s", line_idx, line)
                        continue
                    audio_path, emotion = parts

                audio_path = self.data_dir / audio_path
                if not audio_path.exists():
                    _LOGGER.warning("Audio file not found: %s", audio_path)
                    continue

                self.samples.append({
                    "audio_path": audio_path,
                    "emotion": emotion.strip().lower(),
                })

        _LOGGER.info("Loaded %d samples from manifest", len(self.samples))

    def _load_from_crema_d(self):
        """Auto-detect CREMA-D folder: AudioWAV/<speaker>_<sentence>_<emotion>_<intensity>.wav"""
        audio_dir = self.data_dir / "AudioWAV"
        if not audio_dir.exists():
            raise FileNotFoundError(f"AudioWAV directory not found: {audio_dir}")

        for wav_file in sorted(audio_dir.glob("*.wav")):
            parts = wav_file.stem.split("_")
            if len(parts) < 4:
                _LOGGER.warning("Skipping malformed filename: %s", wav_file.name)
                continue

            emotion_code = parts[2]
            emotion = EMOTION_CODE_MAP.get(emotion_code)
            if not emotion:
                _LOGGER.warning("Unknown emotion code '%s' in %s", emotion_code, wav_file.name)
                continue

            self.samples.append({
                "audio_path": wav_file,
                "emotion": emotion,
            })

        _LOGGER.info("Detected %d CREMA-D samples", len(self.samples))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        item = self.samples[idx]
        audio_path = item["audio_path"]
        emotion = item["emotion"]

        waveform, sr = torchaudio.load(str(audio_path))

        # Stereo → mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Resample
        if sr != self.sample_rate:
            waveform = torchaudio.functional.resample(waveform, sr, self.sample_rate)

        # Normalize to [-1, 1]
        max_val = waveform.abs().max()
        if max_val > 0:
            waveform = waveform / max_val

        return {
            "audio": waveform.squeeze(0),
            "emotion": emotion,
            "audio_path": str(audio_path),
        }


def load_pea_model(model_name: str = "facebook/pe-av-small"):
    """Load PE-A model from HuggingFace Hub."""
    _LOGGER.info("Loading PE-A model: %s", model_name)
    from transformers import AutoModel

    model = AutoModel.from_pretrained(model_name, trust_remote_code=True)
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    return model, device


def extract_audio_embedding(model, audio: torch.Tensor, device: torch.device):
    """Extract audio embedding from PE-A model.

    NOTE: API の正確なシグネチャは Phase 0 PoC で確定。
    以下は推測ベースの実装で、Phase 0 結果に応じて修正が必要。
    """
    audio = audio.to(device).unsqueeze(0)  # [1, T]
    with torch.no_grad():
        if hasattr(model, "get_audio_embeds"):
            embedding = model.get_audio_embeds(audio)
        else:
            # Fallback: forward() and extract embedding from output
            output = model(audio)
            if isinstance(output, dict):
                embedding = output.get("audio_embeds") or output.get("embeddings")
            elif hasattr(output, "audio_embeds"):
                embedding = output.audio_embeds
            else:
                embedding = output

        embedding = torch.nn.functional.normalize(embedding, p=2, dim=-1)
        return embedding.squeeze(0).cpu()  # [D]


def build_style_bank(
    dataset: EmotionAudioDataset,
    model,
    device: torch.device,
    batch_size: int = 1,  # PE-A は可変長入力のため batch_size=1 推奨
    per_utterance_dir: Optional[Path] = None,
):
    """Compute emotion centroids and global centroid from audio embeddings."""
    _LOGGER.info("Extracting audio embeddings...")

    emotion_embeddings: dict[str, list[torch.Tensor]] = {}
    all_embeddings: list[torch.Tensor] = []

    if per_utterance_dir:
        per_utterance_dir = Path(per_utterance_dir)
        per_utterance_dir.mkdir(parents=True, exist_ok=True)

    for i in tqdm(range(len(dataset)), desc="Processing audio"):
        sample = dataset[i]
        audio = sample["audio"]
        emotion = sample["emotion"]
        audio_path = sample["audio_path"]

        try:
            embedding = extract_audio_embedding(model, audio, device)  # [D]
            all_embeddings.append(embedding)

            if emotion not in emotion_embeddings:
                emotion_embeddings[emotion] = []
            emotion_embeddings[emotion].append(embedding)

            if per_utterance_dir:
                utt_id = Path(audio_path).stem
                np.save(str(per_utterance_dir / f"{utt_id}.npy"), embedding.numpy())

        except Exception as e:
            _LOGGER.error("Failed to process %s: %s", audio_path, e)

    # Compute centroids
    emotion_names = sorted(emotion_embeddings.keys())
    emotion_centroids = []

    _LOGGER.info("Computing emotion centroids...")
    for emotion in emotion_names:
        embeddings = torch.stack(emotion_embeddings[emotion])
        centroid = embeddings.mean(dim=0)
        emotion_centroids.append(centroid)
        _LOGGER.info(
            "  %s: %d samples, centroid norm=%.4f",
            emotion, len(embeddings), centroid.norm().item(),
        )

    emotion_centroids = torch.stack(emotion_centroids)  # [N, D]
    all_embeddings_tensor = torch.stack(all_embeddings)  # [total, D]
    global_centroid = all_embeddings_tensor.mean(dim=0)  # [D]

    return emotion_names, emotion_centroids, global_centroid, all_embeddings_tensor


def save_style_bank(output_path: Path, emotion_names, emotion_centroids, global_centroid):
    """Save style bank to .npz format."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    np.savez(
        str(output_path),
        emotion_names=np.array(emotion_names, dtype=object),
        emotion_centroids=emotion_centroids.cpu().numpy().astype(np.float32),
        global_centroid=global_centroid.cpu().numpy().astype(np.float32),
    )
    _LOGGER.info("Style bank saved: %s", output_path)


def generate_report(
    emotion_names,
    emotion_centroids,
    global_centroid,
    all_embeddings,
    output_dir: Path,
):
    """Generate statistics and similarity matrix report."""
    norm_centroids = torch.nn.functional.normalize(emotion_centroids, p=2, dim=-1)
    similarity_matrix = torch.mm(norm_centroids, norm_centroids.t())

    report = {
        "num_emotions": len(emotion_names),
        "num_samples": len(all_embeddings),
        "embedding_dim": emotion_centroids.shape[-1],
        "emotion_names": emotion_names,
        "emotion_stats": {
            name: {
                "centroid_norm": emotion_centroids[i].norm().item(),
                "distance_to_global": (emotion_centroids[i] - global_centroid).norm().item(),
            }
            for i, name in enumerate(emotion_names)
        },
        "cosine_similarity_matrix": similarity_matrix.cpu().numpy().tolist(),
    }

    report_path = output_dir / "style_bank_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    _LOGGER.info("Report saved: %s", report_path)
    _LOGGER.info("Cosine similarity matrix:\n%s", similarity_matrix)


def main():
    parser = argparse.ArgumentParser(
        description="Generate PE-A emotion style bank from audio dataset"
    )
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--model-name", type=str, default="facebook/pe-av-small")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--per-utterance-dir", type=Path, default=None)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--sample-rate", type=int, default=PE_A_SAMPLE_RATE)
    parser.add_argument("--log-level", type=str, default="INFO")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    if args.output is None:
        args.output = args.dataset_dir / "style_bank.npz"

    _LOGGER.info("=" * 60)
    _LOGGER.info("PE-A Style Bank Generator")
    _LOGGER.info("=" * 60)

    dataset = EmotionAudioDataset(
        args.dataset_dir,
        manifest_path=args.manifest,
        sample_rate=args.sample_rate,
    )

    if len(dataset) == 0:
        _LOGGER.error("No audio samples loaded.")
        return

    model, device = load_pea_model(args.model_name)

    emotion_names, emotion_centroids, global_centroid, all_embeddings = build_style_bank(
        dataset, model, device,
        batch_size=args.batch_size,
        per_utterance_dir=args.per_utterance_dir,
    )

    save_style_bank(args.output, emotion_names, emotion_centroids, global_centroid)
    generate_report(
        emotion_names, emotion_centroids, global_centroid, all_embeddings,
        args.output.parent,
    )

    _LOGGER.info("Style bank generation complete!")


if __name__ == "__main__":
    main()
```

### 3.3 inject_style_labels.py (既存データセット拡張)

**配置**: `src/python/piper_train/tools/inject_style_labels.py`

```python
#!/usr/bin/env python3
"""Inject style_vector_path and emotion fields into existing dataset manifest."""

import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from tqdm import tqdm

_LOGGER = logging.getLogger("inject_style_labels")


def inject_style_labels(
    dataset_dir: Path,
    manifest_path: Path,
    style_vectors_dir: Optional[Path] = None,
    emotion_mapping: Optional[dict] = None,
    default_emotion: str = "neutral",
    output_manifest: Optional[Path] = None,
):
    """Add style_vector_path and emotion fields to existing manifest."""
    dataset_dir = Path(dataset_dir)
    manifest_path = Path(manifest_path)
    output_manifest = Path(output_manifest or manifest_path)
    emotion_mapping = emotion_mapping or {}

    updated_count = 0
    skipped_count = 0

    with open(manifest_path, "r") as f:
        original_lines = [line.strip() for line in f if line.strip()]

    updated_lines = []
    for line in tqdm(original_lines, desc="Injecting labels"):
        try:
            item = json.loads(line)
            audio_path = item.get("audio_norm_path") or item.get("audio_path")
            utt_id = Path(audio_path).stem if audio_path else None

            # Emotion
            emotion = None
            if utt_id and utt_id in emotion_mapping:
                emotion = emotion_mapping[utt_id]
            elif audio_path and audio_path in emotion_mapping:
                emotion = emotion_mapping[audio_path]
            else:
                emotion = default_emotion
            item["emotion"] = emotion

            # style_vector_path
            if style_vectors_dir and utt_id:
                style_vec_path = Path(style_vectors_dir) / f"{utt_id}.npy"
                if style_vec_path.exists():
                    item["style_vector_path"] = str(style_vec_path.relative_to(dataset_dir))
                    updated_count += 1
                else:
                    item["style_vector_path"] = None
                    skipped_count += 1
            else:
                item["style_vector_path"] = None

            updated_lines.append(json.dumps(item))
        except Exception as e:
            _LOGGER.warning("Failed to process line: %s", e)

    with open(output_manifest, "w") as f:
        for line in updated_lines:
            f.write(line + "\n")

    _LOGGER.info(
        "Manifest updated: %d with style_vector, %d skipped, total %d",
        updated_count, skipped_count, len(updated_lines),
    )


def load_emotion_mapping_from_csv(csv_path: Path) -> dict:
    mapping = {}
    with open(csv_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                parts = line.split(",", 1)
                if len(parts) == 2:
                    utt_id, emotion = parts
                    mapping[utt_id.strip()] = emotion.strip().lower()
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--style-vectors-dir", type=Path, default=None)
    parser.add_argument("--emotion-csv", type=Path, default=None)
    parser.add_argument("--default-emotion", type=str, default="neutral")
    parser.add_argument("--output-manifest", type=Path, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    emotion_mapping = {}
    if args.emotion_csv:
        emotion_mapping = load_emotion_mapping_from_csv(args.emotion_csv)
        _LOGGER.info("Loaded %d emotion mappings", len(emotion_mapping))

    inject_style_labels(
        args.dataset_dir, args.manifest,
        style_vectors_dir=args.style_vectors_dir,
        emotion_mapping=emotion_mapping,
        default_emotion=args.default_emotion,
        output_manifest=args.output_manifest,
    )


if __name__ == "__main__":
    main()
```

### 3.4 動作確認手順

```bash
# 1. CREMA-D ダウンロード
cd /data/piper/datasets
git clone https://github.com/CheyneyComputerScience/CREMA-D.git --depth=1

# 2. Style bank 生成
uv run python -m piper_train.tools.build_pea_style_bank \
  --dataset-dir /data/piper/datasets/CREMA-D \
  --output /data/piper/style_bank_crema_d.npz \
  --per-utterance-dir /data/piper/style_vectors_crema_d \
  --batch-size 1

# 3. 出力確認
ls -lh /data/piper/style_bank_crema_d.npz
cat /data/piper/style_bank_crema_d/style_bank_report.json

# 4. (オプション) 既存 6lang manifest への注入
uv run python -m piper_train.tools.inject_style_labels \
  --dataset-dir /data/piper/dataset-multilingual-6lang-filtered \
  --manifest /data/piper/dataset-multilingual-6lang-filtered/manifest.jsonl \
  --default-emotion neutral
```

### 3.5 テストケース

**配置**: `tests/test_build_pea_style_bank.py`

```python
import tempfile
from pathlib import Path
import numpy as np
import torch
import pytest
from piper_train.tools.build_pea_style_bank import (
    EmotionAudioDataset, save_style_bank
)


def test_emotion_audio_dataset_from_manifest(tmp_path):
    """CSV manifest からロード."""
    audio_file = tmp_path / "sample.wav"
    sr = 16000
    t = np.arange(sr) / sr
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)

    import soundfile
    soundfile.write(str(audio_file), audio, sr)

    manifest = tmp_path / "manifest.csv"
    manifest.write_text("sample.wav,angry\n")

    dataset = EmotionAudioDataset(tmp_path, manifest_path=manifest)
    assert len(dataset) == 1
    assert dataset[0]["emotion"] == "angry"


def test_crema_d_filename_parsing(tmp_path):
    """CREMA-D ファイル名から emotion 抽出."""
    audio_dir = tmp_path / "AudioWAV"
    audio_dir.mkdir()

    # Dummy wav
    sr = 16000
    audio = np.zeros(sr, dtype=np.float32)
    import soundfile
    soundfile.write(str(audio_dir / "1001_IWW_ANG_HI.wav"), audio, sr)
    soundfile.write(str(audio_dir / "1001_IWW_HAP_XX.wav"), audio, sr)

    dataset = EmotionAudioDataset(tmp_path)
    assert len(dataset) == 2

    emotions = sorted({s["emotion"] for s in dataset.samples})
    assert "angry" in emotions
    assert "happy" in emotions


def test_save_style_bank_schema(tmp_path):
    """.npz スキーマ検証."""
    output_path = tmp_path / "test_bank.npz"
    emotion_names = ["angry", "happy", "sad", "neutral"]
    emotion_centroids = torch.randn(4, 256)
    global_centroid = emotion_centroids.mean(dim=0)

    save_style_bank(output_path, emotion_names, emotion_centroids, global_centroid)

    bank = np.load(str(output_path), allow_pickle=True)
    assert "emotion_names" in bank
    assert "emotion_centroids" in bank
    assert "global_centroid" in bank

    assert bank["emotion_names"].shape[0] == 4
    assert bank["emotion_centroids"].shape == (4, 256)
    assert bank["global_centroid"].shape == (256,)
```

### 3.6 工数内訳 (Phase 3)

| タスク | 工数 |
|-------|-----|
| PE-A モデルローダー (Phase 0 と共通) | 1〜2h |
| CREMA-D データセットクラス | 4h |
| 埋め込み抽出 + 統計計算 | 4h |
| CLI + レポート生成 | 3h |
| `inject_style_labels.py` | 3h |
| テストケース + ドキュメント | 4h |
| **合計** | **約 3 日** |

---

## Phase 4: PE-A Emotion Loss 学習側統合

### 4.1 Fork からの移植マッピング

Fork `yusuke-ai/piper-plus` (コミット `314b3355`) から以下を取り込む:

| 機能 | Fork 行番号 (推定) | 本家への影響 |
|------|-----------------|----------|
| `__init__` の `pea_emotion_*` hparams | lightning.py:61-155 | 9 個の新規ハイパーパラメータ |
| `_pea_emotion_loss_enabled` property | lightning.py:218 | フラグ判定 |
| `_init_pea_emotion_loss()` | lightning.py:225-258 | style bank ロード、register_buffer |
| `_ensure_pea_emotion_model()` | lightning.py:261-297 | モデル遅延ロード、DAC 勾配制御 |
| `_compute_pea_emotion_loss()` | lightning.py:298-375 | 3項 loss 計算 |
| `training_step_g` への loss 統合 | lightning.py:831-833 | loss_gen_all への加算 |
| `add_model_specific_args` CLI 追加 | __main__.py | argparse に 9 個追加 |

### 4.2 lightning.py への patch (概要)

```python
# VitsModel.__init__ に追加 (Phase 4)
def __init__(
    self,
    # ... Phase 1 の style パラメータ ...
    pea_emotion_loss_weight: float = 0.0,
    pea_emotion_centroid_weight: float = 0.0,
    pea_emotion_margin_weight: float = 0.0,
    pea_emotion_style_bank: Optional[str] = None,
    pea_emotion_model_name: str = "facebook/pe-av-small",
    pea_emotion_sample_rate: int = 16000,
    pea_emotion_loss_every_n_steps: int = 1,
    pea_emotion_warmup_steps: int = 0,
    pea_emotion_margin: float = 0.1,
    **kwargs,
):
    ...
    self._pea_emotion_model = None
    self._pea_emotion_to_idx: dict[str, int] = {}
    if self._pea_emotion_loss_enabled:
        self._init_pea_emotion_loss()

@property
def _pea_emotion_loss_enabled(self) -> bool:
    return (
        self.hparams.pea_emotion_loss_weight > 0
        or self.hparams.pea_emotion_centroid_weight > 0
        or self.hparams.pea_emotion_margin_weight > 0
    )

def _init_pea_emotion_loss(self) -> None:
    """Load style bank .npz and register as buffers."""
    if not self._pea_emotion_loss_enabled:
        return
    style_bank = self.hparams.pea_emotion_style_bank
    if not style_bank:
        raise ValueError(
            "--pea-emotion-style-bank is required when PE-A loss is enabled"
        )
    bank = np.load(Path(style_bank), allow_pickle=True)
    emotion_names = [str(name) for name in bank["emotion_names"].tolist()]
    global_centroid = torch.as_tensor(bank["global_centroid"], dtype=torch.float32)
    emotion_centroids = torch.as_tensor(bank["emotion_centroids"], dtype=torch.float32)

    self._pea_emotion_to_idx = {name: i for i, name in enumerate(emotion_names)}

    self.register_buffer(
        "pea_emotion_global_centroid", F.normalize(global_centroid, dim=-1)
    )
    self.register_buffer(
        "pea_emotion_centroids", F.normalize(emotion_centroids, dim=-1)
    )

def _ensure_pea_emotion_model(self):
    """Lazy-load PE-A model with DAC gradient control."""
    if self._pea_emotion_model is not None:
        return self._pea_emotion_model
    from transformers import AutoModel
    model = AutoModel.from_pretrained(
        self.hparams.pea_emotion_model_name,
        trust_remote_code=True,
    )
    # DAC 勾配制御 (fork の実装を踏襲)
    # ... grad_enabled_embedder_forward wrapping ...
    self._pea_emotion_model = model
    return model

def _compute_pea_emotion_loss(self, y_hat: torch.Tensor, batch: Batch) -> Optional[torch.Tensor]:
    """Compute PE-A emotion loss (direction + centroid + margin)."""
    if not self._pea_emotion_loss_enabled:
        return None
    if self.global_step < self.hparams.pea_emotion_warmup_steps:
        return None
    every_n_steps = max(1, int(self.hparams.pea_emotion_loss_every_n_steps))
    if self.global_step % every_n_steps != 0:
        return None
    if not batch.emotions:
        return None

    # batch.emotions の有効サンプルを抽出
    valid_indices = [
        i for i, emo in enumerate(batch.emotions)
        if emo in self._pea_emotion_to_idx
    ]
    if not valid_indices:
        return None

    # emotion → index
    emotion_indices = torch.as_tensor(
        [self._pea_emotion_to_idx[batch.emotions[i]] for i in valid_indices],
        dtype=torch.long, device=y_hat.device,
    )

    # y_hat を PE-A sample rate に resampling
    audio = y_hat[valid_indices]
    if self.hparams.sample_rate != self.hparams.pea_emotion_sample_rate:
        audio = torchaudio.functional.resample(
            audio,
            orig_freq=self.hparams.sample_rate,
            new_freq=self.hparams.pea_emotion_sample_rate,
        )

    # Embedding 抽出
    pea_model = self._ensure_pea_emotion_model()
    embeddings = pea_model.get_audio_embeds(audio)
    embeddings = F.normalize(embeddings, dim=-1)

    centroids = self.pea_emotion_centroids
    global_centroid = self.pea_emotion_global_centroid

    target_centroids = centroids.index_select(0, emotion_indices)
    target_dirs = F.normalize(target_centroids - global_centroid.unsqueeze(0), dim=-1)
    embedding_dirs = F.normalize(embeddings - global_centroid.unsqueeze(0), dim=-1)

    loss = torch.zeros((), device=y_hat.device)

    if self.hparams.pea_emotion_loss_weight > 0:
        loss_dir = (1.0 - F.cosine_similarity(embedding_dirs, target_dirs, dim=-1).mean())
        loss = loss + loss_dir * self.hparams.pea_emotion_loss_weight

    if self.hparams.pea_emotion_centroid_weight > 0:
        loss_centroid = (1.0 - F.cosine_similarity(embeddings, target_centroids, dim=-1).mean())
        loss = loss + loss_centroid * self.hparams.pea_emotion_centroid_weight

    if self.hparams.pea_emotion_margin_weight > 0:
        similarities = embeddings @ centroids.t()
        target_similarity = similarities.gather(1, emotion_indices[:, None]).squeeze(1)
        similarities.scatter_(1, emotion_indices[:, None], float("-inf"))
        max_other_sim, _ = similarities.max(dim=1)
        loss_margin = F.relu(self.hparams.pea_emotion_margin + max_other_sim - target_similarity).mean()
        loss = loss + loss_margin * self.hparams.pea_emotion_margin_weight

    return loss

# training_step_g に追加
def training_step_g(self, ...):
    # ... 既存の loss 計算 ...
    loss_pea_emotion = self._compute_pea_emotion_loss(y_hat, batch)
    if loss_pea_emotion is not None:
        loss_gen_all = loss_gen_all + loss_pea_emotion
        self.log("loss_pea_emotion", loss_pea_emotion, ...)
    # ...
```

### 4.3 DAC 勾配制御の検証

Fork の `_ensure_pea_emotion_model()` で DAC (Discrete Audio Codec) の勾配制御:

```python
def grad_enabled_embedder_forward(embedder, x):
    """Wrap PE-A embedder forward to control DAC gradients."""
    with torch.cuda.amp.autocast(enabled=False):
        with torch.backends.cudnn.flags(enabled=False):
            return embedder(x)
```

**意図**:
- DAC 自体の勾配を止めつつ、DAC 後の連続投影層には勾配を通す
- cuDNN 無効化で量子化層の勾配計算を安定化

**本家統合時の対応**:
- `--pea-emotion-loss-weight 0.0` (既定) なら PE-A 関連コード非実行 → 影響なし
- `> 0` のみ有効化
- cuDNN 無効化の性能影響: **推定 -10〜20% 学習速度**

### 4.4 CLI オプション設計

| オプション | 既定 | 型 | 説明 |
|----------|------|-----|------|
| `--pea-emotion-loss-weight` | 0.0 | float | 方向ロスの重み (c_dir) |
| `--pea-emotion-centroid-weight` | 0.0 | float | セントロイドロスの重み (c_centroid) |
| `--pea-emotion-margin-weight` | 0.0 | float | マージンロスの重み (c_margin) |
| `--pea-emotion-style-bank` | None | Path | `.npz` style bank ファイル |
| `--pea-emotion-model-name` | `"facebook/pe-av-small"` | str | HF モデル ID |
| `--pea-emotion-sample-rate` | 16000 | int | PE-A 入力 SR |
| `--pea-emotion-loss-every-n-steps` | 1 | int | Skip-step (毎 N step) |
| `--pea-emotion-warmup-steps` | 0 | int | 開始遅延 |
| `--pea-emotion-margin` | 0.1 | float | Cosine margin |

### 4.5 推奨プリセット

**初期実験 (Phase 5 Stage 5b)**:
```bash
--pea-emotion-loss-weight 0.1 \
--pea-emotion-centroid-weight 0.1 \
--pea-emotion-margin-weight 0.05 \
--pea-emotion-loss-every-n-steps 4 \
--pea-emotion-warmup-steps 2000
```

**品質重視**:
```bash
--pea-emotion-loss-weight 0.2 \
--pea-emotion-centroid-weight 0.15 \
--pea-emotion-margin-weight 0.1 \
--pea-emotion-loss-every-n-steps 1 \
--pea-emotion-warmup-steps 1000
```

### 4.6 テストケース

**配置**: `tests/test_pea_emotion_loss.py`

```python
def test_pea_emotion_loss_disabled_by_default():
    """全 weight=0 でロス無効."""

def test_pea_emotion_loss_enabled_flag():
    """任意の weight > 0 でフラグ有効化."""

def test_pea_emotion_loss_requires_style_bank():
    """weight > 0 + style_bank=None で ValueError."""

def test_pea_emotion_warmup_delay():
    """warmup_steps 以前は None を返す."""

def test_pea_emotion_every_n_steps_skip():
    """skip step では None を返す."""

def test_pea_emotion_loss_shape():
    """ロス出力が scalar."""
```

### 4.7 既存学習との互換性確認

- 既存チェックポイントロード: `--load_weights_from_checkpoint` で shape チェック、PE-A buffer は新規初期化
- Backward 互換: `--pea-emotion-loss-weight 0.0` で PE-A loss 計算を skip
- Memory: PE-A モデル非ロード (weights=0 時)
- 推論グラフ: PE-A loss は学習時専用、ONNX グラフに含まれず

### 4.8 工数内訳 (Phase 4)

| タスク | 工数 |
|-------|-----|
| PE-A loss 計算ロジック実装 | 5h |
| lightning.py への統合 | 3h |
| CLI オプション追加 | 2h |
| DAC 勾配制御テスト | 3h |
| ユニットテスト (6 テスト) | 4h |
| ドキュメント + エラーメッセージ | 2h |
| CI 確認 + 学習レグレッション | 3h |
| **合計** | **約 1.5 週間 (22h)** |

---

## 合計工数と依存関係

```
Phase 0 (PoC): 1〜2h
     ↓
Phase 1 (学習側, style_vector): 1 週間
     ↓
┌────┴────┐
│         │
Phase 3    Phase 4
(ツール, 3日) (PE-A loss, 1.5週間)
│         │
└────┬────┘
     ↓
Phase 5 (fine-tune, 3〜5日)
```

---

## リスクと対策

| リスク | 確度 | 対策 |
|-------|------|------|
| PE-A モデル transformers 自動ロード不可 | 中 | Phase 0 で要検証、カスタム loader コード整備 |
| CREMA-D DL 失敗 / 破損 | 低 | GitHub mirror or HF datasets 代替準備 |
| Style bank 生成メモリ不足 | 低 | `batch_size=1` で処理 (PE-A は可変長のため) |
| fine-tune での catastrophic forgetting | 中 | `--base_lr 2e-5` + `--freeze-dp` + `--ema-decay 0.9995` |
| PE-A loss が NaN で不安定 | 中 | `--pea-emotion-warmup-steps 2000`、`every_n_steps 4` |
| PE-A API (get_audio_embeds) 名の差異 | 中 | Phase 0 で確定、`build_pea_style_bank.py` に反映 |

---

## 参考

- Fork ブランチ: https://github.com/yusuke-ai/piper-plus/tree/feature/2026-04-14-2312-peav-style-conditioning
- CREMA-D: https://github.com/CheyneyComputerScience/CREMA-D
- PE-A 論文: https://arxiv.org/abs/2512.19687
- `facebook/pe-av-small`: https://huggingface.co/facebook/pe-av-small
- Phase 0-1 計画: [phase-0-1.md](phase-0-1.md)
- Phase 5 計画: [phase-5.md](phase-5.md)
