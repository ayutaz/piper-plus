# Multilingual Dataset Plan (6 Languages)

> **ステータス: 完了 (2026-03-16)** — このプランは実装済みです。dataset-multilingual-6lang-filtered として508,187発話 / 571話者 / 6言語のデータセットが作成されました。

## Overview

Piper TTS の多言語対応に向けたデータセット計画。既存の JA+EN バイリンガルモデル (v4) を拡張し、ZH/ES/FR/PT の4言語を追加して6言語モデルを構築する。

**設計方針:**
- 全言語で商用利用可能なライセンスに統一
- 韓国語 (KO) はオープンな TTS コーパスが CC-BY-NC-SA 4.0 (KSS) しかなく、ライセンス制約のため除外

---

## Final Dataset Configuration

| Language | Dataset | Hours | Speakers | Download Size | License | Source SR | Notes |
|----------|---------|-------|----------|--------------|---------|-----------|-------|
| JA | Existing v4 | ~78h | 20 | 0 (local) | -- | 22,050 Hz | MoE Speech 20 speakers |
| EN | Existing v4 | ~92h | 310 | 0 (local) | -- | 22,050 Hz | LibriTTS-R 310 speakers |
| ZH | AISHELL-3 | 85h | 218 | 19 GB | Apache-2.0 | 44,100 Hz | Mandarin, pinyin transcripts |
| ES | CML-TTS Spanish | 443h | 77 | 48 GB | CC-BY 4.0 | 24,000 Hz | LibriVox audiobooks |
| FR | CML-TTS French | 284h | 45 | 31 GB | CC-BY 4.0 | 24,000 Hz | LibriVox audiobooks |
| PT | CML-TTS Portuguese | 68h | 30 | 9.7 GB | CC-BY 4.0 | 24,000 Hz | LibriVox audiobooks (BR) |
| **Total** | | **~1,050h** | **~700** | **~108 GB** | **All commercial OK** | | |

---

## Dataset Details

### ZH: AISHELL-3

- **URL**: https://www.openslr.org/93/
- **File**: `data_aishell3.tgz` (19 GB)
- **Content**: 88,035 utterances, 218 native Mandarin speakers, ~85 hours
- **License**: Apache License 2.0
- **Sample Rate**: 44,100 Hz (downsample to 22,050 Hz)
- **Format**: WAV + pinyin/character-level transcripts
- **Attributes**: Gender, age group, native accent labels
- **Mirrors**: EU (trmal.net, elda.org), CN (magicdatatech.com)

**Why AISHELL-3:**
- Apache-2.0 is the most permissive license among ZH TTS datasets
- 218 speakers with ~85h provides good per-speaker density (~23 min/speaker)
- TTS-specific design with high-quality studio recordings
- Pinyin transcripts available (useful for G2P validation)

**Alternatives considered:**
| Dataset | Hours | Speakers | License | Reason rejected |
|---------|-------|----------|---------|----------------|
| WenetSpeech4TTS Premium | 945h | many | CC-BY-4.0 (non-commercial clause) | Non-commercial despite CC-BY label |
| CSS10 Chinese | 6.5h | 1 | CC-BY-SA 4.0 | Too small |

### ES: CML-TTS Spanish

- **URL**: https://www.openslr.org/146/
- **File**: `cml_tts_dataset_spanish_v0.1.tar.bz` (48 GB)
- **Content**: ~443 hours, 77 speakers (45 male, 57 female)
- **License**: CC-BY 4.0
- **Sample Rate**: 24,000 Hz (downsample to 22,050 Hz)
- **Source**: LibriVox audiobooks
- **Mirrors**: EU (trmal.net, elda.org), CN (magicdatatech.com)

**Why CML-TTS:**
- CC-BY 4.0 allows commercial use
- 24 kHz source (clean downsample to 22,050 Hz, no quality loss)
- 77 speakers with 443h provides excellent per-speaker density (~5.7h/speaker)
- Same pipeline as FR/PT (unified preprocessing)

**Alternatives considered:**
| Dataset | Hours | Speakers | License | Reason rejected |
|---------|-------|----------|---------|----------------|
| MLS Spanish | 918h | 86 | CC-BY 4.0 | 16 kHz (upsampling to 22 kHz is lossy) |
| CSS10 Spanish | 19.2h | 1 | CC-BY-SA 4.0 | Single speaker, small |
| M-AILABS Spanish | unknown | unknown | BSD 3-Clause | Limited documentation |

