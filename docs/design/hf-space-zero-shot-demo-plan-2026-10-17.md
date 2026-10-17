# HF Space zero-shot デモ 実装計画 (Issue #790 / ステップ 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** HF Space `ayousanz/piper-plus-demo` に、参照音声 (アップロード / マイク録音) から声を写して合成できる実験的な zero-shot タブを追加する。

**Architecture:** 既存の多言語 TTS タブは変更せず、`gr.Tabs` で zero-shot タブを並べる。zero-shot の処理は gradio に依存しない `huggingface-space/zero_shot.py` に閉じ込め、公開済み zs-v1 (`base.onnx` + `campplus.onnx`) を revision 固定 + SHA256 照合で遅延ダウンロードする。話者ベクトル抽出と音素化は、CI (`scripts/public_base_runtime.py`) と zs-v1 同梱 `examples/` で検証済みの手順 (torchaudio Kaldi fbank → 平均減算 → CAM++ → L2 正規化、`piper_plus` の `MultilingualPhonemizer` + `PiperVoice`) をそのまま使う。

**Tech Stack:** Python 3.13 / Gradio 6.26.0 / onnxruntime / torch + torchaudio 2.11.0 (CPU wheel) / huggingface_hub / `src/python_run/piper_plus` (deploy 時にコピー)

**Spec:** Issue #790 「デモに zero shot を試せる機能を入れる」と、本計画の前段調査 (2026-10-17 セッション)。正本の手順: `scripts/public_base_runtime.py:82-191`、`docs/design/zero-shot-base-zs-v1-release-2026-10-10.md`、`docs/reference/speaker-encoder-contract.md`。

## Global Constraints

- モデルは `ayousanz/piper-plus-base` revision `3620ed788667cb76f08bd6cf2db8152c1f4c8bd1` の `releases/zs-v1/` 固定。SHA256: `base.onnx` = `e9860701a941db02149c7cfbe19cfb578c235c5e25020f1f592131d9b3b30f84`、`base.onnx.json` = `d085681edaa5029c54ea8329f3f23ed347ba46ca15cd80e766de9a6a643dafc0`、`campplus.onnx` = `a6ac6a63997761ae2997373e2ee1c47040854b4b759ea41ec48e4e42df0f4d73`。値は `scripts/public_base_runtime.py:14-21` と一致させる。
- 話者ベクトル: 16 kHz mono、`torchaudio.compliance.kaldi.fbank(num_mel_bins=80, frame_length=25, frame_shift=10, dither=0.0, sample_frequency=16000)`、フレーム方向の平均減算、CAM++ 入力名 `input` 形状 `[1, T, 80]`、出力 192 次元を L2 正規化。ゼロベクトルでの代用は禁止。
- 音素化: `MultilingualPhonemizer(languages=["ja","en","zh","es","fr","pt"], default_latin_language=<言語 if en/es/fr/pt else "en">)`、空白と `",.;:!¡¿…—–-«»"` を除外、base の `phoneme_id_map` にない音素は**エラー** (黙って捨てない)。prosody は `PiperVoice` 既定どおりゼロ。
- 推論既定値は base config の `inference` (noise_scale 0.667 / length_scale 1.0 / noise_w 0.8)。
- 既存タブの `MODELS` (6 件) と挙動は変更しない (`test-hf-space.yml` の `len(app.MODELS) == 6` を維持)。
- gradio の pin は 4 箇所同期 (`check_hf_space_gradio_sync.py`)。今回は gradio を上げない。
- 依存追加で license の変わるものは入れない。torch/torchaudio (BSD)、huggingface_hub (Apache-2.0)。CONTRIBUTING の License Policy により配布物に GPL/LGPL は入れない (CI 手順の soxr HQ は LGPL のため、リサンプルは torchaudio の kaiser_best 相当で代替。soxr との CAM++ cosine 0.9992 を実測)。
- UI 文言: 「実験版・品質未承認」「本人の同意のない声を使わないこと」を zero-shot タブ上部に必ず表示する。
- Python 実行は `uv run`。ローカルテストは `uv run --no-sync pytest <path> --no-cov`。

## Review Focus

