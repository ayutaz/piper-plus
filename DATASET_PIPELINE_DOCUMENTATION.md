# Piper-Plus: Bilingual Dataset Pipeline & Hinglish Voice Cloning Documentation

This document provides a comprehensive, end-to-end technical overview of all work completed for the **Hindi**, **English**, and **Hinglish** datasets in the `piper-plus` repository, including all created scripts, modified files, bug fixes, and upload instructions.

---

## 1. Executive Summary of Datasets

| Dataset | Source / Origin | Volume / Specs | Role in Project | Location |
|---|---|---|---|---|
| **Hindi Dataset** | AI4Bharat IndicVoices-R (`ai4bharat/indicvoices_r`) | ~95 GB raw, processed into multi-speaker 22.05 kHz audio | Core Hindi acoustic modeling and phoneme representation | `data/raw-hi-en/indicvoices_r_hi` & `data/dataset-hi-en` |
| **English Dataset** | OpenSLR LibriTTS-R (`train-clean-100`) | ~9.0 GB raw, balanced subset of clean studio English | Core English acoustic modeling & code-switching anchor | `data/raw-hi-en/libritts_r_en` & `data/dataset-hi-en` |
| **Unified Training Dataset** | Combined Hindi + English | **117.67 hours**, 58,567 utterances, 631 speakers, 202 symbols | Ready-to-train Piper VITS multi-speaker checkpoint | `data/dataset-hi-en/` |
| **Hinglish Synthetic Dataset** | DeepSeek API (Text) + F5-TTS (Voice Cloning) | 40+ programming tutor dialogues in Latin script, 22.05 kHz cloned audio | Fine-tuning/evaluation dataset for Indian AI Programming Tutor | `dataset_output/` (`metadata.txt` + `wavs/`) |

---

## 2. Hindi & English Pipeline Details

