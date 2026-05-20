# T-012: `python-inference` distroless 化

**チケット ID**: `T-012`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#1-1` (Distroless / Chainguard 移行 — `python-inference` image)
**Tier**: Tier 3 (HF Space deploy 対象、 **影響最大**)
**Status**: 着手中 (trial PR scope: 並行 Dockerfile.cpu.distroless 新設、 既存 Dockerfile.cpu と docker-compose / HF Space deploy path は不変更)
**PR**: feat/python-inference-distroless-trial (/create-pr skill で起票予定)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: T-013 完了必須 (Gradio + pyopenjtalk distroless multi-stage 知見を確立してから着手)

> **Trial PR scope note (PR #TBD)**
>
> M3 distroless 化を順序を変更して **T-012 自体を trial PR として derisk** する方針に変更。 ticket original の「T-016 → T-015 → T-013 → T-012 → T-014」 順序より先に T-012 着手する理由:
>
> - 既存 `Dockerfile.cpu` を **不変更で残し** 並行 `Dockerfile.cpu.distroless` を新設、 既存 deployment path への影響ゼロ
> - HF Space deploy 検証は user 手動 step (AC-1.2)、 trial 期間中は staging slot のみ使用、 promotion (canonical 置換) は別 PR
> - linux/amd64 single-arch build のみ CI で実行、 multi-arch (arm64) build は次 PR
>
> trial PR で「distroless build が成立し size 削減効果がある」 ことを実証してから T-013/T-014/T-015/T-016 + canonical 置換 PR に進む 5+ PR cadence。

> **M3 内推奨実装順**: T-016 → T-015 → T-013 → **T-012 (本チケット)** → T-014。
> 本 image は HuggingFace Space (`ayousanz/piper-plus`) の deploy 対象であり、 cold start 失敗が user-facing 影響を直接発生させる (R-4)。 T-013 (webui) 完了で Python distroless multi-stage を spike 済みの状態で着手する。
>
> ただし現行 Dockerfile は **GPU 対応** で `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` がベース。 distroless で GPU stack を扱う事例は希少で risk 高。 **CPU 経路 (`Dockerfile.cpu`) を先に distroless 化** し、 GPU 経路は別 PR or scope 外として判断する。

---

## 1. タスク目的とゴール

### 目的

`docker/python-inference/Dockerfile` は GPU/CPU 両対応の Python 推論 image (FastAPI ベース、 `/v1/audio/speech` OpenAI 互換 API + Gradio WebUI 兼用)。 現状 `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` ベース、 image size ~6 GB、 CVE 表面積 巨大。

HuggingFace Space の deploy 対象であり、 image size 削減は **HF Space cold start latency 改善** に直結する。 ただし GPU 経路の distroless 化は技術的に困難 (NVIDIA container runtime + cuDNN shared lib + CUDA toolkit version pin) のため、 **本チケットは CPU 経路 (`Dockerfile.cpu`) の distroless 化に scope を限定** する。

GPU 経路の distroless 化は本チケット完了後に user 判断で別チケット切り出し。

### ゴール (Done definition)

- [ ] `Dockerfile.cpu` の base image を `cgr.dev/chainguard/python:3.13` または `gcr.io/distroless/python3-debian12` に置換 (FR-1.2)
- [ ] multi-stage 化 (builder stage で pyopenjtalk C 拡張 + onnxruntime-cpu wheel build、 final stage で distroless)
- [ ] `docker compose up python-inference-cpu` で起動成功 (AC-1.1a)
- [ ] FastAPI `/health` が HTTP 200、 `/v1/audio/speech` が wav stream 出力
- [ ] image size 50%+ 削減 (AC-1.1b、 現状 CPU image 推定 ~2 GB → 1 GB 以下)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] HF Space deploy 後の動作確認手順を Test Plan に user 手動 step として記載 (AC-1.2)
- [ ] image tag 戦略を user が決定し PR 本文に明記 (FR-1.5)
- [ ] PR コメントに `docker/python-inference/distroless-report.md` 自動投稿 (FR-1.4)

### user 判断待ち項目 (着手前確認)

1. **image tag 戦略 (FR-1.5)**:
   - (a) 既存 tag (`piper-plus-inference:latest`, `piper-plus-inference:cpu`) を置換
   - (b) `piper-plus-inference:<ver>-cpu-distroless` を別 tag で並行配信
   - 推奨は (b)。 HF Space deploy 対象のため、 1-2 週間並行配信で cold start 互換性確認後に置換。