1. **Gradio マイク録音の int16 配列**: `gr.Audio(type="numpy")` は `(sr, int16 ndarray)` を返し、ステレオなら `[N, 2]`。float に直さずに fbank に入れると振幅が 32768 倍になる → Task 1 のテスト `test_int16_stereo_is_scaled_and_downmixed` で固定。
2. **短すぎる / 無音の参照音声**: 0.1 秒未満や全ゼロ入力で NaN や 0 除算にならず、利用者向けのエラーになること → `test_rejects_short_reference` / `test_rejects_silent_reference`。
3. **長すぎる参照音声**: 数分の録音で CPU を占有しないよう先頭 30 秒に切る → `test_long_reference_is_truncated`。
4. **学習していない音素を含むテキスト** (ハングル、言語選択の取り違え): 黙って欠落させず、欠けた音素を列挙してエラー → Task 1 `test_untrained_phonemes_raise`。
5. **HF からの取得失敗・同時アクセス**: 取得失敗時も既存タブは動き、zero-shot タブだけがエラーを出す。同時に押されてもダウンロードとセッション生成は 1 回 → Task 1 `test_assets_loaded_once_under_concurrency`、Task 2 `test_ui_maps_errors_to_gr_error`。

---

## File Structure

| ファイル | 責務 |
|---|---|
| Create `huggingface-space/zero_shot.py` | 固定値、資産の取得と検証、話者ベクトル抽出、音素化、合成。gradio を import しない |
| Create `huggingface-space/zs-v1/base.onnx.json` | zs-v1 config (6,417 B) をリポジトリに同梱。オフラインのテストと実行で使う |
| Create `huggingface-space/tests/test_zero_shot.py` | `zero_shot.py` の単体テスト (偽 CAM++ セッション使用、ネットワーク不要) と `integration` マークの実モデルテスト |
| Create `huggingface-space/tests/test_app_zero_shot.py` | UI ハンドラのエラー変換と `create_interface()` 構築 |
| Modify `huggingface-space/app.py` | `gr.Tabs` 化と zero-shot タブ、ハンドラ `synthesize_zero_shot_ui` |
| Modify `huggingface-space/requirements.txt` | torch/torchaudio CPU wheel、huggingface_hub |
| Modify `huggingface-space/README.md` | frontmatter `python_version`、zero-shot の説明、CAM++ と zs-v1 の帰属表示 |
| (変更なし) `.gitignore` | ONNX は HF キャッシュに置きリポジトリには入れないため不要。config はルート `.gitignore` の `models/` を避けて `huggingface-space/zs-v1/` に置く |
| Modify `.github/workflows/deploy-huggingface.yml` | コピー対象・paths・import 検証の追加 |
| Modify `.github/workflows/test-hf-space.yml` | 同上 + pytest 実行 layer + 実モデル smoke layer |
| Modify `tests/scripts/test_check_python_licenses.py` | requirements の `--extra-index-url` 行を Requirement 解析から除外 |
| Modify `docs/features/webui.md:75-78`、`CHANGELOG.md` (Unreleased) | 「参照音声入力はない」の記述更新と変更履歴 |

---

### Task 1: `zero_shot.py` — 資産取得・話者ベクトル・音素化・合成

**Files:**

- Create: `huggingface-space/zero_shot.py`
- Create: `huggingface-space/zs-v1/base.onnx.json` (pinned revision から取得し SHA を照合して配置)
- Test: `huggingface-space/tests/test_zero_shot.py`

**Interfaces:**