### FR: CML-TTS French

- **URL**: https://www.openslr.org/146/
- **File**: `cml_tts_dataset_french_v0.1.tar.bz` (31 GB)
- **Content**: ~284 hours, 45 speakers (43 male, 20 female)
- **License**: CC-BY 4.0
- **Sample Rate**: 24,000 Hz (downsample to 22,050 Hz)
- **Source**: LibriVox audiobooks
- **Mirrors**: EU (trmal.net, elda.org), CN (magicdatatech.com)

**Why CML-TTS:**
- Same rationale as ES: CC-BY 4.0, 24 kHz, LibriVox-based
- 45 speakers with 284h (~6.3h/speaker)
- Gender imbalance (male-heavy) but acceptable for multi-speaker model

**Alternatives considered:**
| Dataset | Hours | Speakers | License | Reason rejected |
|---------|-------|----------|---------|----------------|
| MLS French | 1,077h | 142 | CC-BY 4.0 | 16 kHz (upsampling lossy) |
| CSS10 French | 15.2h | 1 | CC-BY-SA 4.0 | Single speaker, small |
| SIWIS | 10h | 1 | Free | Single speaker, small |

### PT: CML-TTS Portuguese

- **URL**: https://www.openslr.org/146/
- **File**: `cml_tts_dataset_portuguese_v0.1.tar.bz` (9.7 GB)
- **Content**: ~68 hours, 30 speakers (26 male, 13 female)
- **License**: CC-BY 4.0
- **Sample Rate**: 24,000 Hz (downsample to 22,050 Hz)
- **Source**: LibriVox audiobooks (Brazilian Portuguese)
- **Mirrors**: EU (trmal.net, elda.org), CN (magicdatatech.com)

**Why CML-TTS:**
- Same pipeline as ES/FR
- 30 speakers with 68h (~2.3h/speaker)
- Smallest dataset in the plan but still reasonable for multi-speaker training

**Alternatives considered:**
| Dataset | Hours | Speakers | License | Reason rejected |
|---------|-------|----------|---------|----------------|
| MLS Portuguese | 161h | 42 | CC-BY 4.0 | 16 kHz (upsampling lossy) |
| TTS-Portuguese Corpus | 10.5h | 1 | CC-BY 4.0 | Single speaker, too small |

---

## Excluded: Korean (KO)

**Reason**: No open Korean TTS corpus with a commercial-friendly license exists.

| KO Dataset | Hours | Speakers | License | Issue |
|-----------|-------|----------|---------|-------|
| KSS | 12h | 1 | CC-BY-NC-SA 4.0 | Non-commercial, ShareAlike propagates |
| Zeroth Korean | 52h | 105 | CC-BY 4.0 | ASR-quality smartphone recordings |
| Pansori-TEDxKR | 3h | 41 | CC-BY-NC-ND 4.0 | Too small, NoDerivatives |
| AIHub Multi-speaker | 10,152h | 3,495 | Korea residents only | Geographic restriction |
| NIKL | 120h | many | Application required | Opaque access process |
| CoreaSpeech | 700h | 21,449 | CC-BY-NC 4.0 | Non-commercial, availability unclear |

**OSS TTS projects universally use KSS** (ESPnet, Coqui, Piper, VITS). No LibriVox-based Korean corpus exists (CSS10, CML-TTS, MLS all lack Korean) due to insufficient Korean audiobooks on LibriVox.

Korean can be added in a future phase if a suitable open corpus becomes available.

---

## Disk Space Budget

### Current State

| Item | Size |
|------|------|
| Total disk | 2.0 TB |
| Used | 1,002 GB (49%) |
| Free | ~1.1 TB |

### Cleanable (old checkpoints + datasets)

| Path | Size | Description |
|------|------|-------------|
| `output-bilingual-ja-en/lightning_logs/` | 45 GB | v1 checkpoints (200 epoch) |
| `output-bilingual-ja-en-v2/lightning_logs/` | 36 GB | v2 checkpoints |
| `output-bilingual-ja-en-v3/lightning_logs/` | 63 GB | v3 checkpoints |
| `dataset-bilingual-ja-en-enhanced-fixed/` | 244 GB | Old enhanced-fixed dataset |
| **Total cleanable** | **~388 GB** | |

