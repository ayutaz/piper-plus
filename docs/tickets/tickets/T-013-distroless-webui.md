# T-013: `webui` distroless 化

**チケット ID**: `T-013`
**Milestone**: [M3 Supply Chain](../milestones/M3-supply-chain.md)
**Proposal 項目**: `#1-2` (Distroless / Chainguard 移行 — `webui` image)
**Tier**: Tier 3 (Gradio demo、 中影響)
**Status**: 計画中
**PR**: (未作成)
**担当 (予定)**: Claude Code (agent team) + maintainer review
**着手前提**: T-015 完了推奨 (`pyopenjtalk` C 拡張の multi-stage knowledge を流用)

> **M3 内推奨実装順**: T-016 → T-015 → **T-013 (本チケット)** → T-012 → T-014。
> webui は Gradio Web UI で Python + JS hybrid。 静的 asset (Gradio 同梱の JS / CSS) の配置と Python 単体 image (NLTK data / pyopenjtalk C 拡張) の知見が、 後続 T-012 (python-inference) / T-014 (wyoming) の同 base に直接転用できる。

---

## 1. タスク目的とゴール

### 目的

`docker/webui/Dockerfile` は Gradio (Python + JavaScript) ベースの WebUI image。 現状 `python:3.13.13-slim-trixie` 単一 stage、 apt install で `libsndfile1`、 pip install で `piper_train` / Gradio / requirements。 image size ~1.5 GB、 CVE は base image に依存。

Gradio は内部に React build を持つため、 静的 asset の配置と nginx 介在の有無が distroless 化の論点。 現状 nginx は介在しておらず、 Gradio 自身が 7860 port で listen する Python サーバを起動。

### ゴール (Done definition)

- [ ] base image を `cgr.dev/chainguard/python:3.13` または `gcr.io/distroless/python3-debian12` に置換 (FR-1.2)
- [ ] multi-stage 化 (builder stage で pyopenjtalk C 拡張 build、 final stage で distroless)
- [ ] `docker compose up webui` で起動成功 (AC-1.1a)
- [ ] Gradio UI が `http://localhost:7860` でアクセス可能、 TTS 合成が動作
- [ ] image size 50%+ 削減 (AC-1.1b、 現状推定 ~1.5 GB → 750 MB 以下)
- [ ] `trivy image --severity HIGH,CRITICAL` で CVE 数 80%+ 削減 (AC-1.1c)
- [ ] image tag 戦略を user が決定し PR 本文に明記 (FR-1.5)
- [ ] PR コメントに `docker/webui/distroless-report.md` 自動投稿 (FR-1.4)
- [ ] NLTK data (`/usr/share/nltk_data`) が final stage で読み取り可能
- [ ] non-root user `piper` で起動

### user 判断待ち項目 (着手前確認)

1. **image tag 戦略 (FR-1.5)**:
   - (a) 既存 tag (`piper-plus-webui:latest`) を置換
   - (b) `piper-plus-webui:<ver>-distroless` を別 tag で並行配信
   - 推奨は (b)。 WebUI demo は外部ユーザ (Gradio Share 等) からの cold start 互換性懸念があるため、 並行配信で 1 週間観察後に置換。
2. **nginx を介在させるか**:
   - (a) 介在させない (現状維持、 Gradio 自身が 7860 listen)
   - (b) sidecar nginx で TLS / static asset cache を担当
   - 推奨は (a)。 nginx 導入は別 milestone (M4 docs infra 候補)。 本チケット scope 外。
3. **Gradio version pin の必要性**:
   - 現状 `requirements_webui.txt` で pin
   - distroless 移行に伴う再 build で transitive dep のみ変動する場合あり → `pip freeze` で full lock を採用するか user 判断

---

## 2. 実装内容の詳細

### 2.1 既存 Dockerfile の base image

| stage | base | 主要 install |
|-------|------|--------------|
| (single stage) | `python:3.13.13-slim-trixie` | apt `libsndfile1` + pip `uv` + `uv pip install /app/src/python[inference]` + `requirements_webui.txt` + NLTK data download |

### 2.2 移行後 base image 候補比較

| 候補 | 長所 | 短所 |
|------|------|------|
| `cgr.dev/chainguard/python:3.13` | Python 3.13 同梱、 minimal、 update cadence 早い | pip 同梱なしで pip install は builder 必須、 site-packages 配置 path 注意 |
| `gcr.io/distroless/python3-debian12` | Google maintained、 Debian 12 baseline、 free | Python version は固定 (3.11)、 3.13 が欲しい場合は使えない |
| `cgr.dev/chainguard/wolfi-base` + `apk add python-3.13` | Python 3.13、 apk で追加 install 容易、 shell 有り | size が python:3.13 image より大 |

