# Zero-Shot 参照融合 (GPT-SoVITS v2Pro型) 実験・実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

作成日: 2026-10-17。状態: **計画。コード変更・レンタル・学習は未実施**。

> **改訂1 (2026-10-18):** S0のG0でCAM++統計 (F-stats) が不合格 (話者分割LDAプローブ平均 −0.0083、3/10 split勝ち。[S0記録](../research/zero-shot-reference-fusion-s0-2026-10.md))。§6の分岐に従い主候補をF-mel (参照スペクトログラムの小型encoder) へ切り替えた。Task 5〜10は§8で置き換える。§5のTask 5〜10本文はF-stats版の記録として残す。
作成時のPiperソース: `638b18f5558d4421c6614de7531b0c8cb4cc4be8` (`feat/zero-shot-v8-dataset-scaling`)。

**Goal:** GPT-SoVITS v2Proと同じ「話者照合モデルのpooling前特徴を既存global条件へ加算する」経路をPiperに実装し、未知話者の声の再現性が上がるかを、容量対照付きで$1000以内に判定する。

**Architecture:** CAM++の192次元に加え、同じCAM++のpooling前統計 (平均+標準偏差、1024次元) を事前抽出し、zero-initの小型MLPで`spk_proj`出力へ加算する。融合後のgは従来どおりenc_p・DP・flow・decoder・enc_qへ入るため、ONNXでは入力が1本増えるだけになる。GPUの前に、既存モデルのまま推論側の参照処理 (無音trim、複数参照の平均位置) をCPUで確かめる。

**Tech Stack:** PyTorch / Lightning、`piper_train.speaker_encoder.campplus_torch.CAMPPlus` (凍結)、ONNX Runtime、`uv run`、pytest。

**Spec:** 本書が上位計画 [zero-shot-gpt-sovits-adoption-plan-2026-10-17.md](zero-shot-gpt-sovits-adoption-plan-2026-10-17.md) (以下「元計画」) の §3〜§9 を改訂する。根拠は同日の上流精読・コード照合 (§1)。元計画の §1.2用語、§5.2評価集合、§9.1指標、§10運用は変更せず引き継ぐ。

## Global Constraints

- Python実行は `uv run`、依存追加は `uv add`。テストは `uv run --no-sync pytest <path> --no-cov`。
- Torch処理はGPUを使えるときGPU、ONNX検証はCPU (`CUDA_VISIBLE_DEVICES=""`)。
- 新機能はすべてopt-in。既定値で旧checkpoint・旧ONNX・旧CLIの出力を変えない。
- 既存schema FP16 TTS 40MB、生成CPU p50 +10%以内を維持。新schemaの追加入力で事後に緩和しない。
- テスト閾値を実測に合わせて緩めない。緩める場合は `# threshold-relaxed: <根拠>` を付ける (pre-commit gate)。
- SECSはcross-utteranceのみ、CAM++とnative ECAPAの両方で測る。`goodhart_flag`/`above_ceiling_flag`がtrueなら改善と呼ばない。
- 新経路にCAM++/ECAPA由来の追加損失を足さない (固定encoderのスコアを目標にした崩壊が過去2回)。
- `git commit --no-verify` 禁止。コミットはfeatureブランチに都度行い、devへ直接コミットしない。
- 公開・既定モデル差し替え・リリースは本計画の完了条件に含めない。

## Review Focus

1. 全区間が無音・極短の参照WAV → trim後に音声が残らない場合は黙って未trim音声へ戻さず、理由付きで拒否する (Task 2)。
2. 長い参照 (数十秒) のFP16集計 → 平均がoverflowして0/Infにならず、fp32で有限値を返す (Task 3)。上流v2Proで無音出力事故あり。
3. 融合付きcheckpointを融合なしの旧コードやstreaming exportへ渡す → 黙って融合を落とさず明示エラー (Task 6, Task 9)。
4. referenceとtargetが同一音声 (別path・別cropの同一hashを含む) → 学習を始めない (Task 7)。
5. 新schemaのONNXを未対応runtimeに渡す → `reference_features`を無視して合成せず、明示エラー (Task 10)。

---

## 1. 調査で確定した前提と、元計画からの変更

### 1.1 上流 (GPT-SoVITS main `1b47ca07`) の事実

| 事実 | 根拠 | 計画への意味 |
|---|---|---|
| SoVITS (v1/v2/v2Pro) の参照条件は時間平均したglobal `ge` 1本。enc_p (MRTE後)・flow・decoder・enc_qへ入る | `GPT_SoVITS/module/models.py` L911-944, L957-962 | 参照token列 (元計画R2) に上流の前例はない |
| v2Proは話者照合モデルERes2NetV2の**pooling前**特徴を時間平均した20480次元を`Linear`で写像し`ge`へ加算→PReLU | `models.py` L928-944、`eres2net/ERes2NetV2.py` L240-251 | CAM++のpooling前統計で同型の経路を作れる |
| 学習時の参照は生成対象と同じ発話。話者損失なし | `module/data_utils.py` L109-134、`s2_train.py` L445-450 | 自己参照でも動くが、AR段の補助がないPiperでは別発話の方が安全 |
| v2Proで長い参照のFP16時間平均がoverflowし無音出力、修正で学習が発散し再修正 | `module/modules.py` L716-726、commit 8056efe4→ed89a023 | 集計はfp32で行う |
| 参照encoder入力を約11kHz以下 (32kHzの704 bin) に制限 | `models.py` L912-915 | Piperは22.05kHz (上限11.025kHz)、CAM++は16kHzのため**既に同等以下**。追加作業なし |
| 自己申告SIM: v2 .549 → v2Pro .709 → ProPlus .737。複数変更が同時に入っており分離不能。英語の第三者評価は低い | wiki、CosyVoice2論文 | 上流の数値を目標値にしない |

### 1.2 Piperのコードで確定した事実