### A. Hindi Dataset (`IndicVoices-R`)
* **Download Automation ([`download_hindi.py`](file:///Users/sama/Desktop/piper-plus/download_hindi.py)):**
  * Automated downloader using `huggingface_hub.snapshot_download`.
  * Securely authenticates via Hugging Face token loaded from `.env`.
  * Filters and downloads the Hindi subset (`data/hi/*`) including audio archives (`.tar.gz`) and metadata CSVs.
  * Destination: `data/raw-hi-en/indicvoices_r_hi/`.
* **Preprocessing & Phonemization ([`src/python/piper_train/tools/prepare_hindi_english_dataset.py`](file:///Users/sama/Desktop/piper-plus/src/python/piper_train/tools/prepare_hindi_english_dataset.py)):**
  * Parses transcription metadata and filters audio by duration (0.5s to 12.0s) and quality.
  * Resamples audio to **22,050 Hz, 16-bit Mono PCM** using `soxr` and `soundfile`.
  * Phonemizes Hindi Devanagari text into International Phonetic Alphabet (IPA) tokens via Piper G2P (`piper_plus_g2p.hi`).

### B. English Dataset (`LibriTTS-R`)
* **Download Automation ([`download_english.py`](file:///Users/sama/Desktop/piper-plus/download_english.py)):**
  * Downloads the high-fidelity `train-clean-100` split from OpenSLR.
  * Automatically extracts archives and arranges directory hierarchies.
  * Destination: `data/raw-hi-en/libritts_r_en/`.
* **Balancing & Integration:**
  * Aligns speaker IDs across Hindi and English partitions to prevent language dominance.
  * Phonemizes English text using CMU Pronouncing Dictionary & English G2P (`piper_plus_g2p.en`).
  * Generates pre-computed Mel-spectrogram and phoneme tensors into `data/dataset-hi-en/cache/` (117,134 cached `.pt` files).

---

## 3. Hinglish Dataset & Voice Cloning Pipeline

The objective was to create synthetic Indian English / Hinglish programming tutor speech with a consistent voice persona.

### A. Synthetic Dialogue Text Generation ([`generate_hinglish_text.py`](file:///Users/sama/Desktop/piper-plus/generate_hinglish_text.py))
* Uses the **DeepSeek API** (`deepseek-chat` model) with structured prompt instructions.
* **Script Specification:** Strictly uses **Latin/English characters (A-Z)** for Hinglish (e.g., *"Aapke code mein syntax error hai, dekhiye missing parenthesis."*).
* Automatically extracts and cleans JSON structured utterances, formatting them into standard Piper `metadata.txt`:
  ```text
  file_id|transcription_text
  ```
* Output saved to: [`dataset_output/metadata.txt`](file:///Users/sama/Desktop/piper-plus/dataset_output/metadata.txt).

### B. Master Reference Audio & Transcript ([`master_references/`](file:///Users/sama/Desktop/piper-plus/master_references/))
Zero-shot voice cloning models (F5-TTS) require an exact word-for-word transcript of the reference speaker audio to capture timbre, pitch, and prosody accurately.
* **Audio File:** [`master_references/cloned_indian_tutor_master.wav`](file:///Users/sama/Desktop/piper-plus/master_references/cloned_indian_tutor_master.wav)
  * Clean 8.49-second recording of an Indian speaker.
  * Formatted to 22,050 Hz Mono PCM.
* **Transcript File:** [`master_references/cloned_indian_tutor_master.txt`](file:///Users/sama/Desktop/piper-plus/master_references/cloned_indian_tutor_master.txt)
  * Exact text:
    > *"afterwords the teacher from navgurukul decided to do a class project with Abhishek to see what kind of impact the recognition would have on the community."*

### C. Voice Cloning & Audio Synthesis ([`generate_hinglish_audio.py`](file:///Users/sama/Desktop/piper-plus/generate_hinglish_audio.py))
* **Engine:** F5-TTS (Flow-matching diffusion speech synthesis).
* **Mac Compatibility & Stability:**
  * Configured `--device cpu` as default to bypass Apple MPS limitations on `ComplexFloat` during spectrogram STFT computation.
  * Automatically loads the transcript from `master_references/cloned_indian_tutor_master.txt`.
* **Smart Resume / Skip Logic:**
  * Checks if an utterance WAV already exists before synthesizing. Interrupted runs resume without redundant work.
* **Automatic Piper Resampling:**
  * Resamples generated audio to **22,050 Hz, 16-bit Mono PCM** using `soundfile` and `soxr`.
  * Destination: `dataset_output/wavs/`.

---

## 4. Code Modifications & Bug Fixes

Several core repository files were patched to ensure seamless environment compatibility with Python 3.11, PyTorch 2.2.2, and F5-TTS on macOS:

### 1. [`src/python/piper_train/_compat.py`](file:///Users/sama/Desktop/piper-plus/src/python/piper_train/_compat.py)
* **Problem:** In PyTorch 2.2.2, calling `torch.serialization.add_safe_globals` directly failed if the function was not exposed in specific builds.
* **Fix:** Added dynamic attribute resolution (`getattr(_torch.serialization, "add_safe_globals", None)`), ensuring safe fallback for legacy weights.

### 2. [`src/python/piper_train/vits/mel_processing.py`](file:///Users/sama/Desktop/piper-plus/src/python/piper_train/vits/mel_processing.py)
* **Problem:** Direct top-level import `from librosa.filters import mel as librosa_mel_fn` caused circular import conflicts during dataset tensor generation.
* **Fix:** Refactored into a lazy getter function `_get_librosa_mel()` called on-demand.

### 3. [`src/python/g2p/piper_plus_g2p/registry.py`](file:///Users/sama/Desktop/piper-plus/src/python/g2p/piper_plus_g2p/registry.py)
* **Problem:** Non-installed language phonemizers (like Japanese or Chinese) raised `ImportError` instead of `ModuleNotFoundError`, which triggered warning traces.
* **Fix:** Expanded the exception handler to catch `(ModuleNotFoundError, ImportError)`, logging clean skip notices.

### 4. F5-TTS Dependency & Runtime Fixes (`.venv`)
* **`torch.xpu` AttributeError:** Patched `f5_tts/infer/utils_infer.py` to use `hasattr(torch, "xpu") and torch.xpu.is_available()`.
* **Transformers Version Pin:** Downgraded `transformers` from `5.17.0` (which required PyTorch >= 2.5) to `4.44.2` (fully compatible with PyTorch 2.2.2 on macOS x86_64).

### 5. Configuration Files
* **[`pyproject.toml`](file:///Users/sama/Desktop/piper-plus/pyproject.toml):** Added `[tool.pyrefly]` search paths.
* **[`pyrefly.toml`](file:///Users/sama/Desktop/piper-plus/pyrefly.toml):** Created project-level Pyrefly type checking configuration.
* **[`.vscode/settings.json`](file:///Users/sama/Desktop/piper-plus/.vscode/settings.json):** Set workspace Python interpreter to `.venv/bin/python`.

---

## 5. File Inventory (What Was Created & Modified)

| File Path | Status | Description |
|---|---|---|
| `download_hindi.py` | **NEW** | Script to download Hindi subset of IndicVoices-R from Hugging Face |
| `download_english.py` | **NEW** | Script to download and extract LibriTTS-R clean-100 dataset |
| `src/python/piper_train/tools/prepare_hindi_english_dataset.py` | **NEW** | Master preprocessing, balancing, resampling, and tensor caching tool |
| `tests/test_phase2_dataset_prep.py` | **NEW** | Unit test suite verifying dataset generation and tensor caching |
| `generate_hinglish_text.py` | **NEW** | DeepSeek API script generating Latin-script Hinglish tutor dialogues |
| `generate_hinglish_audio.py` | **NEW** | F5-TTS voice cloning script with CPU fallback & auto-resampling |
| `master_references/cloned_indian_tutor_master.wav` | **NEW** | Reference audio clip for Indian tutor voice cloning |
| `master_references/cloned_indian_tutor_master.txt` | **NEW** | Exact word-for-word transcript for the reference audio |
| `dataset_output/metadata.txt` | **NEW** | Generated Hinglish dialogue metadata (`file_id\|text`) |
| `dataset_output/wavs/` | **NEW** | Directory where cloned 22.05 kHz Hinglish audio is stored |
| `pyrefly.toml` | **NEW** | Configuration for Pyrefly type checker |
| `.vscode/settings.json` | **NEW** | VS Code configuration pointing to `.venv` |
| `DATASET_PIPELINE_DOCUMENTATION.md` | **NEW** | This comprehensive documentation document |
| `pyproject.toml` | **MODIFIED** | Added Pyrefly tool configuration |
| `src/python/piper_train/_compat.py` | **MODIFIED** | Compatibility patch for `add_safe_globals` |
| `src/python/piper_train/vits/mel_processing.py` | **MODIFIED** | Lazy loading for Librosa Mel filter |
| `src/python/g2p/piper_plus_g2p/registry.py` | **MODIFIED** | Exception handling for missing third-party phonemizers |

---