**推奨**: `cgr.dev/chainguard/python:3.13`。 piper-plus は Python 3.13 を採用しているため version 整合性を優先。 distroless/python3-debian12 は Python 3.11 で version 後退するため不採用。

### 2.3 追加 / 変更ファイル

| path | 種別 | 概要 |
|------|------|------|
| `docker/webui/Dockerfile` | 変更 | multi-stage 化 + base image 置換 |
| `docker/webui/distroless-report.md` | 新規 | size + CVE diff の auto-generate 出力 |
| `docker/webui/entrypoint.sh` | 確認 | shell 不在環境で動作するよう exec form 化 (必要なら) |
| `.github/workflows/docker-build.yml` | 変更 | webui matrix に distroless variant 追加 (tag 戦略 b の場合) |
| `.github/workflows/webui-test.yml` | 確認 | distroless image での E2E test 追加 |
| `docs/reference/distroless-migration.md` | 追記 | webui 移行の知見追記 |

### 2.4 multi-stage build 構成

```dockerfile
# Stage 1: Builder (with apt + pip)
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

# wheel build to avoid editable workspace dep (cf. wyoming Dockerfile comment)
RUN uv build /build/src/python/g2p --wheel --out-dir /tmp/wheels/ \
    && uv build /build/src/python      --wheel --out-dir /tmp/wheels/

RUN uv pip install --system "$(ls /tmp/wheels/piper_plus_g2p-*.whl)[all]" \
    && uv pip install --system "$(ls /tmp/wheels/piper_train-*.whl)[inference]" \
    && uv pip install --system -r /build/requirements_webui.txt

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
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/share/nltk_data /usr/share/nltk_data
COPY --from=builder /usr/lib/x86_64-linux-gnu/libsndfile.so* /usr/lib/x86_64-linux-gnu/

ENV NLTK_DATA=/usr/share/nltk_data
ENV PYTHONUNBUFFERED=1
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

COPY docker/webui/app.py /app/app.py
COPY docker/webui/entrypoint.sh /app/entrypoint.sh

WORKDIR /app

# Create model / output dirs and switch user
RUN mkdir -p /models /output \
    && chown -R 65532:65532 /models /output /app

USER 65532

EXPOSE 7860

ENTRYPOINT ["/app/entrypoint.sh"]
```

### 2.5 静的 asset (Gradio React build) の配置

Gradio は `pip install gradio` で取得した site-packages の `gradio/templates/frontend/` に minified JS / CSS / HTML を内蔵。 distroless でも `/usr/local/lib/python3.13/site-packages/gradio/templates/` 経由でアクセス可能。 nginx 介在不要。

### 2.6 entrypoint.sh の distroless 互換性

現行 `docker/webui/entrypoint.sh` は bash script。 distroless python image には bash が含まれないため、 以下のいずれかで対応:

- (a) entrypoint.sh の logic を `app.py` に統合し、 ENTRYPOINT を `["python", "/app/app.py"]` 直接呼び出しに変更
- (b) builder から bash binary を COPY

**推奨**: (a)。 shell 依存を排除することで attack surface 削減と distroless 哲学に整合。

### 2.7 PR コメント自動投稿 (`docker/webui/distroless-report.md`)

format (FR-1.4): T-016 と同 format に Gradio 起動 sample 結果を追加:

```markdown
## Distroless migration report: `webui`

| metric | before | after | delta |
|--------|--------|-------|-------|
| image size | 1.52 GB | 0.71 GB | -53% |
| CVE HIGH | 12 | 1 | -92% |
| CVE CRITICAL | 2 | 0 | -100% |

### Gradio smoke test
- `docker run -p 7860:7860 ...` → exit 0
- `curl http://localhost:7860/info` → HTTP 200
- TTS synthesis via Gradio API → wav 生成成功
```

---

## 3. エージェントチームの役割と人数

| 役割 | 人数 | 担当 | 主要 deliverable |
|------|----|------|----------------|
| **Implementer** | 1 | Dockerfile 移行 + multi-stage build | `docker/webui/Dockerfile` |
| **Test author** | 1 | webui-test.yml の distroless 拡張 + Gradio smoke test | `.github/workflows/webui-test.yml`, `docker/webui/test_app.py` |
| **Spec / Doc author** | 1 | entrypoint.sh の app.py 統合 + distroless-migration.md 追記 | `docker/webui/app.py` 修正、 doc |
| **Reviewer** | 1 | Gradio static asset / NLTK data 配置確認 | review |

**並列度**: T-015 完了後に着手。 wyoming Dockerfile の wheel build pattern (workspace editable 回避) を流用するため、 該当 comment を T-015 / T-013 doc に転記しておく。

**Agent prompt の与え方**: Explore subagent で `docker/webui/Dockerfile` + `app.py` + `entrypoint.sh` + `requirements_webui.txt` を dump → general-purpose で wheel build + distroless final stage 実装と Gradio 動作確認並列。

---

## 4. 提供範囲とテスト項目

### 4.1 提供範囲 (Scope)

**In scope**:

- `docker/webui/Dockerfile` の multi-stage 化 + distroless 化
- entrypoint.sh の app.py 統合 (shell 依存排除)
- NLTK data + libsndfile shared lib の final stage 配置
- Gradio 起動 + TTS 合成の smoke test

**Out of scope**:

- 他の 4 image (別チケット)
- nginx 介在 (別 milestone)
- HuggingFace Space deploy (別チケット T-012 / 別 PR、 webui は HF Space 対象外)
- Gradio version major upgrade (独立 PR)

### 4.2 Unit テスト項目

| ID | 対象 | 入力 | 期待出力 |
|----|------|------|---------|
| UT-1 | Dockerfile build | `docker build -f docker/webui/Dockerfile .` | exit 0 |
| UT-2 | image size | `docker images --format '{{.Size}}'` | before の 50% 以下 |
| UT-3 | CVE scan | `trivy image --severity HIGH,CRITICAL` | before の 20% 以下 |
| UT-4 | Python import | `docker run ... python -c "import piper_train; import gradio"` | exit 0 |
| UT-5 | NLTK data | `docker run ... python -c "import nltk; nltk.data.find('taggers/averaged_perceptron_tagger')"` | exit 0 |
| UT-6 | libsndfile | `docker run ... python -c "import soundfile as sf; sf.info"` | exit 0 |

### 4.3 E2E テスト項目

| ID | シナリオ | 検証手段 |
|----|--------|---------|
| E2E-1 | full build | `docker build -t webui:distroless .` → image 生成 |
| E2E-2 | Gradio 起動 | `docker run -p 7860:7860 -v $(pwd)/test/models:/models webui:distroless` → `curl http://localhost:7860/info` で HTTP 200 |
| E2E-3 | TTS 合成 | Gradio API 経由で `synthesize_speech(text="test", language="en")` → wav 出力 |
| E2E-4 | PR コメント | distroless-report.md が PR に自動投稿 |
| E2E-5 | non-root user | `docker run ... id` で `uid=65532` 確認 |

### 4.4 リグレッション確認

- [ ] 既存 `webui-test.yml` workflow が継続 pass
- [ ] `docker-compose.yml` の volume mount (models / output) が動作
- [ ] `hadolint.yml` rule pass (DEP-1.1)
- [ ] silent-zero 防御: `trivy image` 出力件数 0 件で `::warning::`

---

## 5. 実装に関する懸念事項とレビュー項目

### 5.1 懸念事項

| ID | 懸念 | 対策 | 検出機構 |
|----|------|------|---------|
| C-1 | `pyopenjtalk` C 拡張 (`.so`) が distroless final で symbol resolution 失敗 | builder で wheel build → final に COPY `/usr/local/lib/python3.13`、 libsndfile / libgomp も COPY | UT-4 |
| C-2 | NLTK data path が `/usr/share/nltk_data` で non-root user に読み取り権限なし | builder で chown 不要 (world readable)、 final で `chmod -R 755 /usr/share/nltk_data` 確認 | UT-5 |
| C-3 | Gradio static asset (React build) が site-packages 内に存在しない | site-packages 全体を COPY するため自動で含まれる | E2E-2 |
| C-4 | entrypoint.sh の shell 依存 | app.py に統合し ENTRYPOINT を python 直接呼び出しに変更 | E2E-1 |
| C-5 | non-root user UID (65532 = Chainguard default) と既存 piper user (1000) のミスマッチ | volume mount permission を 65532 に変更 (docker-compose.yml 更新) | E2E-5 |
| C-6 | HEALTHCHECK の curl がない (distroless 不在) | Python の urllib で代替: `HEALTHCHECK CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:7860/info')"]` | E2E-2 |

### 5.2 レビュー項目 (チェックリスト)

- [ ] base image が `cgr.dev/chainguard/python:3.13` であること (FR-1.2、 Python version 3.13 維持)
- [ ] builder stage で wheel build され final に editable install が漏れていないこと (wyoming Dockerfile の comment 参照)
- [ ] image tag 戦略が PR 本文 §1 で明示されていること (FR-1.5、 user 判断)
- [ ] `docker/webui/distroless-report.md` が PR コメントに投稿されること (FR-1.4)
- [ ] image size 50%+ 削減 / CVE 80%+ 削減を満たすこと (AC-1.1)
- [ ] Gradio UI が `http://localhost:7860` で起動すること (E2E-2)
- [ ] TTS 合成が API 経由で動作すること (E2E-3)
- [ ] entrypoint.sh が exec form または app.py に統合されていること
- [ ] HEALTHCHECK が distroless 互換 (exec form + python 経由) であること
- [ ] non-root user (UID 65532) で起動すること
- [ ] silent-zero pattern を踏んでいないか
- [ ] action SHA pin が `@v<X.Y.Z>` または 40-hex か
- [ ] `permissions:` が least privilege か
- [ ] markdownlint / hadolint 全 pass
- [ ] PR 本文が `pull_request_template.md` の section 構造に準拠しているか