- Produces:
  - 定数 `BASE_REPO: str`、`BASE_REVISION: str`、`FILE_SHA256: dict[str, str]` (3 ファイル)、`LANGUAGES: tuple[str, ...] = ("ja","en","zh","es","fr","pt")`、`MIN_REFERENCE_SECONDS = 0.1`、`MAX_REFERENCE_SECONDS = 30.0`、`ENCODER_SAMPLE_RATE = 16000`
  - `class ZeroShotInputError(ValueError)` — 利用者の入力が原因のエラー (UI で gr.Error に変換)
  - `def to_mono_float(sample_rate: int, audio: np.ndarray) -> tuple[int, np.ndarray]` — int16/int32/float、`[N]`/`[N, C]` を float32 mono `[-1, 1]` に
  - `def extract_speaker_embedding(sample_rate: int, audio: np.ndarray, encoder: onnxruntime.InferenceSession) -> np.ndarray` — `(192,)` float32、L2 ノルム 1
  - `def phoneme_ids_for_base(text: str, language: str, voice: PiperVoice) -> list[int]`
  - `class ZeroShotEngine` — `__init__(self, cache_dir: Path | None = None, downloader: Callable[[str], Path] | None = None)`、`def load(self) -> None` (lock 付きで 1 回だけ取得・検証・セッション生成)、`def synthesize(self, text: str, language: str, reference: tuple[int, np.ndarray], length_scale: float = 1.0, noise_scale: float = 0.667, noise_w: float = 0.8) -> tuple[int, np.ndarray]` (sample_rate, int16 1-D)
  - `def get_engine() -> ZeroShotEngine` — モジュール単位のシングルトン

- [ ] **Step 1: config を同梱する**

`https://huggingface.co/ayousanz/piper-plus-base/resolve/3620ed788667cb76f08bd6cf2db8152c1f4c8bd1/releases/zs-v1/base.onnx.json` を `huggingface-space/zs-v1/base.onnx.json` に保存し、`sha256sum` が `d085681e…dafc0` であることを確認する。

- [ ] **Step 2: 失敗するテストを書く** (`huggingface-space/tests/test_zero_shot.py`)

偽 encoder は `get_inputs()` が名前 `input` を返し、`run(None, {"input": x})` で `x.shape` を記録して固定ベクトル (例 `np.arange(1, 193)`) を返す小クラス。`PiperVoice` は `PiperVoice(config=PiperConfig.from_dict(json.load(base.onnx.json)), session=None)` で作る (ID 変換は session を使わない)。

```python
def test_bundled_config_matches_pinned_sha():
    assert sha256(CONFIG_PATH) == zero_shot.FILE_SHA256["base.onnx.json"]

def test_pins_match_ci_verifier():
    from scripts import public_base_runtime as pbr
    assert zero_shot.BASE_REVISION == pbr.BASE_REVISION
    assert zero_shot.FILE_SHA256 == pbr.FILES

def test_int16_stereo_is_scaled_and_downmixed():
    audio = np.array([[32767, -32768], [16384, 16384]], dtype=np.int16)
    sr, mono = zero_shot.to_mono_float(48000, audio)
    assert sr == 48000 and mono.dtype == np.float32 and mono.shape == (2,)
    assert np.all(np.abs(mono) <= 1.0)
    assert mono[1] == pytest.approx(0.5, abs=1e-4)

def test_embedding_is_unit_norm_and_uses_16k_fbank(fake_encoder):
    audio = (0.1 * np.sin(2 * np.pi * 220 * np.arange(48000) / 48000)).astype(np.float32)
    emb = zero_shot.extract_speaker_embedding(48000, audio, fake_encoder)
    assert emb.shape == (192,) and emb.dtype == np.float32
    assert np.linalg.norm(emb) == pytest.approx(1.0, abs=1e-5)
    batch, frames, bins = fake_encoder.last_input_shape
    assert (batch, bins) == (1, 80) and 95 <= frames <= 100   # 1 秒 → 約 98 フレーム

def test_rejects_short_reference(fake_encoder):
    with pytest.raises(zero_shot.ZeroShotInputError, match="0.1"):
        zero_shot.extract_speaker_embedding(16000, np.zeros(800, np.float32) + 0.1, fake_encoder)

def test_rejects_silent_reference(fake_encoder):
    with pytest.raises(zero_shot.ZeroShotInputError):
        zero_shot.extract_speaker_embedding(16000, np.zeros(16000, np.float32), fake_encoder)

def test_long_reference_is_truncated(fake_encoder):
    audio = (0.1 * np.random.default_rng(0).standard_normal(16000 * 120)).astype(np.float32)
    zero_shot.extract_speaker_embedding(16000, audio, fake_encoder)
    assert fake_encoder.last_input_shape[1] <= 30 * 100

@pytest.mark.parametrize("key,language,text", pbr.TEXTS)
def test_phoneme_ids_match_ci_recipe(base_voice, key, language, text):
    # pbr.prepare() と同じ手順を独立に組み立てた期待値と一致すること
    assert zero_shot.phoneme_ids_for_base(text, language, base_voice) == expected_ids(text, language, base_voice)

def test_untrained_phonemes_raise(base_voice):
    with pytest.raises(zero_shot.ZeroShotInputError, match="untrained|未学習"):
        zero_shot.phoneme_ids_for_base("안녕하세요", "ja", base_voice)

def test_unknown_language_raises(base_voice):
    with pytest.raises(zero_shot.ZeroShotInputError):
        zero_shot.phoneme_ids_for_base("hej", "sv", base_voice)

def test_assets_loaded_once_under_concurrency(tmp_path):
    calls = []
    engine = zero_shot.ZeroShotEngine(cache_dir=tmp_path, downloader=counting_downloader(calls))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: engine.load(), range(8)))
    assert sorted(calls) == ["base.onnx", "campplus.onnx"]

def test_sha_mismatch_is_rejected(tmp_path):
    engine = zero_shot.ZeroShotEngine(cache_dir=tmp_path, downloader=writes_garbage)
    with pytest.raises(RuntimeError, match="SHA256"):
        engine.load()
```