2. **GPU 経路の扱い**:
   - (a) 本チケットは CPU のみ、 GPU は別チケット切り出し (推奨)
   - (b) 本チケットで GPU も同時に distroless 化
   - 推奨は (a)。 GPU distroless 化は CUDA toolkit 制約により blast radius 大。
3. **HF Space deploy 検証 (AC-1.2)**:
   - HF Space staging slot で 1-2 日動作確認後に prod slot に切替
   - user 自身で HF token + space repository を扱う必要あり (Claude Code は実行不可)
   - 検証手順を Test Plan に明記し、 user が手動 step として実行する
4. **`Dockerfile` (GPU) と `Dockerfile.cpu` の関係整理**:
   - `docker-compose.yml` で service 分離されているか
   - HF Space は CPU / GPU どちらの image を pull しているか確認

---

## 2. 実装内容の詳細

### 2.1 既存 Dockerfile の base image

| ファイル | base | 主要 install | 用途 |
|---------|------|--------------|------|
| `Dockerfile` (GPU) | `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` | python3.11 + onnxruntime-gpu + Gradio | GPU 推論 |
| `Dockerfile.cpu` | (未確認、 推定 `python:3.13-slim`) | python + onnxruntime + Gradio | CPU 推論、 HF Space |

**着手前 task**: `Dockerfile.cpu` の実 base image / install 内容を確認、 本 ticket の §2.1 を埋める。

### 2.2 移行後 base image 候補比較 (CPU 経路)

| 候補 | 長所 | 短所 |
|------|------|------|
| `cgr.dev/chainguard/python:3.13` | Python 3.13 同梱、 minimal、 T-013 で実績 | pip 同梱なしで builder 必須、 site-packages COPY 必須 |
| `gcr.io/distroless/python3-debian12` | Google maintained、 Debian 12 baseline | Python 3.11 固定で version 後退 |
| `cgr.dev/chainguard/wolfi-base` + `apk add python-3.13` | shell + apk で柔軟、 T-016 で実績 | size 大 |

**推奨**: `cgr.dev/chainguard/python:3.13` (T-013 と統一)。

### 2.3 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docker/python-inference/Dockerfile.cpu` | 変更 | multi-stage 化 + distroless 化 |
| `docker/python-inference/Dockerfile` (GPU) | 不変更 | scope 外 (別チケット) |
| `docker/python-inference/distroless-report.md` | 新規 | size + CVE diff の auto-generate 出力 |
| `docker/python-inference/docker-compose.yml` | 変更 | cpu service の image / user UID 調整 |
| `.github/workflows/docker-build.yml` | 変更 | python-inference matrix に CPU distroless variant 追加 |
| `.github/workflows/deploy-huggingface.yml` | 確認 | HF Space deploy が CPU image を pull する場合の動作確認 |
| `docs/reference/distroless-migration.md` | 追記 | python-inference 移行の知見追記 |

### 2.4 multi-stage build 構成 (CPU 経路)

```dockerfile
# Stage 1: Builder
FROM python:3.13.13-slim-trixie AS builder

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake g++ libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "uv>=0.9,<1"

WORKDIR /build

COPY VERSION /build/VERSION
COPY pyproject.toml /build/pyproject.toml
COPY src/python /build/src/python/
COPY src/python_run/requirements_webui.txt /build/requirements_webui.txt

# wheel build (workspace editable 回避、 wyoming Dockerfile pattern)
RUN uv build /build/src/python/g2p --wheel --out-dir /tmp/wheels/ \
    && uv build /build/src/python      --wheel --out-dir /tmp/wheels/

# CPU-only inference (onnxruntime not onnxruntime-gpu)
RUN uv pip install --system "$(ls /tmp/wheels/piper_plus_g2p-*.whl)[all]" \
    && uv pip install --system "$(ls /tmp/wheels/piper_train-*.whl)[inference]" \
    && uv pip install --system -r /build/requirements_webui.txt \
    && uv pip install --system "fastapi[standard]" uvicorn

# NLTK data
ENV NLTK_DATA=/usr/share/nltk_data
RUN python -c "\
import nltk; \
nltk.download('averaged_perceptron_tagger', download_dir='/usr/share/nltk_data'); \
nltk.download('averaged_perceptron_tagger_eng', download_dir='/usr/share/nltk_data'); \
nltk.download('cmudict', download_dir='/usr/share/nltk_data')"

# Stage 2: Distroless final
FROM cgr.dev/chainguard/python:3.13

USER root

COPY --from=builder /usr/local/lib/python3.13 /usr/local/lib/python3.13
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/
COPY --from=builder /usr/share/nltk_data /usr/share/nltk_data
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsndfile.so* /usr/lib/x86_64-linux-gnu/
COPY --from=builder /usr/lib/x86_64-linux-gnu/libgomp.so* /usr/lib/x86_64-linux-gnu/

ENV NLTK_DATA=/usr/share/nltk_data
ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

COPY docker/python-inference/inference.py /app/
COPY docker/python-inference/test.py /app/
COPY docker/webui/app.py /app/webui.py

WORKDIR /app

RUN mkdir -p /app/models /app/output \
    && chown -R 65532:65532 /app

USER 65532

EXPOSE 8000 7860

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]

ENTRYPOINT ["python", "/app/inference.py"]
```