---

## 6. 一から作り直すとしたら

### 案 A: Gradio を捨てて Streamlit に置換

- **概要**: Gradio は React build 同梱で size が大きい。 Streamlit は同等機能で size 小、 distroless との親和性高。
- **長所**: image size さらに削減 (~200 MB 程度の差)、 UI customization の自由度向上
- **短所**: 既存 `app.py` の Gradio 依存を全面書き換え、 既存 demo URL / 利用者の移行 cost、 audio playback の UX 差異
- **採否**: v1 では Gradio 継続 (現方針)。 v2 で UI framework 再評価時に検討。

### 案 B: WebUI を SSR (Astro / Next.js) で再実装し、 Python は API バックエンドに専念

- **概要**: フロントは Astro / Next.js でビルド (Node.js distroless image)、 バックエンドは python:distroless で FastAPI を 8000 で expose。 docker-compose 2 service 構成。
- **長所**: フロント / バック分離で attack surface 個別管理、 各 image を最小化
- **短所**: 2 service 構成で deploy 複雑化、 maintainer の前提知識増、 docker-compose ファイル増
- **採否**: v1 では単一 image を維持。 v2 で micro-service 化検討時に再評価。

### 結論

現時点での選択は **Gradio + 単一 image を維持し、 distroless base への置換のみ実施** (理由: M3 scope 内に収まる、 既存利用者影響最小、 後続 T-012 / T-014 に Python distroless 知見を直接転用可)。

---

## 7. 後続タスクへの申し送り

### 7.1 完了後に発生する後続作業

- **後続チケット**: T-012 (python-inference、 HF Space deploy 対象)、 T-014 (wyoming、 HA addon 対象)
- **連携 milestone**: M3 内で 2 件後続
- **依存解消**: pyopenjtalk C 拡張 multi-stage + NLTK data 配置 + libsndfile shared lib 配置 pattern を後続 2 image に転用

### 7.2 引き継ぎ事項 (Handoff)

- wheel build pattern (`uv build /build/src/python/g2p --wheel`) は wyoming Dockerfile の comment 参照、 workspace editable 回避必須
- `cgr.dev/chainguard/python:3.13` の default user は UID 65532 (`nonroot`)、 既存 piper user (UID 1000) から変更
- HEALTHCHECK は exec form + Python urllib で書く (curl 不在)
- entrypoint.sh は app.py に統合可能 (shell 依存排除推奨)
- libsndfile1 shared lib (`libsndfile.so*`) は builder から COPY 必須 (apt install が distroless で動作しないため)
- 1 image / 1 PR cadence を守る (FR-1.3)

### 7.3 未解決の質問

- [ ] image tag 戦略 (FR-1.5、 a vs b) — user 判断待ち、 推奨は (b) 並行配信 1 週間観察
- [ ] non-root user UID を 65532 (Chainguard default) にするか 1000 (既存 piper user) にするか — docker-compose volume mount permission との整合性で user 判断
- [ ] requirements_webui.txt の `pip freeze` full lock 採用 — distroless build 再現性確保のため検討

---

## 8. 参照

- 要求定義: [`docs/proposals/ci-expansion-deferred-items-requirements.md`](../../proposals/ci-expansion-deferred-items-requirements.md) §4.1 (`#1` Distroless)
- 要件定義書: [`docs/proposals/ci-expansion-deferred-items-system-requirements.md`](../../proposals/ci-expansion-deferred-items-system-requirements.md) §4.3
- Milestone: [`docs/tickets/milestones/M3-supply-chain.md`](../milestones/M3-supply-chain.md)
- 実 Dockerfile: [`docker/webui/Dockerfile`](../../../docker/webui/Dockerfile)
- 関連: `docker/webui/app.py`, `docker/webui/entrypoint.sh`, `src/python_run/requirements_webui.txt`, `.github/workflows/webui-test.yml`
- 先行チケット: [T-016](T-016-distroless-cpp-dev.md), [T-015](T-015-distroless-cpp-inference.md)
- 外部: Chainguard python <https://images.chainguard.dev/directory/image/python>

---

## 9. 変更履歴

| 日付 | 変更 | 担当 |
|------|------|------|
| 2026-05-19 | 初版 | Claude Code |