`counting_downloader` / `writes_garbage` は `downloader(filename) -> Path` の偽物。前者は SHA 照合を通すため `zero_shot._verify` を monkeypatch で無効化して呼び出し名だけ記録する。

`@pytest.mark.integration` の実モデルテスト `test_real_model_conditioning_changes_audio` も同ファイルに置く: 実際に `get_engine().load()` し、つくよみちゃん参照 (`public_base_runtime` の URL と `REFERENCE_SHA256`) で ja-1 を合成、(a) 出力が有限で 0.3 秒以上、(b) 同じ参照で 2 回の話者ベクトルが一致、(c) 符号反転した話者ベクトルで合成した音声が元と異なる、を確認する (`public_base_runtime.py` の conditioning チェックと同じ考え方。品質判定ではない)。

- [ ] **Step 3: テストが失敗することを確認**

Run: `$env:PYTHONPATH="huggingface-space;src/python_run;src/python;."; uv run --no-sync pytest huggingface-space/tests/test_zero_shot.py -m "not integration" --no-cov -q`
Expected: `ModuleNotFoundError: No module named 'zero_shot'`

- [ ] **Step 4: `zero_shot.py` を実装する**

- 取得: 既定 downloader は `huggingface_hub.hf_hub_download(repo_id=BASE_REPO, revision=BASE_REVISION, filename=f"releases/zs-v1/{name}", cache_dir=...)`。`base.onnx` と `campplus.onnx` だけ取得し、config は同梱ファイルを使う。取得後に全 3 ファイルを SHA256 照合 (`hashlib.sha256` を 1 MiB ずつ。`hashlib.file_digest` は使わない)。
- `load()` は `threading.Lock` で二重実行を防ぎ、`PiperVoice.load(base.onnx, config_path=同梱 config)` と CAM++ 用 `onnxruntime.InferenceSession(providers=["CPUExecutionProvider"])` を作る。`speaker_embedding` 入力があり `sid` がないことを確認する (`public_base_runtime.py:137-140` と同じ)。
- `extract_speaker_embedding`: `to_mono_float` → 先頭 `MAX_REFERENCE_SECONDS` 秒に切る → 0.1 秒未満 / ピーク振幅 < 1e-4 なら `ZeroShotInputError` → `torchaudio.functional.resample` (kaiser_best 相当) で 16 kHz → Global Constraints の fbank → 平均減算 → CAM++ → 有限・非ゼロを確認して L2 正規化。torch / torchaudio は関数内で import する (ruff の `PLC0415` は `huggingface-space/*.py` で許可済み)。
- `phoneme_ids_for_base`: `LANGUAGES` 外は `ZeroShotInputError`。Global Constraints の音素化 → 未学習音素があれば `sorted(missing)` を含む `ZeroShotInputError` → `voice.phonemes_to_ids(phones)`。
- `synthesize`: `load()` → 話者ベクトル → ID → `voice.synthesize_ids_to_raw(ids, language_id=voice.config.language_id_map[language], speaker_embedding=emb, length_scale=..., noise_scale=..., noise_w=...)` → `np.frombuffer(..., dtype=np.int16)`、sample_rate は `voice.config.sample_rate`。
- 話者ベクトルのキャッシュは入れない (YAGNI。1 回の抽出は CPU で 1 秒未満の見込み)。