### 2.5 HF Space deploy 検証手順 (AC-1.2、 user 手動 step)

PR Test Plan に以下を必須記載 (Claude Code は実行不可、 user 手動 step):

```markdown
## Test Plan: HF Space deploy validation (manual)

1. Branch checkout: `git checkout <pr-branch>`
2. Build CPU distroless image locally: `docker build -f docker/python-inference/Dockerfile.cpu -t piper-plus-inference:cpu-distroless .`
3. Smoke test: `docker run -p 8000:8000 -v $(pwd)/test/models:/app/models piper-plus-inference:cpu-distroless`
4. Health check: `curl http://localhost:8000/health` → expect HTTP 200
5. TTS API: `curl -X POST http://localhost:8000/v1/audio/speech -d '{"input": "test", "voice": "tsukuyomi"}' --output test.wav`
6. Push to HF Space staging: (user manual via HF UI or `huggingface-cli upload`)
7. Verify HF Space cold start latency: `curl https://huggingface.co/spaces/ayousanz/piper-plus-staging/api/predict ...` (cold start < 60s)
8. If staging OK, promote to prod via HF Space UI
```

### 2.6 PR コメント自動投稿 (`docker/python-inference/distroless-report.md`)

format (FR-1.4): T-013 と同 format に HF Space cold start latency 比較を追加 (任意、 user 手動測定後に追記):

```markdown
## Distroless migration report: `python-inference` (CPU)

| metric | before | after | delta |
|--------|--------|-------|-------|
| image size | 2.10 GB | 0.95 GB | -55% |
| CVE HIGH | 18 | 2 | -89% |
| CVE CRITICAL | 3 | 0 | -100% |
| HF Space cold start (manual) | 45s | 28s | -38% |
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | Dockerfile.cpu の multi-stage + distroless 化 | `docker/python-inference/Dockerfile.cpu` |
| **Test author** | 1 | FastAPI + Gradio smoke test、 docker-compose 修正 | `docker/python-inference/test.py`, `docker-compose.yml` |
| **Spec / Doc author** | 1 | distroless-migration.md 追記、 HF Space 検証手順 | doc + Test Plan |
| **Deploy verifier** | 1 (user 自身) | HF Space staging deploy + cold start 測定 | 手動検証 report |
| **Reviewer** | 1 | onnxruntime CPU / FastAPI 整合性 | review |

**並列度**: T-013 完了後に着手。 Implementer / Test author は並列、 Deploy verifier は user 手動 step。

**Agent prompt の与え方**: Explore subagent で `Dockerfile` (GPU) + `Dockerfile.cpu` (実体) + `inference.py` + `docker-compose.yml` + `deploy-huggingface.yml` を dump → general-purpose で T-013 の Dockerfile を参考に CPU distroless 化と FastAPI smoke test 並列、 最後に user に HF Space 手動検証を request。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `docker/python-inference/Dockerfile.cpu` の multi-stage 化 + distroless 化
- FastAPI `/v1/audio/speech` + `/health` + `/v1/models` の smoke test
- Gradio webui mode (`--webui`) の動作確認
- HF Space deploy 検証手順 (user 手動 step) の Test Plan 記載

**Out of scope**:

- `Dockerfile` (GPU 経路) の distroless 化 (別チケット、 CUDA toolkit 制約調査が前提)
- HF Space の自動 deploy (user 手動 step に限定)
- `deploy-huggingface.yml` の workflow 改変 (image build path だけが変わる場合は別 PR)
- 他の 4 image (別チケット)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | Dockerfile.cpu build | `docker build -f docker/python-inference/Dockerfile.cpu .` | exit 0 |
| UT-2 | image size | `docker images` | before の 50% 以下 |
| UT-3 | CVE scan | `trivy image --severity HIGH,CRITICAL` | before の 20% 以下 |
| UT-4 | Python import | `python -c "import piper_train; import fastapi; import onnxruntime"` | exit 0、 `onnxruntime` が CPU provider のみ |
| UT-5 | NLTK data | `python -c "import nltk; nltk.data.find('taggers/...')"` | exit 0 |
| UT-6 | libsndfile / libgomp | `python -c "import soundfile, onnxruntime"` | exit 0 |
| UT-7 | non-root user | `id` | UID 65532 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full build | `docker build -t python-inference:cpu-distroless .` |
| E2E-2 | FastAPI 起動 | `docker run -p 8000:8000 ...` → `curl http://localhost:8000/health` HTTP 200 |
| E2E-3 | TTS API | `curl -X POST /v1/audio/speech -d '{"input": "test"}' --output test.wav` |
| E2E-4 | Gradio webui mode | `docker run --entrypoint python ... /app/webui.py` で 7860 起動 |
| E2E-5 | PR コメント | distroless-report.md 自動投稿 |
| E2E-6 (manual) | HF Space staging | user 手動で push + cold start 測定 |

### 4.4 リグレッション確認

- [ ] 既存 `docker-compose.yml` の CPU service が継続動作
- [ ] `webui-test.yml` (CPU image を pull する場合) が継続 pass
- [ ] `deploy-huggingface.yml` (HF Space deploy workflow) が image 変更を反映
- [ ] `hadolint.yml` rule pass (DEP-1.1)
- [ ] silent-zero 防御: `trivy image` 出力件数 0 件で `::warning::`

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | HF Space cold start 失敗 (R-4) | user 手動 staging deploy + cold start 測定を Test Plan に必須化 (AC-1.2) | manual E2E-6 |
| C-2 | onnxruntime-cpu と onnxruntime-gpu の混在で provider 選択ミス | builder で `onnxruntime` (CPU only) のみ install、 `inference.py` で CPU provider 強制設定 | UT-4 |
| C-3 | FastAPI の uvicorn が distroless で起動しない | builder で uvicorn binary を COPY、 ENTRYPOINT `["python", "/app/inference.py"]` で内部 uvicorn 起動 | E2E-2 |
| C-4 | Gradio webui mode (`/app/webui.py`) と FastAPI mode (`/app/inference.py`) の切替 | docker-compose で 2 service 分離、 ENTRYPOINT を image 内で切替 | E2E-2 / E2E-4 |
| C-5 | HF Space token / repository への push 権限が CI 経由で取得困難 | user 手動 deploy で対応、 CI 自動化は別 milestone | manual E2E-6 |
| C-6 | `pyopenjtalk` C 拡張 + onnxruntime + libsndfile + libgomp の shared lib 整合性 | builder の `/usr/local/lib/python3.13` 全体 + `/usr/lib/x86_64-linux-gnu/lib*.so*` を COPY | UT-6 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] base image が `cgr.dev/chainguard/python:3.13` であること (FR-1.2)
- [ ] CPU 経路のみ scope であり GPU 経路は不変更であること (Test Plan で明示)
- [ ] HF Space deploy 検証手順が Test Plan に **user 手動 step** として記載されていること (AC-1.2 必須)
- [ ] image tag 戦略が PR 本文 §1 で明示されていること (FR-1.5、 user 判断)
- [ ] `docker/python-inference/distroless-report.md` が PR コメントに投稿されること (FR-1.4)
- [ ] image size 50%+ 削減 / CVE 80%+ 削減を満たすこと (AC-1.1)
- [ ] FastAPI `/health`, `/v1/audio/speech`, `/v1/models` が動作すること (E2E-2, E2E-3)
- [ ] Gradio webui mode (entrypoint 切替) が動作すること (E2E-4)
- [ ] HEALTHCHECK が exec form + python urllib であること
- [ ] non-root user (UID 65532) で起動すること
- [ ] silent-zero pattern を踏んでいないか
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] markdownlint / hadolint 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか
- [ ] **HF Space staging deploy で cold start 失敗が無いことを user が確認したか** (AC-1.2)