### New Data Requirements

| Item | Compressed | Extracted (est.) |
|------|-----------|-----------------|
| AISHELL-3 | 19 GB | ~30 GB |
| CML-TTS Spanish | 48 GB | ~80 GB |
| CML-TTS French | 31 GB | ~50 GB |
| CML-TTS Portuguese | 9.7 GB | ~15 GB |
| Processed dataset (22 kHz, cache) | -- | ~100 GB |
| **Total new** | **~108 GB** | **~275 GB** |

**After cleanup**: ~1.1 TB free + 388 GB reclaimed = ~1.5 TB available. 275 GB required. **Sufficient.**

---

## Preprocessing Pipeline

### Sample Rate Conversion

All source data must be resampled to 22,050 Hz (Piper's native rate):

| Source | Original SR | Method | Quality Impact |
|--------|------------|--------|---------------|
| JA (existing) | 22,050 Hz | None | -- |
| EN (existing) | 22,050 Hz | None | -- |
| AISHELL-3 | 44,100 Hz | Downsample (integer ratio 2:1) | None |
| CML-TTS (ES/FR/PT) | 24,000 Hz | Downsample (fractional) | Negligible |

### Language-Specific Processing

| Language | Phonemizer | G2P Backend | Notes |
|----------|-----------|-------------|-------|
| JA | JapanesePhonemizer | OpenJTalk + pyopenjtalk | Existing, prosody features (A1/A2/A3) |
| EN | EnglishPhonemizer | g2p-en (Apache-2.0) | Existing, GPL-free |
| ZH | ChinesePhonemizer | pypinyin + tone sandhi | Implemented in feat/multilingual-phonemizer |
| ES | SpanishPhonemizer | Rule-based + stress | Implemented in feat/multilingual-phonemizer |
| FR | FrenchPhonemizer | Rule-based | Implemented in feat/multilingual-phonemizer |
| PT | PortuguesePhonemizer | Rule-based (BR) | Implemented in feat/multilingual-phonemizer |

### Speaker ID Allocation Plan

| Language | Speaker ID Range | Count |
|----------|-----------------|-------|
| JA | 0 -- 19 | 20 |
| EN | 20 -- 329 | 310 |
| ZH | 330 -- 547 | 218 |
| ES | 548 -- 624 | 77 |
| FR | 625 -- 669 | 45 |
| PT | 670 -- 699 | 30 |
| **Total** | 0 -- 699 | **700** |

### Language ID Map

| Language | language_id |
|----------|------------|
| ja | 0 |
| en | 1 |
| zh | 2 |
| es | 3 |
| fr | 4 |
| pt | 5 |

---

## Download Commands

```bash
# AISHELL-3 (19 GB)
wget -c https://openslr.trmal.net/resources/93/data_aishell3.tgz \
  -O /data/piper/downloads/data_aishell3.tgz

# CML-TTS Spanish (48 GB)
wget -c https://openslr.trmal.net/resources/146/cml_tts_dataset_spanish_v0.1.tar.bz \
  -O /data/piper/downloads/cml_tts_dataset_spanish_v0.1.tar.bz

# CML-TTS French (31 GB)
wget -c https://openslr.trmal.net/resources/146/cml_tts_dataset_french_v0.1.tar.bz \
  -O /data/piper/downloads/cml_tts_dataset_french_v0.1.tar.bz

# CML-TTS Portuguese (9.7 GB)
wget -c https://openslr.trmal.net/resources/146/cml_tts_dataset_portuguese_v0.1.tar.bz \
  -O /data/piper/downloads/cml_tts_dataset_portuguese_v0.1.tar.bz
```

---

## References

- AISHELL-3: https://www.openslr.org/93/
  - Paper: https://arxiv.org/abs/2010.11567
- CML-TTS: https://www.openslr.org/146/
  - Paper: https://arxiv.org/abs/2306.10097
  - GitHub: https://github.com/freds0/CML-TTS-Dataset
- MLS (reference): https://www.openslr.org/94/
  - Paper: https://arxiv.org/abs/2012.03411
- CSS10 (reference): https://github.com/Kyubyong/css10
- KSS (excluded): https://www.kaggle.com/datasets/bryanpark/korean-single-speaker-speech-dataset