- [ ] **Step 5: 単体テストが通ることを確認**

Run: Step 3 と同じコマンド
Expected: 全件 PASS

- [ ] **Step 6: 実モデルテストを確認**

Run: `$env:PYTHONPATH="huggingface-space;src/python_run;src/python;."; uv run --no-sync pytest huggingface-space/tests/test_zero_shot.py -m integration --no-cov -q`
Expected: PASS。生成音声を `huggingface-space/tests/` 外 (scratchpad) に保存して聴感を一度確認する (品質判定ではなく「声が出ていて参照に寄っている」程度)。

- [ ] **Step 7: Commit**

```bash
git add huggingface-space/zero_shot.py huggingface-space/zs-v1/base.onnx.json huggingface-space/tests/test_zero_shot.py
git commit -m "feat(hf-space): zs-v1 の zero-shot 推論モジュールを追加 (#790)"
```

---

### Task 2: `app.py` — zero-shot タブ

**Files:**

- Modify: `huggingface-space/app.py:214-341` (`create_interface`)
- Test: `huggingface-space/tests/test_app_zero_shot.py`

**Interfaces:**

- Consumes: `zero_shot.get_engine()`、`ZeroShotEngine.synthesize(...)`、`zero_shot.ZeroShotInputError`、`zero_shot.LANGUAGES`
- Produces: `def synthesize_zero_shot_ui(text: str, language: str, reference: tuple[int, np.ndarray] | None, length_scale: float, noise_scale: float, noise_w: float) -> tuple[int, np.ndarray]`

- [ ] **Step 1: 失敗するテストを書く**

`app` の import は `download_models()` と NLTK ダウンロードを走らせるため、テストは `test-hf-space.yml` と同じく deploy ディレクトリ相当 (`PYTHONPATH` に `huggingface-space`) で実行し、`zero_shot.get_engine` を monkeypatch した偽エンジンを使う。