---

## 6. 一から作り直すとしたら

### 案 A: HF Space を独自 image に依存せず、 公式 `huggingface/transformers-pytorch-cpu` ベースに移行

- **概要**: 自前 Dockerfile を廃止し、 HF 公式の Python base + piper_train を `pip install` するだけの構成。 distroless 化は不要、 HF Space の上流 update に自動追従。
- **長所**: maintainer 負担削減、 HF Space との互換性自動保証、 image security は HF 側に委譲
- **短所**: HF 公式 image は size 大 (~3 GB) で distroless 目標 (50% 削減) と矛盾、 custom 設定 (NLTK data 同梱) 不可、 vendor lock-in
- **採否**: v1 では独自 Dockerfile + distroless 化を選択。 HF Space lock-in を回避するため。

### 案 B: 1 image で CPU/GPU 両対応せず、 2 image に完全分離

- **概要**: 現状 `Dockerfile` (GPU 兼 CPU fallback) + `Dockerfile.cpu` の 2 file 構成を見直し、 GPU と CPU を完全に別 image (`piper-plus-inference-gpu`, `piper-plus-inference-cpu`) に分離。 docker-compose は service 名で切替。
- **長所**: 各 image を最適化 (GPU は nvidia base 維持、 CPU は distroless)、 attack surface が個別管理可能、 HF Space は CPU image を pull
- **短所**: image build matrix 増、 maintainer 負担増、 既存 docker-compose 互換性破壊
- **採否**: v1 では現状の 2 Dockerfile 構成を維持 (現方針継続)。 ただし本チケットは CPU のみ distroless 化することで実質的に「CPU と GPU を別 image として扱う」 方向に近づく。 v2 で完全分離検討。

### 結論

現時点での選択は **CPU 経路のみ distroless 化、 GPU 経路は別チケット切り出し** (理由: GPU distroless 化は CUDA toolkit 制約で blast radius 大、 HF Space は CPU image を主に pull、 段階導入で R-4 緩和)。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-014 (wyoming、 HA addon deploy 対象)
- **連携 milestone**: M3 内で 1 件後続 + 別チケット (GPU 経路 distroless 化、 別 milestone 候補)
- **依存解消**: FastAPI + uvicorn + onnxruntime-cpu の distroless 構成知見を wyoming (CPU only) に転用

### 7.2 引き継ぎ事項 (Handoff)

- HF Space deploy は CI 自動化されておらず、 user 手動で `huggingface-cli upload` か HF UI 経由で実施する必要あり
- cold start latency は CPU 推論で 30-60s が baseline、 distroless 後は 20-40s が目標
- GPU 経路の distroless 化は NVIDIA container runtime + cuDNN shared lib の COPY が必要、 blast radius 大で別チケット必須
- onnxruntime-cpu と onnxruntime-gpu の混在は provider 選択ミスの原因、 builder で 1 種類のみ install
- HF Space cold start 失敗時のロールバック手順: HF Space UI で 1 つ前の commit に revert (CI からは不可能、 user 手動)
- 1 image / 1 PR cadence を守る (FR-1.3)

### 7.3 未解決の質問

- [ ] image tag 戦略 (FR-1.5、 a vs b) — user 判断待ち、 推奨は (b) 並行配信
- [ ] GPU 経路の distroless 化を別チケットで実施するか M3 retrospective 後に判定
- [ ] HF Space staging slot の準備状況 (user 側 setup 必要)
- [ ] `Dockerfile.cpu` の実 base image 確認 (本 ticket 着手前に Read)

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 (`#1` Distroless), AC-1.2 (HF Space deploy)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md), M3-R2 / M3-R3 リスク
- 実 Dockerfile: [`docker/python-inference/Dockerfile`](../../../docker/python-inference/Dockerfile), [`docker/python-inference/Dockerfile.cpu`](../../../docker/python-inference/Dockerfile.cpu)
- 関連: `docker/python-inference/inference.py`, `docker/python-inference/test.py`, `docker/python-inference/docker-compose.yml`, `.github/workflows/deploy-huggingface.yml`
- 先行チケット: [T-016](T-016-distroless-cpp-dev.md), [T-015](T-015-distroless-cpp-inference.md), [T-013](T-013-distroless-webui.md)
- 外部: HuggingFace Spaces docs <https://huggingface.co/docs/hub/spaces-sdks-docker>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