| 事実 | 場所 |
|---|---|
| 学習用CAM++は`audio_norm`から抽出。推論の参照WAVはtrimせずにfbank化する。**訂正 (2026-10-18、Ruling R14):** multilingual datasetのcacheは既定でVADなし + soxr MQ (`prepare_multilingual_dataset` → `norm_audio.cache_norm_audio_no_vad(resample_quality="MQ")`) で、`audio_norm`はVAD trim済みとは限らない。VAD trim (16kHz上のenergy VAD + soxr HQ) をするのは別のbuilder `norm_audio.cache_norm_audio_fast`。v10bの実データがどちらで作られたかはS2のdata auditで確定する | `extract_speaker_embedding.py` L102-136 (学習) / L65-99 (推論)、`norm_audio/__init__.py` (`cache_norm_audio_fast` / `cache_norm_audio_no_vad`)、`tools/prepare_multilingual_dataset.py` (`resample_quality="MQ"`) |
| Gへは生成対象と同じ発話の埋め込み。G・SCL・swap・Latent Fillingが1つの`speaker_embeddings`を共有 | `vits/lightning.py` L1963, L2059, L2283, L2418 |
| `spk_proj`はLinear(192→512)→LN→GELU→Linear。gは`[B,512,1]` | `vits/models.py` L1459-1490 |
| 話者情報損失の78%がdecoder段。prior/flowを完璧にしても上限は+0.04 (recon bound 0.714)。融合後のgはdecoderのFiLMにも入るが、decoderの描画歪みを直す保証はない | [zero-shot-v11-conditioning-design.md §10.1](zero-shot-v11-conditioning-design.md#101-チェーン会計--話者情報はどこで死ぬか実測) |
| CAM++のpooling直前は512ch (`out_nonlinear`出力)。`StatsPool`で平均+標準偏差1024次元 | `speaker_encoder/campplus_torch.py` L334-410 |
| 再開失敗時に`strict=False`のweights-only読込へ自動で切り替わる | `__main__.py` L1962-1989 |
| streaming exportは非対応構造を`check_streaming_export_supported`で拒否する仕組みがある | `export_onnx_streaming.py` L71-95 |
| 研究ブランチはdevより169 commit先行、devに未収録 | `git rev-list origin/dev..HEAD` |

### 1.3 元計画からの変更点

| 元計画 | 本計画 | 理由 |
|---|---|---|
| 主候補R1 (pooled) / R2 (K=8 token) を**prior直前**に注入 | 主候補は**F-stats**: CAM++ pooling前統計をzero-init MLPで`spk_proj`出力へ加算。gの全注入先へ届く | 上流v2Proの忠実な類似物。prior単独は上限+0.04。ONNX変更が入力1本で済む |
| 新規の小型mel encoderを学習 | 第2段階へ延期 (F-mel)。F-statsのpilotで経路の価値を確認してから | 凍結・事前抽出で済むF-statsの方が安く、mel encoderは参照specの追加読込が必要 |
| R2 token / 2参照mask | 保留 | 上流に前例がなく、漏れの経路が太い |
| 帯域制限入力の比較 | 削除 | Piperの22.05kHz・CAM++の16kHzで既に上流と同等以下 |
| GPU前にPython/C++の参照WAV実生成まで実装 | GPU前は**ONNX export・ORT一致・未対応runtimeの拒否**まで。参照WAV入力のruntime実装は採用判断後 | 採否未定の経路にruntime実装を先行させない |
| 凍結→解除による慣らし | `requires_grad`凍結を使わず、param groupのLR倍率で慣らす | 凍結中のパラメータはEMA shadowとoptimizerに入らない (`ema.py` L58-62、`lightning.py` L2907) |
| 新しい実装ブランチをdevから作る | 現在の`feat/zero-shot-v8-dataset-scaling` (devから分岐済み) でそのまま実装する (2026-10-17 ユーザー決定) | 必要な研究commitがこのブランチにある。devへの統合は採用判断後の別作業 |
| 段階0なし | **段階0: 既存v10b ep79でのCPU検証**を追加 (§2) | trim・平均位置・特徴の有用性をGPUなしで先に確かめる |

## 2. 段階と判定ゲート

| 段階 | 内容 | GPU | 判定ゲート (次へ進む条件) |
|---|---|---|---|
| S0 CPU検証 | Task 1〜4: 再開の厳格化、参照trim、fp32集計、CAM++統計抽出。既存v10b ep79で (a) 参照trim有無、(b) 複数参照の平均を埋め込み側/g側、(c) CAM++統計の話者分離度を測る | 不要 | G0: (a)(b)の採否と、学習・推論で使うfrontendを1つに固定。(c)で統計特徴の話者分離度が192次元以上と確認 (下回れば§6の分岐) |
| S1 実装 | Task 5〜10: 融合module、Ccap、参照ペア、EMA・移行、ONNX、runtime拒否 | 不要 | G1: 全テスト成功、旧経路の出力不変、Torch/ORT一致 |
| S2 データ | 元計画§5.1の復元・監査。CAM++ 192と統計1024を、G0で固定したfrontendで**同じpassで**再抽出し来歴を記録。参照ペアmanifest作成 | 不要 | G2: 選んだ学習集合が監査通過、自己参照fallback 0 |
| S3 smoke | RTX 5090×1、bf16。各群100 batch warm start + 100 batch strict再開 | 要 | G3: 非有限値0、融合MLPの重みが変化、保存・再開が連続、回収成功 |
| S4 pilot | 4群を同じ露出量で短期比較 (§3) | 要 | G4: F-statsがCcapとC0を開発群で上回るか判定。上回らなければS5へ進まず報告 |
| S5 本比較 | C0とG4の選択候補を同露出で比較。新run 40epoch相当を初期案 | 要 | G5: 元計画§9.1の選抜条件 |
| S6 最終判定 | 最終評価群、AB試聴、ONNX/CPU計測 | 一部 | 改善/非改善/判定不能を根拠付きで区別 |

S2はS0・S1と並行できる。S3はG0〜G2がそろってから。

## 3. 比較群

| 群 | Gへの参照 | 追加module | 判別すること |
|---|---|---|---|
| E0 | (学習なし) v10b ep79 | なし | 現在のモデル |
| C0-self | 生成対象と同じ発話 | なし | v10b学習条件の継続。warm startの影響の基準 |
| C0 | 同話者の別発話 | なし | 別発話参照だけの効果 |
| Ccap | 同話者の別発話 | 192次元入力のMLP (F-statsと追加パラメータ数±5%) | 容量増の効果 |
| F-stats | 同話者の別発話 | CAM++統計1024→MLP→`spk_proj`出力へ加算 | pooling前統計の効果 |

- C0/Ccap/F-statsは参照発話・初期重み・データ順・損失・評価集合を共通にする。
- SCLの正例とGへの参照は別フィールドで管理し、SCLは従来どおり (Task 7)。
- C0-selfはpilotのみ。本比較はC0と選択候補。
- 初期重みはv10b ep79 raw。optimizer・EMA・epochは継承しない。warm restartが転写能力を回復しなかった前例 (v9) があるため、新moduleに十分な露出量を確保し、短期pilotで完成と判断しない。

## 4. 予算 ($1000、CloudRift RTX 5090 $0.65/時)

本表で元計画§8.2と`output/cloudrift-readonly-audit-20261017/assessment.json`の`budget_caps`を置き換える。

| 用途 | 上限 |
|---|---:|
| 環境構築・S3 smoke | $30 |
| warm速度計測・露出量の見積もり | $50 |
| S4 pilot (4群) | $200 |
| S5 本比較 (2群) | $430 |
| 再試行・最終export・回収 | $120 |
| 予備 | $170 |
| **合計** | **$1000** |

速度は同一processで300 batch以後の窓で測る。残額でS5とS6を完了できない見積もりなら、S5を始めず集合・群数を再設計する。

## 5. 実装タスク (S0〜S1)

作業ブランチ: 現在の`feat/zero-shot-v8-dataset-scaling`。タスクごとにコミットしてpushする。元計画ファイルと`docs/research/README.md`の未コミット変更は、ユーザーが扱いを決めるまで触らない。

### Task 1: 再開の厳格化

**Files:**
- Modify: `src/python/piper_train/__main__.py:1957-1990`
- Test: `src/python/tests/test_resume_strict.py` (新規)

**Interfaces:**
- Produces: `run_strict_resume(trainer, model, ckpt_path: str) -> None` (`__main__.py`内)。失敗時は`SystemExit`。weights-only読込は`--resume-weights-only`だけが行う。

- [ ] **Step 1: 失敗するテストを書く**

```python
def test_strict_resume_failure_does_not_fall_back(monkeypatch, tmp_path):
    trainer = FakeTrainer(raises=RuntimeError("size mismatch"))
    model = FakeModel()
    with pytest.raises(SystemExit, match="--resume-weights-only"):
        run_strict_resume(trainer, model, str(tmp_path / "x.ckpt"))
    assert model.load_state_dict_calls == []  # strict=False 読込が起きない
```

- [ ] **Step 2: 失敗を確認** — `uv run --no-sync pytest src/python/tests/test_resume_strict.py --no-cov` → FAIL (`run_strict_resume`未定義)
- [ ] **Step 3: 実装** — 既存の`try/except`ブロックを`run_strict_resume`へ移し、except節は元の例外を連鎖させた`SystemExit`に置き換える。メッセージに「weights-onlyで始めるなら `--resume-weights-only` を明示」を含める。
- [ ] **Step 4: 成功を確認** — 同コマンドPASS、`test_resume_weights_only.py`もPASS
- [ ] **Step 5: Commit** — `git add src/python/piper_train/__main__.py src/python/tests/test_resume_strict.py && git commit -m "fix(python): strict再開の失敗時にweights-onlyへ黙って切り替えない"`

### Task 2: 参照音声のtrim (学習と同じenergy VAD)

**Files:**
- Create: `src/python/piper_train/reference_frontend.py`
- Modify: `src/python/piper_train/extract_speaker_embedding.py:65-99` (`preprocess_audio`に`trim: bool = False`)、`src/python/piper_train/infer_onnx.py` (`--reference-trim {none,energy-vad}`、既定`none`)
- Test: `src/python/tests/test_reference_frontend.py` (新規)

**Interfaces:**
- Produces: `trim_reference_audio(audio: np.ndarray, sample_rate: int) -> tuple[np.ndarray, dict]`。16kHzへsoxr HQで写した複写に`energy_vad_numpy(chunk_size=480, threshold=0.02, keep_before=2, keep_after=2)`を適用し、元のsample rateの音声を切る。dictは`offset_sec`, `duration_sec`, `method="energy_vad_numpy@16k"`。有声区間がなければ`ValueError`。

- [ ] **Step 1: テストを書く**

```python
def test_trim_matches_training_vad_bounds():
    audio = np.concatenate([np.zeros(22050), tone(22050, 0.3), np.zeros(22050)])
    out, info = trim_reference_audio(audio, 22050)
    assert 0.9 < info["offset_sec"] < 1.0
    assert len(out) < len(audio)

def test_trim_rejects_all_silence():
    with pytest.raises(ValueError, match="no voiced"):
        trim_reference_audio(np.zeros(44100, dtype=np.float32), 22050)

def test_preprocess_audio_trim_default_off_is_unchanged(wav_with_silence):
    assert np.array_equal(preprocess_audio(wav_with_silence), preprocess_audio(wav_with_silence, trim=False))
```

- [ ] **Step 2: 失敗を確認** — `uv run --no-sync pytest src/python/tests/test_reference_frontend.py --no-cov` → FAIL
- [ ] **Step 3: 実装** — `reference_frontend.py`に`trim_reference_audio`、`preprocess_audio`はtrim時にfbank化前へ適用、`infer_onnx`のCAM++抽出経路にフラグを配線。
- [ ] **Step 4: 成功を確認** — 同コマンドPASS、`test_extract_speaker_embedding.py`と`test_infer_onnx_speaker_embedding_integration.py`もPASS
- [ ] **Step 5: Commit** — 変更3ファイル+テストを`git add`し`feat(python): 参照音声に学習時と同じenergy VAD trimを任意適用`

### Task 3: fp32の時間平均とCAM++統計抽出

**Files:**
- Modify: `src/python/piper_train/reference_frontend.py`
- Modify: `src/python/piper_train/extract_speaker_embedding.py` (`--per-utterance`に`--also-campp-stats`。出力は`<utt>.campp_stats.npy`とmanifestの`campp_stats_path`、来歴に`feature="campp_stats_v1"`, `dim=1024`, `frontend`, `weights_sha256`)
- Test: `src/python/tests/test_reference_frontend.py`

**Interfaces:**
- Produces: `masked_time_mean_fp32(x: Tensor[B,C,T], mask: Tensor[B,1,T]) -> Tensor[B,C]` (float32。`x/len`を先に計算してから和をとる。全mask0の行は`ValueError`)。
- Produces: `campplus_stats(model: CAMPPlus, fbank: Tensor[B,T,80]) -> Tensor[B,1024]` (`head`→`xvector`の`out_nonlinear`までを実行し、`statistics_pooling`と同じ定義の平均+標準偏差をfp32で返す。`dense`は通さない)。

- [ ] **Step 1: テストを書く**

```python
def test_masked_mean_fp16_long_input_is_finite():
    x = torch.full((1, 4, 200_000), 60000.0, dtype=torch.float16)
    out = masked_time_mean_fp32(x, torch.ones(1, 1, 200_000))
    assert out.dtype == torch.float32 and torch.isfinite(out).all()
    assert torch.allclose(out, torch.full((1, 4), 60000.0), rtol=1e-3)

def test_campplus_stats_matches_internal_statspool(campplus_random):
    fbank = torch.randn(2, 300, 80)
    stats = campplus_stats(campplus_random, fbank)
    assert stats.shape == (2, 1024)
    assert torch.allclose(stats, reference_statspool_via_hook(campplus_random, fbank), atol=1e-5)
```

- [ ] **Step 2: 失敗を確認** → FAIL
- [ ] **Step 3: 実装** — 2関数と抽出CLIのオプション。統計抽出は192次元と同じfbank入力から同じpassで行う。
- [ ] **Step 4: 成功を確認** — `test_reference_frontend.py`と`test_extract_speaker_embedding.py`がPASS
- [ ] **Step 5: Commit** — `feat(python): CAM++のpooling前統計をfp32で抽出`

### Task 4: S0のCPU検証を実行し、G0を記録

**Files:**
- Modify: `src/python/piper_train/tools/cpu_reference_comparison.py` (`reference_embedding`に`trim: bool = False`、新関数`projected_average(model, embeddings: np.ndarray) -> torch.Tensor`= 各埋め込みを`spk_proj`へ通してからg側で平均)
- Create: `docs/research/zero-shot-reference-fusion-s0-2026-10.md` (結果記録)
- Test: `src/python/tests/test_cpu_reference_comparison.py`

**Interfaces:**
- Consumes: Task 2 `trim_reference_audio`、Task 3 `campplus_stats`
- Produces: G0の判定 (`frontend`: trimの有無、複数参照の平均位置、統計特徴の採否)。S2の再抽出とTask 5〜10の既定値はこれに従う。

- [ ] **Step 1: テストを書く** — `test_projected_average_equals_single_when_one_reference` (1参照なら`spk_proj(e)`と一致)、`test_reference_embedding_trim_changes_only_with_silence` (無音なしWAVではtrimの有無で同値)
- [ ] **Step 2〜4:** FAIL確認 → 実装 → PASS (`uv run --no-sync pytest src/python/tests/test_cpu_reference_comparison.py --no-cov`)
- [ ] **Step 5: 測定** — `scripts/run_zero_shot_cpu_evaluation.py`の既存manifest (v10b ep79、raw/EMA/ONNX) で次の3条件を別出力に測る: (a) 参照trim なし/あり、(b) 2参照の埋め込み平均/g平均 (Torchのみ)、(c) 評価集合でCAM++ 192とCAM++統計1024のcross-utt同話者/別話者cosineの分離度 (AUC)。固定3文の旧結果は上書きしない。
- [ ] **Step 6: 判定と記録** — 結果記録に数値・manifest hash・G0の採否を書く。trimの採否は「CAM++/ECAPA crossがともに非退行、CER非退行」で決め、片方だけの改善は採らない。
- [ ] **Step 7: Commit** — ツール・テスト・結果記録を`git add`し`docs: 参照処理のCPU検証とG0判定を記録`

> **注:** 以下のTask 5〜10はF-stats版 (改訂1で廃止)。実装は§8のTask 5R〜10Rに従う。

### Task 5: 融合moduleと容量対照

**Files:**
- Create: `src/python/piper_train/vits/reference_fusion.py`
- Modify: `src/python/piper_train/vits/models.py:1459-1543` (`SynthesizerTrn.__init__`に`reference_fusion: str = "none"`、`reference_feature_dim: int = 1024`。`_get_speaker_condition(speaker_embeddings=None, reference_features=None)`、`_get_global_conditioning(..., reference_features=None)`、`forward`/`infer`へ`reference_features`を通す)
- Modify: `src/python/piper_train/__main__.py` (`--reference-fusion {none,campp_stats,capacity}`、既定`none`)
- Test: `src/python/tests/test_reference_fusion.py` (新規)

**Interfaces:**
- Produces: `ReferenceFusion(in_dim: int, gin_channels: int)`: `Linear(in_dim, gin)` → `PReLU(gin)` → `Linear(gin, gin)` (最後のLinearの重みとbiasをzero-init)。`forward(features: Tensor[B,in_dim]) -> Tensor[B,gin,1]`。
- Produces: `CapacityControl(gin_channels: int, target_params: int)`: 入力は192次元のCAM++埋め込み、同じ3層構成で隠れ幅を`target_params`の±5%に合わせて決める。最後のLinearはzero-init。
- Produces: `g_spk = spk_proj(e) + fusion(...)`。`reference_fusion="campp_stats"`で`reference_features`がNoneなら`ValueError`。lang成分には足さない。

- [ ] **Step 1: テストを書く**

```python
def test_fusion_none_matches_legacy_output(tiny_model_pair):
    legacy, fused = tiny_model_pair("none"), tiny_model_pair("campp_stats")
    fused.load_state_dict(legacy.state_dict(), strict=False)
    assert torch.equal(infer(legacy, seed=0), infer(fused, seed=0, reference_features=torch.randn(1, 1024)))

def test_fusion_receives_gradient_after_steps(tiny_fused_model):
    before = tiny_fused_model.reference_fusion.net[0].weight.clone()
    train_steps(tiny_fused_model, n=3)
    assert not torch.equal(before, tiny_fused_model.reference_fusion.net[0].weight)

def test_capacity_control_param_count_within_5pct():
    f, c = ReferenceFusion(1024, 512), CapacityControl(512, target_params=n_params(ReferenceFusion(1024, 512)))
    assert abs(n_params(c) - n_params(f)) / n_params(f) <= 0.05

def test_missing_reference_features_raises(tiny_fused_model):
    with pytest.raises(ValueError, match="reference_features"):
        tiny_fused_model.infer(*tiny_inputs(), speaker_embeddings=torch.randn(1, 192))
```

- [ ] **Step 2: 失敗を確認** — `uv run --no-sync pytest src/python/tests/test_reference_fusion.py --no-cov` → FAIL
- [ ] **Step 3: 実装** — module、モデル配線、CLI。`spk_proj`を直接呼ぶ箇所 (`vits/lightning.py` L2459 DINO、`models.py` L1900/L1950/L2091、`vits/telemetry.py` L101) は`_get_speaker_condition`経由に揃え、融合有効時に`reference_features`を渡す。
- [ ] **Step 4: 成功を確認** — 新テストと`test_speaker_embedding.py`、`test_adaln_encp.py`、`test_snac_stats_flag.py`がPASS
- [ ] **Step 5: Commit** — `feat(python): CAM++統計を話者条件へ加算する融合moduleと容量対照を追加`

### Task 6: EMA・LR慣らし・重み移行

**Files:**
- Modify: `src/python/piper_train/vits/ema.py:18-20` (両scopeに`reference_fusion`と`capacity_control`を追加)
- Modify: `src/python/piper_train/vits/lightning.py` (`configure_optimizers`で新moduleを別param groupにし、`--reference-fusion-lr-scale` (既定1.0) と`--reference-fusion-warmup-steps` (既定0) を適用。`requires_grad`は変更しない)
- Modify: `src/python/piper_train/checkpoint_io.py`
- Test: `src/python/tests/test_reference_fusion.py`、`src/python/tests/test_checkpoint_io.py`、`src/python/tests/test_ema_scope_extended.py`

**Interfaces:**
- Produces: `load_state_with_allowed_missing(model, state_dict: dict, allowed_prefixes: tuple[str, ...]) -> dict` (返り値は`{"missing": [...], "unexpected": [...]}`。許可prefix以外のmissing、unexpected、shape差は`ValueError`)。`--resume-weights-only`は融合有効時にこれを`allowed_prefixes=("reference_fusion.", "capacity_control.")`で使う。
- Produces: 融合付きcheckpointを`reference_fusion="none"`のモデルへ読むと`ValueError` (unexpected keys)。

- [ ] **Step 1: テストを書く** — `test_ema_tracks_reference_fusion_in_legacy_and_extended`、`test_fusion_param_group_lr_scale`、`test_allowed_missing_accepts_only_fusion_keys`、`test_fused_checkpoint_into_legacy_model_raises`
- [ ] **Step 2〜4:** FAIL確認 → 実装 → PASS (`uv run --no-sync pytest src/python/tests/test_reference_fusion.py src/python/tests/test_checkpoint_io.py src/python/tests/test_ema_scope_extended.py src/python/tests/test_resume_weights_only.py --no-cov`)
- [ ] **Step 5: Commit** — `feat(python): 融合moduleのEMA登録・LR慣らし・許可key付き移行`

### Task 7: 学習時の参照ペア (SCLとの分離)

**Files:**
- Modify: `src/python/piper_train/vits/dataset.py:238-323, 618-691` (jsonlの`reference_utterance_id`・`reference_embedding_path`・`reference_feature_path`を読み、Batchに`reference_embeddings: Tensor[B,192] | None`、`reference_features: Tensor[B,1024] | None`、`reference_utterance_ids: list[str] | None`を追加)
- Modify: `src/python/piper_train/vits/lightning.py:1963-2060` (Gには`reference_embeddings`があればそれを、なければ従来の`speaker_embeddings`を渡す。SCL・swap・Latent Fillingは`speaker_embeddings`のまま)
- Modify: `src/python/piper_train/zero_shot_requirements.py`
- Create: `src/python/piper_train/tools/build_reference_pairs.py`
- Test: `src/python/tests/test_reference_pairs.py` (新規)

**Interfaces:**
- Produces: `validate_reference_pairs(utterance_ids, reference_utterance_ids, speaker_ids, splits, audio_sha256) -> None` (参照=target、別話者、別split、同一音声hashのいずれかで`ValueError`)。`--strict-zero-shot`はbatchごとに呼ぶ。
- Produces: `build_reference_pairs(entries: list[dict], seed: int) -> tuple[list[dict], dict]` (各targetに同話者・同split・別hashの参照を1つ割り当てる。候補がないtargetは除外し、除外数と理由を返す)。
- Produces: `--latent-filling-tau`または`--c-swap-spk`と融合を同時指定すると`SystemExit` (192次元のみを補間・交換するため)。

- [ ] **Step 1: テストを書く** — `test_pairs_never_self_reference`、`test_pairs_reject_same_hash_different_path`、`test_pairs_keep_split`、`test_generator_uses_reference_embeddings_while_scl_uses_target`、`test_fusion_with_latent_filling_is_rejected`
- [ ] **Step 2〜4:** FAIL確認 → 実装 → PASS (`uv run --no-sync pytest src/python/tests/test_reference_pairs.py src/python/tests/test_strict_zero_shot.py --no-cov`)
- [ ] **Step 5: Commit** — `feat(python): 学習時のG参照を別発話にしSCL入力と分離`

### Task 8: ONNX export

**Files:**
- Modify: `src/python/piper_train/export_onnx.py:33-81, 684-715` (融合有効時に入力`reference_features` `[B,1024]` float32を追加。configへ`"reference_conditioning": {"schema": "campp_stats_v1", "dim": 1024, "frontend": <G0の値>}`を記録)
- Modify: `src/python/piper_train/export_onnx_streaming.py:71-95` (`check_streaming_export_supported`で融合モデルを`NotImplementedError`)
- Test: `src/python/tests/test_export_reference_fusion.py` (新規)

**Interfaces:**
- Produces: ONNX入力名`reference_features`。融合なしモデルの入力名リストは従来と完全一致。

- [ ] **Step 1: テストを書く** — `test_legacy_export_input_names_unchanged`、`test_fused_export_has_reference_features_input`、`test_torch_ort_parity_with_reference_features` (`--no-stochastic`、FP32、atol 1e-4)、`test_streaming_export_rejects_fusion`
- [ ] **Step 2〜4:** FAIL確認 → 実装 → PASS (`CUDA_VISIBLE_DEVICES="" uv run --no-sync pytest src/python/tests/test_export_reference_fusion.py src/python/tests/test_export_onnx.py --no-cov`)
- [ ] **Step 5: Commit** — `feat(python): 参照融合モデルのONNX exportとstreaming拒否`

### Task 9: 評価経路の接続

**Files:**
- Modify: `src/python/piper_train/tools/generate_eval_audio.py:181-231` (manifestの参照WAVから、G0のfrontendでCAM++ 192と統計1024を作りfeedする。manifestへfrontend・特徴hashを記録)
- Modify: `src/python/piper_train/evaluation_manifest.py:246-261`
- Test: `src/python/tests/test_zs_eval_integration.py`

**Interfaces:**
- Consumes: Task 3 `campplus_stats`、Task 8 の入力名
- Produces: 融合モデルの評価で`reference_features`が欠けると例外。旧モデルの評価出力は不変。

- [ ] **Step 1〜4:** `test_eval_feeds_reference_features_for_fused_model`、`test_eval_legacy_model_unchanged`、`test_eval_manifest_records_frontend_and_feature_hash` をFAIL→実装→PASS
- [ ] **Step 5: Commit** — `feat(python): zero-shot評価に参照特徴のfeedと来歴を追加`

### Task 10: 未対応runtimeでの拒否

**Files:**
- Modify: `src/python_run/piper_plus/voice.py:1076-1125`、`src/python_run/piper_plus/api/engine.py:168-196`
- Modify: `src/cpp/piper.cpp:512-562`
- Test: `src/python_run/tests/test_reference_schema_rejection.py` (新規)、`src/cpp/tests/` の入力検出テスト

**Interfaces:**
- Produces: ONNX入力に`reference_features`があるとき、Python・C++とも読み込み時に「このモデルは参照特徴入力が必要で、このruntimeは未対応」と明示エラー。旧モデルは不変。

- [ ] **Step 1〜4:** `test_python_runtime_rejects_reference_features_model`、`test_python_runtime_legacy_model_loads`、C++の同等テストをFAIL→実装→PASS (`uv run --no-sync pytest src/python_run/tests/test_reference_schema_rejection.py --no-cov`、`ctest --test-dir build`)
- [ ] **Step 5: Commit** — `fix: 参照特徴入力付きONNXを未対応runtimeで明示拒否`

### S1の完了確認

- [ ] `uv run --no-sync pytest src/python/tests src/python_run/tests --no-cov` 全件PASS、`.github/workflows/python-tests.yml`へ新テストを追加
- [ ] tiny fixtureでCPU計測: 融合ありのTTS FP16容量差と生成p50差を記録 (40MB / +10%の範囲内)

## 6. 停止・分岐

| 状態 | 対応 |
|---|---|
| G0でCAM++統計の話者分離度が192次元を上回らない | F-statsを主候補から外し、F-mel (小型mel encoderを`spk_proj`出力へ加算) の設計に戻る。GPUは借りない (2026-10-18 発生 → §8) |
| G0でtrimがCAM++/ECAPAのどちらかを退行させる | trimを採らず、frontendは現状維持で固定 |
| smokeで融合MLPの重みが変化しない・非有限値・再開失敗 | runを止めて実装へ戻る |
| pilotでF-statsがCcapを上回らない | 参照統計の利得は未確認として報告。容量増の効果と区別する |
| F-statsが類似度を上げるがCERが悪化 | 参照からの内容漏れを疑い、参照ペア・統計の時間平均・注入量を診断。長期学習で自動解決とみなさない |
| 費用上限 | 定期保存から回収し、起動したinstanceだけを終了。対照未完了なら比較未完了と報告 |

## 7. 採用後に別計画で行うこと

- runtime (Python・C++、続いてRust/Go/C#/WASM) の参照WAV → CAM++ 192+統計1024の抽出。現状のRust/Go/C#/WASMは学習とは別のfbank・resample実装で、frontend差が既にある。
- CAM++ ONNXの統計出力追加とgolden比較。
- F-mel、参照token (R2)、長文chunk文脈。
- devへの統合範囲の決定。

## 8. 改訂1 (2026-10-18): F-melへの再設計

### 8.1 判断の根拠

- G0 (c): CAM++のpooling前統計1024次元を192次元に足しても、未知話者の分離は良くならなかった (LDAプローブ平均 −0.0083、3/10 split勝ち)。CAM++の192次元は同じ統計のaffine射影なので、CAM++内部の情報を増やしても上積みが少ない。
- F-melは**CAM++を通らない別の情報源**として、参照音声の線形スペクトログラムを学習可能なencoderで読む。上流GPT-SoVITSのSoVITSでも、参照条件の本体は線形スペクトログラムから作る`ref_enc` (MelStyleEncoder) の時間平均`ge`である (v2Proの話者照合特徴はその上への加算)。
- CPUではF-melの利得を測れない (encoderの学習が要る)。そのため、S1の実装とテストまでをCPUで行い、利得の判定はS4 pilotのCcap対照で行う。GPUの使用は従来どおりユーザーの明示許可後。

### 8.2 設計

| 項目 | 内容 |
|---|---|
| 入力 | 参照発話の線形振幅スペクトログラム `[B, 513, T_ref]` (`filter_length // 2 + 1`)。学習cacheの`.spec.pt`と同じ`spectrogram_torch(n_fft=1024, hop=256, win=1024, center=False)`。長さ`[B]` int64 |
| encoder | `ReferenceSpecEncoder`: log圧縮 (`log(clamp(x, 1e-5))`) → spectral Linear×2 (Mish) → Conv1dGLU×2 (k=5、mask付き) → multi-head self-attention (2 head、key padding mask) → **fp32のmasked時間平均** (Task 3の`masked_time_mean_fp32`を再利用) → Linear(hidden→gin、**重み・bias zero-init**) |
| 合流 | `g_spk = spk_proj(e_ref) + reference_encoder(spec_ref)`。lang成分には足さない。初期状態では旧モデルと出力が同じ |
| 192次元の参照 | 学習時のGへのCAM++ 192次元も参照発話のもの (Task 7R)。SCL・swap・Latent Fillingは従来どおり生成対象の埋め込み |
| 対照Ccap | 192次元を入力とするMLP (Linear→PReLU→Linear、最後をzero-init) を`spk_proj`出力へ加算。追加パラメータ数をF-melの±5%に合わせる |
| 学習時の切り出し | 参照specをランダムに最大`--reference-max-frames` (既定512 frame ≈ 5.9秒) へ切り出す。検証時は先頭から固定長 |
| 推論frontend | 学習cacheを作ったbuilderと同じ手順。名前の閉じた集合 (`reference_spec_contract.py`) から選ぶ: `energy-vad@16k;soxr-hq` (`cache_norm_audio_fast`: 16kHzでenergy VAD → 元srで切り出し → soxr HQでモデルsrへ → `spectrogram_torch`)、`no-vad;soxr-mq` / `no-vad;soxr-hq` (`cache_norm_audio_no_vad`: soxrでモデルsrへ → `spectrogram_torch`)。既定値はなく、学習の`--reference-spec-frontend`でcheckpointに残し、export・評価がそれに合わせる (Ruling R14)。評価・推論は参照specを先頭から`reference_max_frames`に切ってから渡す (Ruling R15)。CAM++ 192次元はG0どおりtrimなし |
| 損失 | 追加しない。再構成・adversarial等の既存損失のみで学習する (CAM++/ECAPA由来の損失は足さない) |

### 8.3 比較群の置き換え

§3のF-statsをF-melに置き換える。Ccapの`target_params`はF-melのencoderのパラメータ数にする。他の群 (E0・C0-self・C0) と予算 (§4) は変えない。S2ではCAM++統計の再抽出をやめ、参照ペアを作る → 参照専用spec cacheを名前付きfrontendで作る (`build_reference_spec_cache`、Ruling R17)。学習音声のspec cacheは参照specには使わない。

S2ではあわせて次を行う (Ruling R14・R17、final review I1)。

- 手順: ① `build_reference_pairs`で参照ペアを作る。datasetの行に`audio_path`があれば、参照の元音声を`reference_audio_path`として書き足す。② `build_reference_spec_cache`で、参照に使う発話の元音声から参照specをCPUで作り直す。frontendは閉じた集合の名前を1つ指定し、sample rateはdatasetの`config.json`、STFT設定はconfigか明示したflagから取る (既定値では作らない)。`reference_audio_spec_path`だけをcacheへ向け直した新しいjsonlと、cache dirの来歴sidecar (`reference_spec_cache.json`) ができる。③ 学習の`--reference-spec-frontend`に②と同じ名前を渡す。学習は起動時にsidecarを照合し、frontendやSTFT設定の食い違い、sidecarに載っていない参照specを`SystemExit`で拒否する。
- 言語ごとに、学習音声のspec cacheをどのbuilderで作ったかを記録する。`prepare_multilingual_dataset`はJA+ENの発話をbilingual datasetのjsonlから取り込み、その`audio_norm_path`・`audio_spec_path`をそのまま使う。JA+ENのcacheは`prepare_bilingual_dataset`が`cache_norm_audio` (Silero VAD、閉じた集合の外) か`cache_norm_audio_fast` (`energy-vad@16k;soxr-hq`) で作ったもの。zh/es/fr/ptはVADなしで作られ、記録された手順では`--gpu-spec-device cuda:0` (閉じた集合の外) を使っている。参照specは参照専用cacheから読むので、この結果でfrontend名を決める必要はない。
- dataset dirに`test_utterances.jsonl`があると、ref_specの学習は各行に`reference_audio_spec_path`を要求し、起動時に`ValueError`で止まる。この列も起動時の照合の対象になる。各行に`reference_audio_path`を書けば`build_reference_spec_cache`で向け直せるが、そのための手順はまだない。S2で書くか、ファイルを外すかを決める。同じ行の`speaker_embedding`と参照specが同じ発話のものかどうかは検査していない。
- S3の注意: 自己参照で記録したnoneのcheckpoint (`generator_reference="self"`) からref_specへwarm startすると、`generator_reference`のWARNINGが1回出る。R16aどおりの想定した警告で、止める必要はない。

### 8.4 テストの方針 (2026-10-18 ユーザー指示)

全タスクをTDDで実装する。各タスクで次を守る。

- 実装前にテストを書き、**失敗を実行して確認**してから実装する。失敗の確認結果 (失敗したテスト名と理由) を報告に残す。
- 正常系だけでなく、境界値 (長さ0・1、最大長、batch 1と複数、padding有無)、異常系 (欠落・形状違い・dtype違い・NaN/Inf入力で明示エラー)、後方互換 (既定値で旧checkpoint・旧ONNX・旧CLIの出力がbit一致) を必ず含める。
- 数値の一致は、意味のある許容誤差を根拠付きで決める。実測に合わせて緩めない。
- 1つの性質を1つのテストで確かめる。モックで実装の中身を置き換えて「呼ばれたこと」だけを見るテストにしない。tiny modelを実際に動かす。
- 回帰の確認として、触ったモジュールの既存テストも全件実行する。
- 新しいテストファイルは`.github/workflows/python-tests.yml`の実行対象に入っていることを確認する。

### 8.5 実装タスク (S1、Task 5R〜10R)

Ruling R3を置き換える: module属性名は`reference_encoder`と`capacity_control`。

#### Task 5R: 参照spec encoderと容量対照

**Files:**
- Create: `src/python/piper_train/vits/reference_encoder.py`
- Modify: `src/python/piper_train/vits/models.py` (`SynthesizerTrn.__init__`に`reference_conditioning: str = "none"` (`none` / `ref_spec` / `capacity`)、`reference_spec_channels: int = 513`。`_get_speaker_condition(speaker_embeddings=None, reference_spec=None, reference_spec_lengths=None)`、`_get_global_conditioning`、`forward`、`infer`へ通す)
- Modify: `src/python/piper_train/__main__.py` (`--reference-conditioning {none,ref_spec,capacity}`、既定`none`)
- Test: `src/python/tests/test_reference_encoder.py` (新規)

**Interfaces:**
- Produces: `ReferenceSpecEncoder(spec_channels: int, gin_channels: int, hidden_channels: int = 128, kernel_size: int = 5, n_heads: int = 2)`、`forward(spec: Tensor[B,F,T], spec_lengths: LongTensor[B]) -> Tensor[B,gin,1]`。長さ0の行は`ValueError`。
- Produces: `CapacityControl(in_dim: int, gin_channels: int, target_params: int)`、`forward(e: Tensor[B,in_dim]) -> Tensor[B,gin,1]`。
- Produces: `reference_conditioning="ref_spec"`で`reference_spec`か長さがNoneなら`ValueError`。`none`のとき参照specが渡されたら`ValueError` (黙って落とさない)。

- [ ] **Step 1: テストを書く** — 少なくとも: `test_none_matches_legacy_output` (同じ重みで旧モデルと出力一致)、`test_zero_init_ref_spec_matches_legacy_output` (初期状態は`spk_proj`のみと一致)、`test_padding_does_not_change_output` (末尾padの長さを変えても出力不変)、`test_batch_rows_independent` (batch内の他行の参照が出力に影響しない)、`test_long_fp16_reference_is_finite` (8000 frame、fp16入力で有限)、`test_length_one_reference`、`test_zero_length_reference_raises`、`test_shape_and_dtype_errors`、`test_encoder_receives_gradient_after_steps`、`test_spk_proj_gradient_unchanged_at_init`、`test_capacity_control_param_count_within_5pct`、`test_missing_reference_spec_raises`、`test_reference_spec_on_legacy_model_raises`
- [ ] **Step 2: 失敗を確認** — `uv run --no-sync pytest src/python/tests/test_reference_encoder.py --no-cov` → FAIL
- [ ] **Step 3: 実装** — `spk_proj`を直接呼ぶ箇所 (`vits/lightning.py`のDINO、`models.py`内の直接呼び出し、`vits/telemetry.py`) を`_get_speaker_condition`経由に揃える。**実装での変更:** DINOは意図して`spk_proj`を直接呼んだままにした。DINOは`spk_proj`本体とEMA teacher (`spk_proj`の複製) を比べる損失で、`_get_speaker_condition`を通すと参照項 (`reference_encoder` / `capacity_control`) がstudent側だけに入り、新経路へteacher由来の追加損失を掛けることになるため (§8.2「損失は追加しない」)。`models.py`内の呼び出しとtelemetryは`_get_speaker_condition`経由にし、telemetryには参照specを渡す
- [ ] **Step 4: 成功を確認** — 新テストと`test_speaker_embedding.py`、`test_adaln_encp.py`、`test_snac_stats_flag.py`がPASS
- [ ] **Step 5: Commit** — `feat(python): 参照スペクトログラムを話者条件へ加算するencoderと容量対照を追加`

#### Task 6R: EMA・LR慣らし・重み移行

§5 Task 6と同じ。置き換え: EMAの両scopeと許可prefixは`reference_encoder.` / `capacity_control.`、CLIは`--reference-lr-scale` (既定1.0) と`--reference-warmup-steps` (既定0)。`load_state_with_allowed_missing`のinterfaceは同じ。

- [ ] テスト: `test_ema_tracks_reference_encoder_in_legacy_and_extended`、`test_reference_param_group_lr_scale`、`test_reference_warmup_ramps_lr`、`test_default_optimizer_groups_unchanged`、`test_allowed_missing_accepts_only_reference_keys`、`test_allowed_missing_rejects_shape_mismatch`、`test_reference_checkpoint_into_legacy_model_raises`
- [ ] Commit — `feat(python): 参照encoderのEMA登録・LR慣らし・許可key付き移行`

#### Task 7R: 学習時の参照ペア (SCLとの分離)

**Files:**
- Modify: `src/python/piper_train/vits/dataset.py` (jsonlの`reference_utterance_id`・`reference_audio_spec_path`・`reference_speaker_embedding_path`を読む。Batchに`reference_embeddings: Tensor[B,192] | None`、`reference_specs: Tensor[B,513,T_ref] | None`、`reference_spec_lengths: LongTensor[B] | None`、`reference_utterance_ids: list[str] | None`を追加。学習時はランダム切り出し、検証時は先頭固定)
- Modify: `src/python/piper_train/vits/lightning.py` (`--generator-reference {self,cross_utt}` 既定`self`。`cross_utt`ではGへ`reference_embeddings` (と`ref_spec`時は`reference_specs`) を渡す。SCL・swap・Latent Fillingは`speaker_embeddings`のまま。validation・audio loggingのforwardにも同じ参照を渡す)
- Modify: `src/python/piper_train/zero_shot_requirements.py`
- Create: `src/python/piper_train/tools/build_reference_pairs.py`
- Test: `src/python/tests/test_reference_pairs.py` (新規)

**Interfaces:**
- Produces: `validate_reference_pairs(utterance_ids, reference_utterance_ids, speaker_ids, splits, audio_sha256) -> None` (参照=target、別話者、別split、同一音声hashのどれかで`ValueError`)。`--strict-zero-shot`はbatchごとに呼ぶ。
- Produces: `build_reference_pairs(entries: list[dict], seed: int) -> tuple[list[dict], dict]` (各targetに同話者・同split・別hashの参照を1つ割り当て、上の3フィールドを書く。候補がないtargetは除外し、除外数と理由を返す)。
- Produces: `--generator-reference cross_utt`で参照フィールドが欠ける発話は読み込み時に`ValueError` (自己参照へ黙って戻さない)。`--reference-conditioning`が`none`以外なら`cross_utt`必須 (違えば`SystemExit`)。`--latent-filling-tau`または`--c-swap-spk`との同時指定も`SystemExit`。

- [ ] テスト: `test_pairs_never_self_reference`、`test_pairs_reject_same_hash_different_path`、`test_pairs_keep_split`、`test_pairs_same_speaker`、`test_pairs_deterministic_by_seed`、`test_single_utterance_speaker_excluded_with_reason`、`test_generator_uses_reference_while_scl_uses_target`、`test_self_mode_batch_unchanged`、`test_missing_reference_fields_raise`、`test_reference_crop_bounds`、`test_validation_crop_deterministic`、`test_reference_conditioning_requires_cross_utt`、`test_reference_conditioning_with_latent_filling_is_rejected`
- [ ] PASS: `uv run --no-sync pytest src/python/tests/test_reference_pairs.py src/python/tests/test_strict_zero_shot.py --no-cov`
- [ ] Commit — `feat(python): 学習時のG参照を別発話にしSCL入力と分離`

#### Task 8R: ONNX export

**Files:**
- Modify: `src/python/piper_train/export_onnx.py` (`ref_spec`時に入力`reference_spec` `[B,513,T_ref]` float32と`reference_spec_lengths` `[B]` int64を追加。configへ`"reference_conditioning": {"schema": "ref_spec_v1", "spec_channels": 513, "filter_length", "hop_length", "win_length", "sample_rate", "center": false, "frontend", "max_frames"}`を記録。`frontend`は学習hparam `reference_spec_frontend`の値、`max_frames`は`reference_max_frames`の値をcheckpointから写す (Task 11RでR14・R15に合わせて修正。当初は`"energy-vad@16k;soxr-hq"`の固定値で`max_frames`がなかった)。`capacity`は入力を増やさない)
- Modify: `src/python/piper_train/export_onnx_streaming.py` (`check_streaming_export_supported`で`reference_conditioning != "none"`を`NotImplementedError`)
- Test: `src/python/tests/test_export_reference_encoder.py` (新規)

- [ ] テスト: `test_legacy_export_input_names_unchanged`、`test_ref_spec_export_has_reference_inputs`、`test_torch_ort_parity_with_reference_spec` (`--no-stochastic`、FP32、atol 1e-4、参照長2種)、`test_fp16_export_long_reference_finite`、`test_capacity_export_input_names_unchanged`、`test_config_records_reference_conditioning`、`test_streaming_export_rejects_reference_conditioning`
- [ ] PASS: `CUDA_VISIBLE_DEVICES="" uv run --no-sync pytest src/python/tests/test_export_reference_encoder.py src/python/tests/test_export_onnx.py --no-cov`
- [ ] Commit — `feat(python): 参照spec入力付きONNX exportとstreaming拒否`

#### Task 9R: 評価経路の接続

**Files:**
- Modify: `src/python/piper_train/reference_frontend.py` (`reference_spec_from_audio(audio, sample_rate, *, target_sample_rate, filter_length, hop_length, win_length, frontend) -> (Tensor[513,T], dict)`。`frontend`は既定値なしの必須引数で、名前の閉じた集合 (`reference_spec_contract.py`) から選んだ学習cache builderと同じ手順で作る。当初案の`trim=True`と「`cache_norm_audio_fast`と同じ手順」はR14で置き換えた)
- Modify: `src/python/piper_train/tools/generate_eval_audio.py`、`src/python/piper_train/evaluation_manifest.py`
- Test: `src/python/tests/test_reference_frontend.py`、`src/python/tests/test_zs_eval_integration.py`

- [ ] テスト: `test_reference_spec_matches_training_cache_builder` (同じWAVで、frontend名ごとに写したbuilderの学習cacheのspecと一致。3つのfrontendでparametrize。Task 2の残課題も兼ねる。当初名は`test_reference_spec_matches_cache_norm_audio_fast`)、`test_reference_spec_resamples_16k_and_44k`、`test_reference_spec_silent_audio_raises`、`test_eval_feeds_reference_spec_for_ref_spec_model`、`test_eval_legacy_model_unchanged`、`test_eval_manifest_records_frontend_and_spec_hash`
- [ ] Commit — `feat(python): zero-shot評価に参照specのfeedと来歴を追加`

#### Task 10R: 未対応runtimeでの拒否

§5 Task 10と同じ。検出する入力名を`reference_spec`に置き換える。

- [ ] テスト: `test_python_runtime_rejects_reference_spec_model`、`test_python_runtime_legacy_model_loads`、`test_http_engine_rejects_reference_spec_model`、C++の同等テスト
- [ ] Commit — `fix: 参照spec入力付きONNXを未対応runtimeで明示拒否`

### 8.6 判断の記録

- **Ruling R7 (frontend):** ~~CAM++ 192次元はG0どおりtrimなし。F-melのspecは学習cache (VAD trim済み`audio_norm`由来) と同じ手順でtrimする。G0 (a) は既存モデルのCAM++経路での測定で、未学習のencoderには当てはまらないため。外れた場合の費用: S6でtrim有無をCPUで比べ直す。~~ **specの部分はRuling R14で置き換え** (学習cacheはVAD trim済みとは限らなかった)。CAM++ 192次元をtrimしない部分はそのまま。
- **Ruling R8 (入力形式):** encoderの入力はmelではなく線形スペクトログラム。学習cacheをそのまま使え、runtimeはenc_qと同じSTFT 1回で作れるため。log圧縮はencoder内で行う。
- **Ruling R14 (frontend、R7のspec部分を置き換え):** 参照specのfrontendは、実在するcache builderを写した名前の閉じた集合 (`energy-vad@16k;soxr-hq` / `no-vad;soxr-mq` / `no-vad;soxr-hq`) から明示的に選ぶ。学習は`--reference-spec-frontend`でcheckpointに残し、export・評価はそれとmanifestを照合する。v10bの実データのbuilderはS2のdata auditで確定する。理由: §1.2の前提 (学習cacheはVAD trim済み) がmultilingual cacheでは誤りだった。費用: hparam 1つと受け渡し。
- **Ruling R15 (評価時の参照長):** 評価は参照specを、モデルの`reference_max_frames`まで先頭から切ってから渡す (学習の検証時と同じ切り方)。ONNXのconfigには`max_frames`を追加する。理由: 学習は512 frameより長い参照を見ないので、評価も学習と同じ分布の参照を渡す。費用: config 1項目。
- **Ruling R16 (再開時の参照hparam照合):** 再開時に参照関連のhparam (`reference_spec_frontend` / `generator_reference` / `reference_max_frames`) をcheckpointと照合する。strict resumeは不一致で停止、weights-onlyとFTはfrontendの不一致のみ停止し他は警告、keyの無い旧checkpointは受け入れる。理由: CLIの値だけを見ると、続きの学習で宣言を変えても何も出ず、epochごとに宣言の違うcheckpointができて評価の比較が成り立たなくなる (final review I3)。
- **Ruling R17 (参照専用spec cache):** Gの参照specは、学習音声のspec cacheではなく、参照に使う発話の元音声から名前付きfrontendでCPUで作り直した参照専用cache (`tools/build_reference_spec_cache.py`) から読む。学習は起動時にcacheのsidecarのfrontend・STFT設定をモデルと照合し、sidecarに載っていない参照specを拒否する。学習音声のcacheは変えない。理由: 学習音声のcacheは言語ごとに別のbuilder (閉じた集合の外を含む) で作られ、checkpointが宣言できるfrontend名は1つなので、そのままでは学習と評価のspecの作り方が食い違っても検出できない (final review I1)。費用: 参照される発話の数だけCPUでspecを作る。
- **未解決 (S4で確認):** 参照encoderが話者以外 (録音条件・内容) を拾い、CERが悪化する可能性。§6の「類似度は上がるがCERが悪化」の行で扱う。

### 8.7 実装結果 (S1)

S1 (Task 5R〜11R) の実装とCPUテストは`feat/zero-shot-v8-dataset-scaling`で完了した。GPUでの学習・評価はまだ行っていない。

| Task | 内容 | commit |
|---|---|---|
| 5R | 参照spec encoderと容量対照 | `4d46cb99`、`b7b1aed4` |
| 6R | EMA・LR慣らし・重み移行 | `8e7edfe9`、`8b8b9678`、`6904ef0e` |
| 7R | 学習時の参照ペア (SCLとの分離) | `81f579bf`、`65af279e` |
| 8R | ONNX export | `2c14802d`、`d8a7b866` |
| 9R | 評価経路の接続 | `bc0ca41e`、`b84bd92d` |
| 10R | 未対応runtimeでの拒否 | `65c0faec`、`a68f9088` |
| 11R | 7R・8R・9Rの契約の突き合わせ (学習hparam `reference_spec_frontend`、exportのfrontend・`max_frames`、評価の先頭切り出し、通し試験) | `ed94919c` と、この節を含むdocsのcommit |

実装中の判断 (1行ずつ):

- **R9:** 参照付きbaseから参照moduleの無いモデルへFTするときは、参照の重みを警告付きで捨てる (`spk_proj`と同じ扱い)。
- **R10:** weights-onlyの読込では、学習専用の補助module (WavLM判別器など) の有無の差を警告付きで許す。生成器と主判別器は厳密に照合する。
- **R11:** 並列worktreeのテストは、mainの`.venv`のpythonに`PYTHONPATH`でworktreeの`src`を先に入れて実行する。
- **R12:** ONNX graphの中では参照spec長をclampしない。入力の検査はruntimeと評価が行い、ONNX export契約に記録する。
- **R13:** jsonlのsplitと学習時のランダムなtrain/val分割は一致しない。跨いだ参照は止めずに数えて警告する。
- **R14:** 参照specのfrontendは名前の閉じた集合から明示的に選び、モデルの宣言とmanifestを照合する (§8.6)。
- **R15:** 評価は参照specをモデルの`reference_max_frames`まで先頭から切って渡す (§8.6)。
- **R16:** 再開時に参照関連のhparam (frontend / generator_reference / reference_max_frames) をcheckpointと照合する。strict resumeは不一致で停止、weights-onlyとFTはfrontendの不一致のみ停止し他は警告、keyの無い旧checkpointは受け入れる (§8.6)。
- **R17:** Gの参照specは、元音声から名前付きfrontendで作り直した参照専用cacheから読み、学習は起動時にそのsidecarをモデルと照合する (§8.6)。

残っていること:

- 既存の失敗テスト (今回の変更より前から失敗している):
  - `test_speaker_encoder_golden` の8件 (n_fft 400と512の食い違い)
  - `test_decoder_upsample_mode` のresize modeのexport
  - `test_carrier_head` (実行するdirectoryによって結果が変わる)
  - `test_piper_proc_exec` (ctestの下で実行したとき)
- 範囲外のbug: `piper_plus/api/engine.py`の`_fill_speaker_embedding_inputs`が`speaker_embedding_mask`を常に渡す。
- Rust・Go・C#・WASMのruntimeは、参照spec入力付きのモデルをまだ拒否しない (拒否はPython runtimeとC++のみ)。
- 学習側の`piper_train.infer_onnx`も、参照spec入力付きのモデルを明示的に拒否せず、対応もしていない (ORTの入力欠落エラーで止まる)。
- v10bの実データの学習cacheがどのbuilderで作られたか (frontend名) はS2のdata auditで確定する。
- **決定 (Ruling R17):** 参照specのfrontendが言語ごとに異なる、または閉じた集合の外になる問題 (final review I1) は、参照に使う発話だけを名前付きのfrontendで作り直した参照専用のspec cacheに切り出し、`reference_audio_spec_path`をそこへ向けて解決する (`build_reference_spec_cache`、CPUのみ、参照される発話の数だけ)。学習は起動時にcacheのsidecarを照合する。別案の「GPU batch経路を許容誤差つきで閉じた集合に加える」は、言語ごとの混在を表せないので採らなかった。
- dataset dirに`test_utterances.jsonl`があると、ref_specの学習は起動時に止まる。各行に`reference_audio_spec_path`が要るが、この列を書くtoolがない (§8.3)。
- 学習は参照specをfp16で保存した`.spec.pt`からfloatに戻して使い、評価はfloat32のまま渡す。相対差は2^-11以下で、9Rの報告に記録した。揃える場合は評価で`.half().float()`してから渡す。