```python
def test_ui_requires_reference():
    with pytest.raises(gr.Error, match="参照音声|reference"):
        app.synthesize_zero_shot_ui("こんにちは", "ja", None, 1.0, 0.667, 0.8)

def test_ui_maps_errors_to_gr_error(monkeypatch):
    monkeypatch.setattr(app.zero_shot, "get_engine", lambda: RaisingEngine(zero_shot.ZeroShotInputError("too short")))
    with pytest.raises(gr.Error, match="too short"):
        app.synthesize_zero_shot_ui("こんにちは", "ja", (16000, np.ones(16000, np.int16)), 1.0, 0.667, 0.8)

def test_ui_maps_download_failure_to_gr_error(monkeypatch):
    monkeypatch.setattr(app.zero_shot, "get_engine", lambda: RaisingEngine(OSError("hub down")))
    with pytest.raises(gr.Error):
        app.synthesize_zero_shot_ui("こんにちは", "ja", (16000, np.ones(16000, np.int16)), 1.0, 0.667, 0.8)

def test_ui_rejects_empty_text():
    with pytest.raises(gr.Error):
        app.synthesize_zero_shot_ui("  ", "ja", (16000, np.ones(16000, np.int16)), 1.0, 0.667, 0.8)

def test_interface_builds_with_zero_shot_tab():
    assert len(app.MODELS) == 6
    assert app.create_interface() is not None
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `$env:PYTHONPATH="huggingface-space;src/python_run;src/python;."; uv run --no-sync pytest huggingface-space/tests/test_app_zero_shot.py --no-cov -q`
Expected: FAIL (`AttributeError: module 'app' has no attribute 'synthesize_zero_shot_ui'`)

- [ ] **Step 3: 実装する**

- `create_interface()` の中身を `with gr.Tabs():` → `gr.Tab("Multilingual TTS")` (既存 UI をそのまま移す) と `gr.Tab("Zero-shot (experimental)")` に分ける。
- zero-shot タブ: 冒頭 Markdown (実験版・品質未承認・未知話者の再現は不完全・本人の同意のない声を使わない・参照音声はサーバーに保存しない)、言語 Dropdown (`zero_shot.LANGUAGES`、既定 `ja`)、Textbox (既定 `SAMPLE_TEXTS["ja"]`、言語変更で差し替え)、`gr.Audio(sources=["upload", "microphone"], type="numpy", label="Reference audio (3-30 s)")`、スライダー 3 本 (既定 1.0 / 0.667 / 0.8)、ボタン、出力 `gr.Audio(type="numpy")`。
- `synthesize_zero_shot_ui`: 空テキスト・参照なしを `gr.Error` に。`ZeroShotInputError` は文言そのまま、その他の例外は `logger.exception` した上で「モデルの読み込みまたは合成に失敗しました」の `gr.Error` に変換。
- `create_minimal_interface()` は変更しない。

- [ ] **Step 4: テストが通ることを確認**

Run: Step 2 と同じ
Expected: 全件 PASS

- [ ] **Step 5: ローカルで起動して手動確認**

Run: `huggingface-space` で `uv run --no-sync python app.py` (`PYTHONPATH` は上と同じ)
Expected: 既存タブで日本語合成ができる。zero-shot タブでファイルアップロードとマイク録音の両方から合成できる。0.05 秒の音声と韓国語テキストで分かりやすいエラーが出る。

- [ ] **Step 6: Commit**

```bash
git add huggingface-space/app.py huggingface-space/tests/test_app_zero_shot.py
git commit -m "feat(hf-space): zero-shot タブを追加 (#790)"
```

---

### Task 3: 依存・README・デプロイ / CI

**Files:**

- Modify: `huggingface-space/requirements.txt`、`huggingface-space/README.md`
- Modify: `.github/workflows/deploy-huggingface.yml`、`.github/workflows/test-hf-space.yml`
- Modify: `tests/scripts/test_check_python_licenses.py:49-57`

**Interfaces:**

- Consumes: Task 1/2 のファイル一式
- Produces: deploy bundle `hf-space-deploy/` に `zero_shot.py`、`zs-v1/base.onnx.json`、`piper_plus/` (`src/python_run/piper_plus` のコピー) が入ること

- [ ] **Step 1: license テストを先に直す (失敗の確認)**

`requirements.txt` に `--extra-index-url https://download.pytorch.org/whl/cpu` を入れると `Requirement("--extra-index-url ...")` が `InvalidRequirement` で落ちる。先に requirements を変更して `uv run --no-sync pytest tests/scripts/test_check_python_licenses.py --no-cov -q` が FAIL することを確認し、`-` で始まる行 (pip オプション) を宣言の解析から除外する。

requirements.txt に追加する行:

```text
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.11.0+cpu         # zero-shot: CAM++ 前処理の Kaldi fbank (BSD-3-Clause)
torchaudio==2.11.0+cpu    # torchaudio.compliance.kaldi.fbank (BSD-2-Clause)
huggingface_hub>=0.30     # zs-v1 の revision 固定ダウンロード (Apache-2.0)
```

Expected (修正後): PASS

- [ ] **Step 2: README を更新する**

- frontmatter に `python_version: "3.13"` を追加 (CI の `setup-python` と揃える。`check_hf_space_frontmatter.py` は未知キーを拒否しない)。
- 「Zero-shot (experimental)」節: 使い方、制約 (実験版・品質未承認・173 音素の旧音素表のため学習していない音素はエラー・参照音声は保存しない)、同意の注意。
- Credits に zs-v1 (`ayousanz/piper-plus-base` の pinned `releases/zs-v1/`、MIT) と CAM++ (`releases/zs-v1/licenses/CAMPP-APACHE-2.0.txt`、`NOTICE.md` へのリンク) を追加。
- `_Last updated_` 行を更新。

Run: `python scripts/check_hf_space_frontmatter.py; python scripts/check_hf_space_gradio_sync.py`
Expected: 両方 OK

- [ ] **Step 3: (不要) `.gitignore`**

ONNX は `hf_hub_download` の HF キャッシュに保存されるため変更不要。`huggingface-space/zs-v1/base.onnx.json` が ignore されず追跡されていることだけ確認する。

- [ ] **Step 4: `deploy-huggingface.yml`**

- `on.push.paths` に `src/python_run/piper_plus/**` と `huggingface-space/zs-v1/**` は `huggingface-space/**` に含まれるので前者だけ追加。
- Prepare: `cp huggingface-space/zero_shot.py`、`cp -r huggingface-space/zs-v1 hf-space-deploy/`、`cp -r src/python_run/piper_plus hf-space-deploy/` (`__pycache__` 除外)。`huggingface-space/tests/` はコピーしない。
- import 検証リストに `("zero_shot", "ZeroShotEngine")`、`("piper_plus.voice", "PiperVoice")`、`("piper_plus.phonemize.multilingual", "MultilingualPhonemizer")` を追加 (検証 step の `pip install` に `huggingface_hub` を追加。torch は関数内 import なので不要)。

- [ ] **Step 5: `test-hf-space.yml`**

- `push.paths` / `pull_request.paths` に `src/python_run/piper_plus/**`、`scripts/public_base_runtime.py`、`tests/scripts/test_check_python_licenses.py` を追加。
- Prepare に Step 4 と同じコピーを追加。
- 新 layer「Layer 6: zero-shot unit tests」: `pip install -r requirements.txt pytest` 済みの環境で `PYTHONPATH=hf-space-deploy:. pytest huggingface-space/tests -m "not integration" -q -p no:cacheprovider --no-cov` (repo の pytest.ini の `--cov` を回避)。
- 新 layer「Layer 7: zero-shot real-model smoke」: `pytest huggingface-space/tests -m integration -q --no-cov`。HF からの取得を伴うため `timeout-minutes: 15`。
- 既存 Layer 5 の `len(app.MODELS) == 6` はそのまま。

- [ ] **Step 6: ローカルで deploy bundle を再現して確認**

deploy workflow の Prepare と同じコピーを scratchpad の一時ディレクトリに行い、そこで `python -c "import app; app.create_interface()"` が通ることを確認。

- [ ] **Step 7: Commit**

```bash
git add huggingface-space/requirements.txt huggingface-space/README.md .github/workflows/deploy-huggingface.yml .github/workflows/test-hf-space.yml tests/scripts/test_check_python_licenses.py
git commit -m "ci(hf-space): zero-shot の依存とデプロイ・テスト経路を追加 (#790)"
```

---

### Task 4: ドキュメントと PR

**Files:**

- Modify: `docs/features/webui.md:75-78`、`CHANGELOG.md` (Unreleased)

- [ ] **Step 1: ドキュメント更新**

`docs/features/webui.md` の「どちらの WebUI にも参照音声 / 埋め込みの入力は無い」を、HF Space には zero-shot タブがあり Docker WebUI には無い、に修正。`CHANGELOG.md` Unreleased に「HF Space に実験的 zero-shot タブを追加 (#790)」。重大度マーカーは付けない。

- [ ] **Step 2: ローカル総合確認**

Run: `uv run pre-commit run --files <変更ファイル>` と Task 1-3 のテスト一式
Expected: すべて PASS (Windows の autocrlf/cp932 由来の偽失敗は除く)

- [ ] **Step 3: Commit と PR**

`/commit` でコミット後、`/create-pr` で dev 向け PR を作成 (本文に「聴感確認は機能確認であり品質承認ではない」「Pages 対応は別 PR」を明記)。マージ後に `deploy-huggingface.yml` が走り、post-deploy 検証で Space が RUNNING になることと、実 Space で zero-shot タブが動くことを確認する。

---

## 決定事項 (2026-10-17 ユーザー確認済み)

1. **既定の参照音声サンプルは置かない**: Examples に参照音声は入れず、アップロード / 録音のみ。
2. **Space の Python は 3.13 を指定する**: frontmatter に `python_version: "3.13"` を追加し、CI の `setup-python` と揃える。
